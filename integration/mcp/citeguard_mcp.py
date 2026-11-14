#!/usr/bin/env python3
"""CiteGuard-CN MCP stdio 服务（零依赖，仅标准库）。

把 CiteGuard 的核验能力暴露成 Model Context Protocol (MCP) 工具，供
Claude Desktop / Cursor 等 AI 客户端直接调用。传输层是最简单的 stdio：
stdin/stdout 上每行一个 JSON-RPC 2.0 对象（UTF-8），日志与调试信息只写 stderr，
因此 stdout 永远只有协议消息。

提供的工具：
    citeguard_health          GET  {BASE}/api/health
    citeguard_check_support   POST {BASE}/api/support/check
    citeguard_live_check      POST {BASE}/api/live/check

启动（先让 CiteGuard 服务在监听）：
    python integration/mcp/citeguard_mcp.py

环境变量：
    CITEGUARD_BASE_URL     CiteGuard 服务地址，默认 http://127.0.0.1:8013
    CITEGUARD_MCP_TIMEOUT  单次 HTTP 超时秒数，默认 60
    CITEGUARD_MCP_DEBUG    "1" 时把协议/HTTP 诊断写到 stderr

只依赖 json/os/sys/urllib，不 import citeguard 包，所以既不需要安装本仓库，
也不会和产品依赖（FastAPI 等）耦合。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "citeguard-mcp"
SERVER_VERSION = "1.0.0"
DEFAULT_BASE_URL = "http://127.0.0.1:8013"
DEFAULT_TIMEOUT = 60.0

# 说明：这里刻意只使用 Python 标准库，且不 import citeguard 包——MCP 客户端
# 往往用一个独立的 Python 解释器拉起本文件，装没装产品依赖都要能跑。

TOOLS = [
    {
        "name": "citeguard_health",
        "description": (
            "检查本地 CiteGuard 服务是否在线。返回 ok、版本、是否离线模式，"
            "以及支持的输入格式列表。无参数。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "citeguard_check_support",
        "description": (
            "判断一条论点（claim）是否被给定证据（evidence，通常是摘要或原文段落）支持。"
            "返回 support / partial / contradict / no_evidence 等标签、置信度与理由；"
            "证据不足时明确返回 no_evidence，不做真伪裁决。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim": {
                    "type": "string",
                    "description": "待核验的论点，最长 500 字。",
                },
                "evidence": {
                    "type": "string",
                    "description": (
                        "证据文本（摘要/段落）。服务端会截断到 8000 字；"
                        "空字符串会被拒绝。"
                    ),
                },
            },
            "required": ["claim", "evidence"],
            "additionalProperties": False,
        },
    },
    {
        "name": "citeguard_live_check",
        "description": (
            "CiteGuard Live：判断浏览器页面里选中的一句话与页面检索到的候选摘要是否一致"
            "（划词核验）。claim 必填，页面标题/URL 至少提供一个效果最好。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim": {
                    "type": "string",
                    "description": "页面中选中的句子，最长 500 字。",
                },
                "page_title": {
                    "type": "string",
                    "description": "页面标题（可选），最长 300 字。",
                },
                "page_url": {
                    "type": "string",
                    "description": "页面 URL（可选），最长 2048 字符。",
                },
                "mode": {
                    "type": "string",
                    "enum": ["fast", "full"],
                    "default": "fast",
                    "description": "fast=轻量检索（默认）；full=完整检索。",
                },
                "phase": {
                    "type": "string",
                    "enum": ["retrieve", "judge", "full"],
                    "default": "full",
                    "description": (
                        "retrieve=只检索；judge=只判定（不重新检索）；full=检索+判定（默认）。"
                    ),
                },
            },
            "required": ["claim"],
            "additionalProperties": False,
        },
    },
]

_TOOL_NAMES = tuple(tool["name"] for tool in TOOLS)


class CiteGuardError(Exception):
    """可安全展示给 MCP 客户端的错误（不携带栈）。

    消息里写清是哪一步失败、服务端返回了什么、以及怎么修（启动服务/检查 key），
    这样 AI 客户端可以直接把这句话转述给用户。
    """


def _debug(message: str) -> None:
    if os.environ.get("CITEGUARD_MCP_DEBUG") == "1":
        sys.stderr.write("[citeguard-mcp] " + message + "\n")
        sys.stderr.flush()


def _base_url() -> str:
    return (os.environ.get("CITEGUARD_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _timeout() -> float:
    raw = os.environ.get("CITEGUARD_MCP_TIMEOUT")
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise CiteGuardError(
            f"CITEGUARD_MCP_TIMEOUT 必须是数字（当前为 {raw!r}），例如 60"
        ) from None
    if value <= 0:
        raise CiteGuardError("CITEGUARD_MCP_TIMEOUT 必须大于 0")
    return value


def _is_loopback(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


def _opener(url: str):
    """本机地址绕过系统代理。

    Windows 上 urllib 会读取注册表里的 HTTP 代理；如果用户开着科学上网工具，
    发往 127.0.0.1 的请求也可能被塞进代理而失败。回环地址直接禁用代理更稳，
    远程地址（团队共享的 CiteGuard）仍走系统代理设置。
    """
    if _is_loopback(url):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def _describe_http_error(exc: urllib.error.HTTPError, url: str) -> str:
    detail = ""
    try:
        raw = exc.read()
    except Exception:  # pragma: no cover - 读错误体失败不应掩盖 HTTP 状态
        raw = b""
    text = raw.decode("utf-8", "replace").strip() if raw else ""
    if text:
        try:
            parsed = json.loads(text)
        except ValueError:
            detail = " ".join(text.split())[:300]
        else:
            if isinstance(parsed, dict):
                for key in ("detail", "error", "message"):
                    value = parsed.get(key)
                    if isinstance(value, str) and value.strip():
                        detail = value.strip()
                        break
                if not detail:
                    detail = json.dumps(parsed, ensure_ascii=False)[:300]
            else:
                detail = json.dumps(parsed, ensure_ascii=False)[:300]
    return f"CiteGuard API 返回 HTTP {exc.code}（{url}）：{detail or '无错误详情'}"


def request_json(method: str, path: str, payload: dict | None = None):
    """调用 CiteGuard HTTP API 并把 JSON 响应解析成 Python 对象。

    所有失败（连不上、超时、HTTP 4xx/5xx、响应不是 JSON）都转换成
    带中文说明的 CiteGuardError，调用方据此返回 MCP 的 isError 结果。
    """
    url = _base_url() + path
    body = None
    headers = {
        "Accept": "application/json",
        "User-Agent": f"{SERVER_NAME}/{SERVER_VERSION}",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    _debug(f"{method} {url} body={body.decode('utf-8') if body else '<none>'}")
    try:
        timeout = _timeout()
        with _opener(url).open(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise CiteGuardError(_describe_http_error(exc, url)) from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError,)) or "timed out" in str(reason).lower():
            raise CiteGuardError(
                f"请求 {url} 超时（CITEGUARD_MCP_TIMEOUT={_timeout():g}s）。"
                "判定模型较慢时可调大该值，或先用 phase=retrieve 只做检索。"
            ) from None
        raise CiteGuardError(
            f"无法连接 CiteGuard 服务 {url}：{reason}。"
            "请先在仓库根目录启动服务："
            "python -m uvicorn web.app:app --host 127.0.0.1 --port 8013"
        ) from None
    except TimeoutError:
        raise CiteGuardError(
            f"请求 {url} 超时（CITEGUARD_MCP_TIMEOUT={_timeout():g}s）。"
        ) from None
    except OSError as exc:
        raise CiteGuardError(f"请求 {url} 失败：{exc}") from None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CiteGuardError(
            f"{url} 返回了非 UTF-8 响应（{len(raw)} 字节），服务端可能不是 CiteGuard。"
        ) from None
    try:
        return json.loads(text)
    except ValueError:
        snippet = " ".join(text.split())[:200]
        raise CiteGuardError(
            f"{url} 返回的不是 JSON：{snippet or '<空响应>'}。"
            "请确认 CITEGUARD_BASE_URL 指向的是一个 CiteGuard 服务。"
        ) from None


def _compact(value) -> str:
    """MCP content.text 用紧凑 JSON，省 token 也便于客户端解析。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _require_text(arguments: dict, key: str, *, max_length: int, optional: bool = False) -> str:
    value = arguments.get(key)
    if value is None:
        if optional:
            return ""
        raise CiteGuardError(f"缺少必填参数 {key}（非空字符串）")
    if not isinstance(value, str):
        raise CiteGuardError(f"参数 {key} 必须是字符串，实际是 {type(value).__name__}")
    text = value.strip()
    if not text and not optional:
        raise CiteGuardError(f"参数 {key} 不能为空")
    if len(text) > max_length:
        raise CiteGuardError(f"参数 {key} 最长 {max_length} 字，当前 {len(text)} 字")
    return text


def _tool_health(arguments: dict) -> dict:
    return request_json("GET", "/api/health")


def _tool_check_support(arguments: dict) -> dict:
    claim = _require_text(arguments, "claim", max_length=500)
    evidence = _require_text(arguments, "evidence", max_length=8000)
    return request_json(
        "POST", "/api/support/check", {"claim": claim, "evidence": evidence}
    )


def _tool_live_check(arguments: dict) -> dict:
    claim = _require_text(arguments, "claim", max_length=500)
    page_title = _require_text(arguments, "page_title", max_length=300, optional=True)
    page_url = _require_text(arguments, "page_url", max_length=2048, optional=True)

    mode = arguments.get("mode") or "fast"
    if not isinstance(mode, str) or mode not in {"fast", "full"}:
        raise CiteGuardError(f"参数 mode 只能是 fast 或 full，当前 {mode!r}")
    phase = arguments.get("phase") or "full"
    if not isinstance(phase, str) or phase not in {"retrieve", "judge", "full"}:
        raise CiteGuardError(f"参数 phase 只能是 retrieve、judge 或 full，当前 {phase!r}")

    payload = {"claim": claim, "mode": mode, "phase": phase}
    if page_title:
        payload["page_title"] = page_title
    if page_url:
        payload["page_url"] = page_url
    return request_json("POST", "/api/live/check", payload)


_HANDLERS = {
    "citeguard_health": _tool_health,
    "citeguard_check_support": _tool_check_support,
    "citeguard_live_check": _tool_live_check,
}


def _tool_result(payload) -> dict:
    return {"content": [{"type": "text", "text": _compact(payload)}], "isError": False}


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def call_tool(name: str, arguments: dict) -> dict:
    """执行一个工具，返回 MCP 标准的 tools/call result。"""
    handler = _HANDLERS.get(name)
    if handler is None:
        return _tool_error(
            f"未知工具 {name!r}。可用工具：{', '.join(_TOOL_NAMES)}"
        )
    try:
        payload = handler(arguments)
    except CiteGuardError as exc:
        return _tool_error(str(exc))
    except Exception as exc:  # 兜底：任何未预期异常都变成可读文本，绝不把栈丢给客户端
        _debug(f"tool {name} crashed: {exc!r}")
        return _tool_error(f"调用 {name} 时内部错误：{exc.__class__.__name__}: {exc}")
    return _tool_result(payload)


def _result(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _initialize_result() -> dict:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": (
            "CiteGuard-CN：中文引证核验。先用 citeguard_health 确认本地服务在线，"
            "再用 citeguard_check_support 判断 claim 与 evidence 是否一致，"
            "或用 citeguard_live_check 做页面划词核验。没有证据时会返回 no_evidence，"
            "不会猜测真伪。"
        ),
    }


def dispatch(message) -> dict | None:
    """处理一条已解析的 JSON-RPC 消息；通知（无 id）返回 None。"""
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request：每一行必须是一个 JSON 对象")

    is_notification = "id" not in message
    request_id = message.get("id")
    method = message.get("method")

    if not isinstance(method, str) or not method:
        if is_notification:
            return None
        return _error(request_id, -32600, "Invalid Request：缺少 method 字段")

    if method == "initialize":
        return _result(request_id, _initialize_result())

    # notifications/initialized、notifications/cancelled 等一律静默（MCP 规范要求）
    if method.startswith("notifications/"):
        return None

    if method == "ping":
        return _result(request_id, {})

    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})

    if method == "tools/call":
        if is_notification:
            return None
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _error(request_id, -32602, "Invalid params：params 必须是对象")
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _error(request_id, -32602, "Invalid params：缺少工具名 name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "Invalid params：arguments 必须是对象")
        return _result(request_id, call_tool(name, arguments))

    if is_notification:
        return None
    return _error(request_id, -32601, f"Method not found：{method}")


def _write_message(message: dict) -> None:
    sys.stdout.write(_compact(message) + "\n")
    sys.stdout.flush()


def _configure_streams() -> None:
    # Windows 控制台默认可能是 GBK；协议规定 UTF-8，显式固定编码，
    # 避免中文 claim/理由在管道里被 mojibake 或抛 UnicodeEncodeError。
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - 某些宿主包装流不支持
            pass


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if any(arg in {"-h", "--help"} for arg in argv):
        sys.stdout.write(__doc__ or "")
        return 0
    if any(arg in {"-V", "--version"} for arg in argv):
        sys.stdout.write(f"{SERVER_NAME} {SERVER_VERSION}\n")
        return 0

    _configure_streams()
    _debug(
        f"{SERVER_NAME} {SERVER_VERSION} ready; protocol={PROTOCOL_VERSION}; "
        f"base_url={_base_url()}"
    )
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError as exc:
                _write_message(_error(None, -32700, f"Parse error：{exc}"))
                continue
            response = dispatch(message)
            if response is not None:
                _write_message(response)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
