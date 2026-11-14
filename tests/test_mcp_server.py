"""integration/mcp/citeguard_mcp.py 的端到端测试（全离线）。

设计口径与 tests/ 其余用例一致：
- **不联网**：用标准库 ``http.server`` 在 127.0.0.1 起一个 mock CiteGuard，
  只实现 ``/api/health``、``/api/support/check``、``/api/live/check``。
- **真实进程**：MCP 服务以 ``subprocess`` 启动，走真实的 stdio 管道，
  断言的是 Claude Desktop / Cursor 等 MCP 客户端会看到的那一层 JSON，而不是直接调用函数。
- **可控超时**：stdout 由后台线程读进队列，任何一条响应缺失都会在 10s 内
  给出带 stderr 的失败信息，不会挂死测试会话。
"""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]  # citeguard/
SERVER_SCRIPT = ROOT / "integration" / "mcp" / "citeguard_mcp.py"

TOOL_NAMES = {"citeguard_health", "citeguard_check_support", "citeguard_live_check"}


# --------------------------------------------------------------------------- #
# Mock CiteGuard HTTP 服务
# --------------------------------------------------------------------------- #


class MockCiteGuard(BaseHTTPRequestHandler):
    """最小 CiteGuard API：记录每次调用，按路径返回可断言的固定 JSON。"""

    calls: list[dict] = []
    support_error: tuple[int, dict] | None = None
    _lock = threading.Lock()

    # --- helpers -------------------------------------------------------- #
    def _record(self, body) -> None:
        with type(self)._lock:
            type(self).calls.append(
                {"method": self.command, "path": self.path, "body": body}
            )

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:  # 服务端也应给出可读错误，这里保留原文
            return raw.decode("utf-8", "replace")

    # --- HTTP verbs ----------------------------------------------------- #
    def do_GET(self):  # noqa: N802 (http.server API)
        self._record(None)
        if self.path == "/api/health":
            self._send(
                200,
                {
                    "ok": True,
                    "version": "9.9.9-mock",
                    "offline": False,
                    "supported": [".pdf", ".txt"],
                },
            )
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self):  # noqa: N802 (http.server API)
        body = self._read_body()
        self._record(body)
        if self.path == "/api/support/check":
            if type(self).support_error is not None:
                status, payload = type(self).support_error
                self._send(status, payload)
                return
            evidence = (body or {}).get("evidence", "")
            self._send(
                200,
                {
                    "ok": True,
                    "label": "support",
                    "confidence": 0.91,
                    "reason": "mock judge",
                    "evidence": evidence[:12],
                    "prompt_version": "mock",
                },
            )
        elif self.path == "/api/live/check":
            self._send(
                200,
                {
                    "ok": True,
                    "verdict": "matched",
                    "claim": (body or {}).get("claim"),
                    "mode": (body or {}).get("mode"),
                    "phase": (body or {}).get("phase"),
                },
            )
        else:
            self._send(404, {"detail": "not found"})

    def log_message(self, *args):  # 静音测试输出
        pass


@pytest.fixture(scope="module")
def mock_service():
    """整个模块共用一个 mock 服务，避免每个用例重复起停 HTTP 端口。"""
    MockCiteGuard.calls = []
    MockCiteGuard.support_error = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockCiteGuard)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", MockCiteGuard
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _fresh_mock_state(mock_service):
    """每个用例开始前清空 mock 的调用记录与错误注入，保证互相独立。"""
    _base_url, handler = mock_service
    handler.calls = []
    handler.support_error = None
    yield


# --------------------------------------------------------------------------- #
# MCP 子进程客户端
# --------------------------------------------------------------------------- #


class McpProcess:
    """用 stdin/stdout 管道驱动真正的 MCP 服务进程。"""

    def __init__(self, base_url: str, extra_env: dict | None = None):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("CITEGUARD_")
        }
        env.update(
            {
                "CITEGUARD_BASE_URL": base_url,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
            }
        )
        env.update(extra_env or {})
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(ROOT),
            env=env,
        )
        self.messages: queue.Queue[str] = queue.Queue()
        self.stderr_lines: list[str] = []
        self.initialized = False
        self._next_id = 0
        self._reader = threading.Thread(target=self._pump_stdout, daemon=True)
        self._err_reader = threading.Thread(target=self._pump_stderr, daemon=True)
        self._reader.start()
        self._err_reader.start()

    # --- plumbing ------------------------------------------------------- #
    def _pump_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            if line.strip():
                self.messages.put(line.rstrip("\n"))

    def _pump_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self.stderr_lines.append(line.rstrip("\n"))

    def stderr_text(self) -> str:
        time.sleep(0.05)  # 给 stderr 读取线程一点时间追上
        return "\n".join(self.stderr_lines)

    # --- protocol ------------------------------------------------------- #
    def write_raw(self, text: str) -> None:
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:  # pragma: no cover
            pytest.fail(f"MCP 服务进程已退出，无法写入：{exc}\nstderr:\n{self.stderr_text()}")

    def send(self, method: str, params=None, *, request_id=None, notification=False):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notification:
            if request_id is None:
                self._next_id += 1
                request_id = self._next_id
            message["id"] = request_id
        self.write_raw(json.dumps(message, ensure_ascii=False))
        return request_id

    def read(self, timeout: float = 10.0) -> dict:
        try:
            line = self.messages.get(timeout=timeout)
        except queue.Empty:
            pytest.fail(
                f"MCP 服务 {timeout:g}s 内没有响应。\nstderr:\n{self.stderr_text()}"
            )
        try:
            return json.loads(line)
        except ValueError:  # pragma: no cover - 协议被破坏时应立刻失败
            pytest.fail(f"stdout 出现非 JSON 行：{line!r}")

    def initialize(self) -> dict:
        self.send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        )
        response = self.read()
        self.send("notifications/initialized", notification=True)
        self.initialized = True
        return response

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        self.send("tools/call", {"name": name, "arguments": arguments or {}})
        return self.read()

    # --- lifecycle ------------------------------------------------------ #
    def close(self) -> int:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except OSError:  # pragma: no cover
            pass
        try:
            return self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            self.proc.kill()
            return self.proc.wait(timeout=5)


@pytest.fixture(scope="module")
def shared_client(mock_service):
    """一个长驻 MCP 进程模拟真实会话：多轮 tools/call 复用同一条 stdio 管道。"""
    base_url, _handler = mock_service
    proc = McpProcess(base_url)
    try:
        yield proc
    finally:
        proc.close()


@pytest.fixture()
def client(shared_client):
    """已握手的共享客户端；需要全新进程的用例自行创建 McpProcess。"""
    if not shared_client.initialized:
        shared_client.initialize()
    return shared_client


@pytest.fixture()
def mcp(client):
    return client


def _tool_text(response: dict) -> str:
    result = response["result"]
    assert result["isError"] is False, result
    content = result["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"
    return content[0]["text"]


def _tool_error_text(response: dict) -> str:
    result = response["result"]
    assert result["isError"] is True, result
    content = result["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"
    text = content[0]["text"]
    assert "Traceback" not in text
    return text


# --------------------------------------------------------------------------- #
# 协议层
# --------------------------------------------------------------------------- #


def test_initialize_returns_protocol_version_and_tools_capability(mock_service):
    base_url, _handler = mock_service
    fresh = McpProcess(base_url)
    try:
        response = fresh.initialize()
    finally:
        fresh.close()

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "citeguard-mcp"
    assert isinstance(result["serverInfo"]["version"], str)
    assert result["serverInfo"]["version"]


def test_notification_initialized_is_not_answered(client):
    # 共享客户端已在 fixture 中完成握手，这里只验证通知不产生响应
    client.send("notifications/initialized", notification=True)
    client.send("ping", request_id="after-notification")

    response = client.read()
    assert response["id"] == "after-notification"
    assert response["result"] == {}
    # 通知不能被回复：ping 的响应之后不应再有任何消息
    time.sleep(0.2)
    assert client.messages.empty()


def test_tools_list_exposes_three_documented_tools(mcp):
    mcp.send("tools/list")
    response = mcp.read()

    tools = response["result"]["tools"]
    assert {tool["name"] for tool in tools} == TOOL_NAMES
    assert len(tools) == 3

    by_name = {tool["name"]: tool for tool in tools}
    for tool in tools:
        assert tool["description"].strip()
        assert tool["inputSchema"]["type"] == "object"

    support = by_name["citeguard_check_support"]
    assert set(support["inputSchema"]["required"]) == {"claim", "evidence"}

    live = by_name["citeguard_live_check"]
    assert live["inputSchema"]["required"] == ["claim"]
    assert live["inputSchema"]["properties"]["mode"]["enum"] == ["fast", "full"]
    assert live["inputSchema"]["properties"]["phase"]["enum"] == [
        "retrieve",
        "judge",
        "full",
    ]

    health = by_name["citeguard_health"]
    assert health["inputSchema"]["properties"] == {}


def test_unknown_method_returns_jsonrpc_error_32601(client):
    client.send("citeguard/not-a-method", request_id="m-404")
    response = client.read()

    assert response["id"] == "m-404"
    assert response["error"]["code"] == -32601
    assert "citeguard/not-a-method" in response["error"]["message"]
    assert client.proc.poll() is None, "未知方法不应让服务进程退出"


def test_malformed_json_line_returns_parse_error_without_crashing(client):
    client.write_raw("{this is not json")
    response = client.read()

    assert response["id"] is None
    assert response["error"]["code"] == -32700

    # 解析错误后仍能继续服务
    client.send("ping", request_id="still-alive")
    assert client.read()["id"] == "still-alive"


def test_blank_lines_are_ignored_and_eof_exits_cleanly(mock_service):
    base_url, _handler = mock_service
    fresh = McpProcess(base_url)
    try:
        fresh.write_raw("")
        fresh.send("ping", request_id="p1")
        assert fresh.read()["id"] == "p1"
    finally:
        exit_code = fresh.close()
    assert exit_code == 0


# --------------------------------------------------------------------------- #
# 工具层：请求透传与返回格式
# --------------------------------------------------------------------------- #


def test_health_tool_calls_get_api_health(mcp, mock_service):
    _base_url, handler = mock_service
    response = mcp.call_tool("citeguard_health")

    payload = json.loads(_tool_text(response))
    assert payload == {
        "ok": True,
        "version": "9.9.9-mock",
        "offline": False,
        "supported": [".pdf", ".txt"],
    }
    assert handler.calls[-1] == {"method": "GET", "path": "/api/health", "body": None}


def test_check_support_forwards_claim_and_evidence(mcp, mock_service):
    _base_url, handler = mock_service
    claim = "该方法在中文论文上平均提升 2.3%。"
    evidence = "实验显示，该方法在中文论文数据集上平均提升 2.1%。"

    response = mcp.call_tool(
        "citeguard_check_support", {"claim": claim, "evidence": evidence}
    )

    payload = json.loads(_tool_text(response))
    assert payload["label"] == "support"
    assert payload["confidence"] == 0.91
    assert handler.calls[-1] == {
        "method": "POST",
        "path": "/api/support/check",
        "body": {"claim": claim, "evidence": evidence},
    }


def test_live_check_uses_documented_defaults(mcp, mock_service):
    _base_url, handler = mock_service
    response = mcp.call_tool(
        "citeguard_live_check",
        {
            "claim": "该文提出了一种新的中文引文核验方法。",
            "page_title": "引文核验方法研究",
            "page_url": "https://example.org/paper",
        },
    )

    payload = json.loads(_tool_text(response))
    assert payload["verdict"] == "matched"
    assert handler.calls[-1]["body"] == {
        "claim": "该文提出了一种新的中文引文核验方法。",
        "page_title": "引文核验方法研究",
        "page_url": "https://example.org/paper",
        "mode": "fast",
        "phase": "full",
    }


def test_live_check_forwards_mode_and_phase(mcp, mock_service):
    _base_url, handler = mock_service
    response = mcp.call_tool(
        "citeguard_live_check",
        {
            "claim": "只做检索阶段。",
            "mode": "full",
            "phase": "retrieve",
        },
    )

    payload = json.loads(_tool_text(response))
    assert payload["mode"] == "full"
    assert payload["phase"] == "retrieve"
    assert handler.calls[-1]["body"] == {
        "claim": "只做检索阶段。",
        "mode": "full",
        "phase": "retrieve",
    }


# --------------------------------------------------------------------------- #
# 错误路径：HTTP/参数/连接失败都必须是 isError 文本，不能抛栈
# --------------------------------------------------------------------------- #


def test_http_error_becomes_is_error_without_traceback(mcp, mock_service):
    _base_url, handler = mock_service
    handler.support_error = (400, {"detail": "需要 claim 和 evidence 两个字段"})

    response = mcp.call_tool(
        "citeguard_check_support", {"claim": "论点", "evidence": "证据"}
    )

    text = _tool_error_text(response)
    assert "HTTP 400" in text
    assert "需要 claim 和 evidence 两个字段" in text
    assert mcp.proc.poll() is None, "HTTP 错误不应让服务进程退出"

    # 出错后服务必须还能继续用（AI 客户端会继续发请求）
    mcp.send("ping", request_id="after-http-error")
    assert mcp.read()["id"] == "after-http-error"


def test_connection_refused_is_readable_error():
    # 拿一个刚释放的端口，保证没有服务在监听
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    base_url = f"http://127.0.0.1:{free_port}"

    proc = McpProcess(base_url)
    try:
        proc.initialize()
        response = proc.call_tool("citeguard_health")
        text = _tool_error_text(response)
        assert "无法连接 CiteGuard 服务" in text
        assert base_url in text
        assert "uvicorn" in text  # 给出怎么修
        assert proc.proc.poll() is None
    finally:
        proc.close()


def test_missing_required_argument_is_rejected_before_http(mcp, mock_service):
    _base_url, handler = mock_service
    before = len(handler.calls)

    response = mcp.call_tool("citeguard_check_support", {"claim": "只有论点"})

    text = _tool_error_text(response)
    assert "evidence" in text
    assert len(handler.calls) == before, "参数校验失败时不应发 HTTP 请求"


def test_invalid_mode_is_rejected_before_http(mcp, mock_service):
    _base_url, handler = mock_service
    before = len(handler.calls)

    response = mcp.call_tool(
        "citeguard_live_check", {"claim": "论点", "mode": "slow"}
    )

    text = _tool_error_text(response)
    assert "mode" in text and "fast" in text
    assert len(handler.calls) == before


def test_unknown_tool_returns_is_error_and_lists_available_tools(mcp):
    response = mcp.call_tool("citeguard_missing", {})

    text = _tool_error_text(response)
    assert "未知工具" in text
    for name in TOOL_NAMES:
        assert name in text
    assert mcp.proc.poll() is None


# --------------------------------------------------------------------------- #
# 静态契约：默认值必须与文档一致
# --------------------------------------------------------------------------- #


def _load_server_module():
    spec = importlib.util.spec_from_file_location(
        "citeguard_mcp_under_test", SERVER_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_base_url_and_timeout_match_docs():
    module = _load_server_module()

    assert module.DEFAULT_BASE_URL == "http://127.0.0.1:8013"
    assert module.DEFAULT_TIMEOUT == 60.0
    assert module.PROTOCOL_VERSION == "2024-11-05"
    assert module.SERVER_NAME == "citeguard-mcp"


def test_server_script_uses_stdlib_only():
    source = SERVER_SCRIPT.read_text(encoding="utf-8")
    imports = {
        line.split()[1]
        for line in source.splitlines()
        if line.startswith("import ")
    }
    assert imports <= {"json", "os", "sys", "urllib.error", "urllib.parse", "urllib.request"}
    assert "from __future__" in source
