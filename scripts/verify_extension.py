#!/usr/bin/env python3
"""Verify the CiteGuard Live v2 browser extension in a real Chromium.

The script deliberately uses Playwright's persistent context with
``--load-extension`` (not a mocked extension API) and talks to the real local
service on ``http://127.0.0.1:8013``.  It checks four things:

1. Chromium loads ``extension/v2`` and starts its MV3 service worker.
2. The side panel UI can hand a selected sentence + page context to the local
   ``POST /api/live/check`` endpoint and render the returned label.
3. The same flow works from three real public pages, with the page URL/title
   preserved in the request payload.
4. A connection failure produces the panel's error state and a real screenshot.

The context-menu click itself is native browser UI and cannot be clicked by
Playwright.  The script reproduces the exact handoff that ``background.js``
performs: a ``citeguard-live-request`` runtime message plus the
``cg_live_request`` storage entry.  This boundary is documented in
``docs/extension_v2.md``; no screenshot is fabricated.

Usage (PowerShell, from the repository root)::

    $env:PYTHONIOENCODING = "utf-8"
    python scripts/verify_extension.py

The local service must already be running::

    $env:PYTHONPATH = "src"
    python -m uvicorn web.app:app --host 127.0.0.1 --port 8013
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTENSION = REPO_ROOT / "extension" / "v2"
DEFAULT_SHOTS_DIR = REPO_ROOT / "docs" / "evidence" / "shots"
DEFAULT_BASE_URL = "http://127.0.0.1:8013"
SHOT_PREFIX = "phase-54-extension-"
LIVE_LABELS = {"support", "partial", "contradict", "no_evidence"}

PUBLIC_CASES: list[dict[str, str]] = [
    {
        "slug": "example",
        "url": "https://example.com/",
        "title": "Example Domain",
    },
    {
        "slug": "iana-example-domains",
        "url": "https://www.iana.org/help/example-domains",
        "title": "Example Domains",
    },
    {
        "slug": "python-tutorial",
        "url": "https://docs.python.org/3/tutorial/index.html",
        "title": "The Python Tutorial",
    },
]


def _package_version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return ""


def _browser_roots() -> list[Path]:
    roots: list[Path] = []
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if configured:
        roots.append(Path(configured))
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        roots.append(Path(local_app_data) / "ms-playwright")
    roots.extend(
        [
            Path.home() / ".cache" / "ms-playwright",
            Path.home() / "Library" / "Caches" / "ms-playwright",
        ]
    )
    return roots


def find_chromium(extension_dir: Path) -> Path | None:
    """Return a real Chromium executable, preferring a Playwright build.

    ``PLAYWRIGHT_BROWSERS_PATH`` may point at an empty directory in this
    environment, so do not trust a single environment variable.
    """
    relative_names = (
        "chrome-win64/chrome.exe",
        "chrome-win/chrome.exe",
        "chrome-linux/chrome",
        "chrome-linux64/chrome",
        "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
    )
    for root in _browser_roots():
        if not root.is_dir():
            continue
        for folder in sorted(root.glob("chromium-*"), key=lambda item: item.name, reverse=True):
            for relative in relative_names:
                candidate = folder / relative
                if candidate.is_file():
                    return candidate
    for variable in ("CHROME_PATH", "CHROMIUM_PATH"):
        explicit = os.environ.get(variable, "").strip()
        if explicit and Path(explicit).is_file():
            return Path(explicit)
    if os.name == "nt":
        for base in (
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base:
                continue
            candidate = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if candidate.is_file():
                return candidate
    return None


def find_edge() -> Path | None:
    if os.name != "nt":
        return None
    for base in (
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ):
        if not base:
            continue
        candidate = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if candidate.is_file():
            return candidate
    return None


def executable_version(executable: Path) -> str:
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or result.stderr or "").strip().splitlines()[0] if (
        result.stdout or result.stderr
    ) else ""


def probe_server(base_url: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/live"
    try:
        with urlopen(url, timeout=10) as response:  # noqa: S310 - fixed local URL
            body = response.read(200_000)
        return {"ok": True, "url": url, "status": response.status, "bytes": len(body)}
    except Exception as exc:  # noqa: BLE001 - report the concrete failure
        return {"ok": False, "url": url, "error": f"{type(exc).__name__}: {exc}"}


def wait_for_worker(context: Any, timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for worker in context.service_workers:
            if worker.url.startswith("chrome-extension://"):
                return worker
        time.sleep(0.2)
    return None


def watch_console(page: Any, bucket: list[str], label: str) -> None:
    def on_console(message: Any) -> None:
        if message.type == "error":
            bucket.append(f"[{label}] console.error: {message.text}")

    def on_page_error(error: Any) -> None:
        bucket.append(f"[{label}] pageerror: {error}")

    page.on("console", on_console)
    page.on("pageerror", on_page_error)


def inject_selection(page: Any) -> dict[str, str] | None:
    """Select the first substantial paragraph and return its page context."""
    return page.evaluate(
        """() => {
          const paragraphs = Array.from(document.querySelectorAll("main p, article p, p"));
          const element = paragraphs.find((node) => {
            const text = (node.innerText || "").replace(/\\s+/g, " ").trim();
            return text.length >= 60 && node.getClientRects().length > 0;
          });
          if (!element) {
            return null;
          }
          element.scrollIntoView({block: "center"});
          const range = document.createRange();
          range.selectNodeContents(element);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          let claim = selection.toString().replace(/\\s+/g, " ").trim();
          if (claim.length > 300) {
            claim = claim.slice(0, 299).trim() + "…";
          }
          return {
            claim,
            page_url: location.href,
            page_title: document.title,
          };
        }"""
    )


def extension_card(page: Any, extension_id: str) -> dict[str, Any]:
    return page.evaluate(
        """(extId) => {
          const manager = document.querySelector("extensions-manager");
          const list = manager && manager.shadowRoot
            && manager.shadowRoot.querySelector("extensions-item-list");
          const listRoot = list && list.shadowRoot;
          const item = listRoot && (
            listRoot.querySelector('extensions-item[id="' + extId + '"]')
            || listRoot.querySelector("extensions-item")
          );
          if (!item) {
            return {found: false};
          }
          const root = item.shadowRoot;
          const name = root && root.querySelector("#name");
          const toggle = root && (root.querySelector("#enableToggle") || root.querySelector("#enable-toggle"));
          const errorButton = root && root.querySelector("#errors-button");
          return {
            found: true,
            name: name ? name.textContent.trim() : "",
            enabled: toggle ? Boolean(toggle.checked) : null,
            error_button_present: Boolean(errorButton),
            error_button_visible: errorButton ? !errorButton.hidden : false,
            text: (root ? root.textContent : "").replace(/\\s+/g, " ").trim().slice(0, 240),
          };
        }""",
        extension_id,
    )


def wait_for_extension_card(page: Any, extension_id: str, timeout: int = 20_000) -> None:
    page.wait_for_function(
        """(extId) => {
          const manager = document.querySelector("extensions-manager");
          const list = manager && manager.shadowRoot
            && manager.shadowRoot.querySelector("extensions-item-list");
          const listRoot = list && list.shadowRoot;
          return Boolean(
            listRoot && (
              listRoot.querySelector('extensions-item[id="' + extId + '"]')
              || listRoot.querySelector("extensions-item")
            )
          );
        }""",
        arg=extension_id,
        timeout=timeout,
    )


def make_request(case: str, claim: str, page_url: str, page_title: str) -> dict[str, str]:
    return {
        "id": f"verify-{case}-{int(time.time() * 1000)}",
        "claim": claim,
        "pageUrl": page_url,
        "pageTitle": page_title,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def trigger_request(
    worker: Any, request: dict[str, str], *, write_storage: bool = True
) -> dict[str, str]:
    """Mimic background.js: runtime message, then optional storage handoff.

    A real context-menu click cannot be automated; this is the same message
    payload and storage key that ``background.js`` produces.  The callback
    error is recorded for diagnostics; Chromium reports "The message port
    closed before a response was received" when a listener does not call
    sendResponse(), even though the panel did receive the message.
    """
    return worker.evaluate(
        """async (args) => {
          const {request, writeStorage} = args;
          const result = {callback_error: ""};
          await new Promise((resolve) => {
            let settled = false;
            const finish = (error) => {
              if (!settled) {
                settled = true;
                result.callback_error = error ? String(error.message || error) : "";
                resolve();
              }
            };
            try {
              chrome.runtime.sendMessage(
                {type: "citeguard-live-request", request},
                () => {
                  finish(chrome.runtime.lastError || "");
                }
              );
            } catch (error) {
              finish(error);
            }
            setTimeout(() => finish(""), 1500);
          });
          if (writeStorage) {
            await chrome.storage.local.set({cg_live_request: request});
          }
          return result;
        }""",
        {"request": request, "writeStorage": write_storage},
    )


def read_panel(panel: Any) -> dict[str, Any]:
    return panel.evaluate(
        """() => {
          const visible = (id) => {
            const node = document.getElementById(id);
            return node ? !node.hidden : false;
          };
          const badge = document.getElementById("label-badge");
          const error = document.getElementById("error-msg");
          return {
            state: visible("state-result")
              ? "result"
              : visible("state-error")
                ? "error"
                : visible("state-loading")
                  ? "loading"
                  : "idle",
            label_text: badge ? badge.textContent.trim() : "",
            label_class: badge ? badge.className : "",
            confidence: document.getElementById("confidence")
              ? document.getElementById("confidence").textContent.trim()
              : "",
            reason: document.getElementById("reason")
              ? document.getElementById("reason").textContent.trim()
              : "",
            error_message: error ? error.textContent.trim() : "",
            claim_value: document.getElementById("claim")
              ? document.getElementById("claim").value
              : "",
            endpoint: document.getElementById("endpoint-line")
              ? document.getElementById("endpoint-line").textContent.trim()
              : "",
          };
        }"""
    )


def run_api_case(
    *,
    panel: Any,
    worker: Any,
    request: dict[str, str],
    timeout_ms: int,
    screenshot: Path | None,
    write_storage: bool = True,
) -> dict[str, Any]:
    record: dict[str, Any] = {"request": request, "status": None, "payload": None, "response": None}
    try:
        with panel.expect_response(
            lambda response: "/api/live/check" in response.url
            and response.request.method == "POST",
            timeout=timeout_ms,
        ) as response_info:
            record["handoff"] = trigger_request(worker, request, write_storage=write_storage)
        response = response_info.value
        record["status"] = response.status
        record["request_url"] = response.url
        try:
            record["payload"] = response.request.post_data_json
        except Exception as exc:  # noqa: BLE001 - record malformed payloads
            record["payload_error"] = f"{type(exc).__name__}: {exc}"
        try:
            record["response"] = response.json()
        except Exception as exc:  # noqa: BLE001 - a non-JSON body is a finding
            record["response_error"] = f"{type(exc).__name__}: {exc}"
        panel.wait_for_function(
            """() => {
              const result = document.getElementById("state-result");
              const error = document.getElementById("state-error");
              return Boolean((result && !result.hidden) || (error && !error.hidden));
            }""",
            timeout=15_000,
        )
    except Exception as exc:  # noqa: BLE001 - the caller records a failed check
        record["exception"] = f"{type(exc).__name__}: {exc}"
    record["dom"] = read_panel(panel)
    if screenshot is not None:
        panel.screenshot(path=str(screenshot), full_page=True)
        record["screenshot"] = str(screenshot.relative_to(REPO_ROOT)).replace("\\", "/")
    return record


def check_api_record(record: dict[str, Any], *, label_required: bool = True) -> list[str]:
    problems: list[str] = []
    if record.get("exception"):
        problems.append(f"API 请求失败：{record['exception']}")
        return problems
    if record.get("status") != 200:
        problems.append(f"HTTP 状态不是 200：{record.get('status')!r}")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        problems.append("请求体不是 JSON 对象")
    else:
        request = record["request"]
        if payload.get("claim") != request["claim"]:
            problems.append("请求体 claim 与选区不一致")
        if payload.get("page_url") != request["pageUrl"]:
            problems.append("请求体 page_url 与页面 URL 不一致")
        if payload.get("page_title") != request["pageTitle"]:
            problems.append("请求体 page_title 与页面标题不一致")
        if not payload.get("page_url"):
            problems.append("请求体 page_url 为空")
        if not payload.get("page_title"):
            problems.append("请求体 page_title 为空")
    data = record.get("response")
    if not isinstance(data, dict):
        problems.append("响应体不是 JSON 对象")
        return problems
    if data.get("ok") is not True:
        problems.append(f"响应 ok 不是 true：{data.get('ok')!r}")
    label = data.get("label")
    if label_required and label not in LIVE_LABELS:
        problems.append(f"响应 label 非法：{label!r}")
    dom = record.get("dom") or {}
    if dom.get("state") != "result":
        problems.append(f"面板最终状态不是 result：{dom.get('state')!r}")
    if label and label not in str(dom.get("label_text", "")):
        problems.append("面板标签与 API label 不一致")
    if not dom.get("reason"):
        problems.append("面板没有渲染 reason")
    return problems


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extension",
        type=Path,
        default=DEFAULT_EXTENSION,
        help="unpacked extension directory (default: extension/v2)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="local CiteGuard service base URL (default: http://127.0.0.1:8013)",
    )
    parser.add_argument(
        "--shots-dir",
        type=Path,
        default=DEFAULT_SHOTS_DIR,
        help="screenshot output directory (default: docs/evidence/shots)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run Chromium headless (the default is headed so a human can watch)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    extension_dir = args.extension.resolve()
    shots_dir = args.shots_dir.resolve()
    base_url = args.base_url.rstrip("/")
    shots_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "ok": False,
        "task": "phase-54 CiteGuard Live v2 extension real-browser verification",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "playwright": _package_version("playwright"),
            "headless": bool(args.headless),
            "extension_dir": str(extension_dir),
            "server": base_url,
        },
        "extension": {},
        "local_live": {},
        "public_pages": [],
        "error_state": {},
        "screenshots": [],
        "console_errors": [],
        "checks": [],
        "failures": [],
        "limitations": [
            "右键菜单本身是 Chromium 原生 UI，Playwright 无法点击菜单项；本地用例用与 background.js 相同的 runtime 消息触发面板（不写 storage），公开网页用例用 runtime 消息 + cg_live_request storage handoff，未验证菜单项的实际点击。",
            "脚本使用 Playwright 自带 Chromium（本机未安装系统 Chrome），Edge 仅记录版本、未加载扩展测试。",
            "真实用户点击工具栏图标打开 side panel 的浏览器手势无法自动化；脚本在扩展页 sidepanel.html 中验证同一份 UI/JS。",
            "公开网页只覆盖 3 个稳定页面；不覆盖登录页、PDF、付费墙、CSP 限制页。",
            "本机服务未配置判定模型，标签与原因是本地规则/外部元数据摘要；不读取网页全文，不做事实核查。",
            "截图由 Playwright 直接截取，未拼接或美化；外部页面内容可能随时间变化。",
        ],
    }

    def check(name: str, condition: bool, detail: str = "") -> bool:
        passed = bool(condition)
        summary["checks"].append({"check": name, "ok": passed, "detail": detail})
        if not passed:
            summary["failures"].append(name if not detail else f"{name}：{detail}")
        return passed

    server = probe_server(base_url)
    summary["server"] = server
    if not server.get("ok"):
        summary["error"] = (
            "本地服务不可用，请先运行："
            " $env:PYTHONPATH=\"src\"; python -m uvicorn web.app:app --host 127.0.0.1 --port 8013"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    executable = find_chromium(extension_dir)
    summary["environment"]["chromium"] = str(executable) if executable else ""
    summary["environment"]["chromium_version"] = executable_version(executable) if executable else ""
    edge = find_edge()
    summary["environment"]["edge"] = str(edge) if edge else ""
    summary["environment"]["edge_version"] = executable_version(edge) if edge else ""
    if executable is None:
        summary["error"] = (
            "未找到 Playwright Chromium；请运行 python -m playwright install chromium，"
            "或设置 CHROME_PATH 指向 Chrome/Chromium 可执行文件。"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001 - report an actionable dependency error
        summary["error"] = f"无法导入 Playwright：{type(exc).__name__}: {exc}"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    profile_dir = Path(tempfile.mkdtemp(prefix="citeguard-ext-verify-"))
    context = None
    playwright = None
    try:
        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            executable_path=str(executable),
            headless=bool(args.headless),
            viewport={"width": 1440, "height": 960},
            args=[
                f"--disable-extensions-except={extension_dir}",
                f"--load-extension={extension_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate",
            ],
        )
        context.set_default_timeout(30_000)
        try:
            browser_version = context.browser.version if context.browser is not None else ""
        except Exception:  # noqa: BLE001 - version is diagnostic only
            browser_version = ""
        if browser_version:
            summary["environment"]["chromium_version"] = browser_version

        worker = wait_for_worker(context)
        check("MV3 service worker 启动", worker is not None, worker.url if worker else "30s 内未出现")
        if worker is None:
            raise RuntimeError("扩展 service worker 未启动")

        parsed_worker = urlparse(worker.url)
        extension_id = parsed_worker.netloc
        summary["extension"]["id"] = extension_id
        summary["extension"]["service_worker"] = worker.url
        summary["environment"]["extension_id"] = extension_id
        check("service worker 来自扩展", worker.url.endswith("/background.js"), worker.url)

        manifest = worker.evaluate("() => chrome.runtime.getManifest()")
        summary["extension"]["manifest"] = {
            key: manifest.get(key)
            for key in ("manifest_version", "name", "version", "minimum_chrome_version")
        }
        check("manifest_version 为 3", manifest.get("manifest_version") == 3)
        check("扩展版本为 0.2.0", manifest.get("version") == "0.2.0")
        check(
            "manifest 声明 side panel",
            (manifest.get("side_panel") or {}).get("default_path") == "sidepanel.html",
        )
        check(
            "host_permissions 只指向本地服务",
            all(
                urlparse(item).hostname in {"127.0.0.1", "localhost"}
                for item in (manifest.get("host_permissions") or [])
            ),
        )

        extensions_page = context.new_page()
        watch_console(extensions_page, summary["console_errors"], "chrome://extensions")
        extensions_page.goto("chrome://extensions/", wait_until="domcontentloaded")
        wait_for_extension_card(extensions_page, extension_id)
        card = extension_card(extensions_page, extension_id)
        summary["extension"]["card"] = card
        loaded_shot = shots_dir / f"{SHOT_PREFIX}loaded.png"
        extensions_page.screenshot(path=str(loaded_shot), full_page=True)
        summary["screenshots"].append(
            {
                "path": str(loaded_shot.relative_to(REPO_ROOT)).replace("\\", "/"),
                "what": "chrome://extensions 中已加载的 CiteGuard Live v2 卡片",
            }
        )
        check("chrome://extensions 显示扩展卡片", card.get("found") is True, str(card))
        if card.get("enabled") is not None:
            check("扩展处于启用状态", card.get("enabled") is True)
        check(
            "扩展卡片没有错误按钮",
            card.get("error_button_visible") is not True,
            str(card.get("error_button_present")),
        )

        panel = context.new_page()
        watch_console(panel, summary["console_errors"], "sidepanel")
        panel.goto(f"chrome-extension://{extension_id}/sidepanel.html", wait_until="domcontentloaded")
        panel.wait_for_selector("#check-btn", state="visible")
        panel.wait_for_timeout(600)

        local_page = context.new_page()
        watch_console(local_page, summary["console_errors"], "/live")
        local_response = local_page.goto(base_url + "/live", wait_until="domcontentloaded", timeout=45_000)
        check("本地 /live 页面可打开", local_response is not None and local_response.status == 200,
              f"status={getattr(local_response, 'status', None)}")
        selection = inject_selection(local_page)
        check("本地 /live 页面能选中文字", bool(selection and selection.get("claim")),
              str(selection.get("claim", "")[:40]) if selection else "未找到段落")
        if not selection:
            raise RuntimeError("/live 页面没有可选择的段落")
        local_page.bring_to_front()
        local_page.wait_for_timeout(300)
        local_shot = shots_dir / f"{SHOT_PREFIX}local-live.png"
        local_page.screenshot(path=str(local_shot), full_page=False)
        summary["screenshots"].append(
            {
                "path": str(local_shot.relative_to(REPO_ROOT)).replace("\\", "/"),
                "what": "本地 /live 页面，脚本已选中段落（真实 Chromium 截图）",
            }
        )
        summary["local_live"]["page"] = {
            "url": selection["page_url"],
            "title": selection["page_title"],
            "claim": selection["claim"],
        }

        local_request = make_request(
            "local", selection["claim"], selection["page_url"], selection["page_title"]
        )
        local_record = run_api_case(
            panel=panel,
            worker=worker,
            request=local_request,
            timeout_ms=120_000,
            screenshot=shots_dir / f"{SHOT_PREFIX}live-result.png",
            write_storage=False,
        )
        # 本地用例只走 runtime 消息，证明消息通道本身可用；随后补写 storage，
        # 让面板持久化与真实 background.js 行为一致。
        try:
            worker.evaluate(
                "(req) => chrome.storage.local.set({cg_live_request: req})",
                local_request,
            )
        except Exception as exc:  # noqa: BLE001 - persistence is not required for the API check
            summary["local_live"]["storage_error"] = f"{type(exc).__name__}: {exc}"
        summary["local_live"]["api"] = local_record
        summary["local_live"]["message_only"] = True
        if local_record.get("screenshot"):
            summary["screenshots"].append(
                {
                    "path": local_record["screenshot"],
                    "what": "侧边栏显示真实 /api/live/check 结果与来源证据",
                }
            )
        local_problems = check_api_record(local_record)
        if local_problems:
            for problem in local_problems:
                check("本地 /live API 检查", False, problem)
        else:
            check("本地 /live API 检查", True, f"label={local_record.get('response', {}).get('label')}")
            check(
                "本地用例仅靠 runtime 消息触发真实 API",
                local_record.get("status") == 200
                and (local_record.get("payload") or {}).get("claim") == local_request["claim"],
                "未写 cg_live_request storage，排除了 storage 回退路径",
            )

        for case in PUBLIC_CASES:
            page = context.new_page()
            watch_console(page, summary["console_errors"], case["slug"])
            public_record: dict[str, Any] = {"case": case, "page": {}, "api": None}
            try:
                response = page.goto(case["url"], wait_until="domcontentloaded", timeout=60_000)
                public_record["page"]["status"] = getattr(response, "status", None)
                check(
                    f"{case['slug']} 页面可打开",
                    response is not None and response.status == 200,
                    f"status={getattr(response, 'status', None)}",
                )
                page.wait_for_timeout(400)
                public_selection = inject_selection(page)
                if not public_selection:
                    raise RuntimeError("页面没有可选择的段落")
                public_selection["page_title"] = public_selection["page_title"] or page.title()
                page.bring_to_front()
                page.wait_for_timeout(300)
                shot = shots_dir / f"{SHOT_PREFIX}{case['slug']}.png"
                page.screenshot(path=str(shot), full_page=False)
                summary["screenshots"].append(
                    {
                        "path": str(shot.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "what": f"{case['url']} 上的真实选区",
                    }
                )
                public_record["page"].update(public_selection)
                public_record["page"]["final_url"] = page.url
                public_record["page"]["title"] = public_selection["page_title"]
                public_record["page"]["screenshot"] = str(shot.relative_to(REPO_ROOT)).replace("\\", "/")
                request = make_request(
                    case["slug"],
                    public_selection["claim"],
                    page.url,
                    public_selection["page_title"],
                )
                api_record = run_api_case(
                    panel=panel,
                    worker=worker,
                    request=request,
                    timeout_ms=180_000,
                    screenshot=None,
                )
                public_record["api"] = api_record
                problems = check_api_record(api_record)
                if problems:
                    for problem in problems:
                        check(f"{case['slug']} 真实 API 检查", False, problem)
                else:
                    check(
                        f"{case['slug']} 真实 API 检查",
                        True,
                        f"label={api_record.get('response', {}).get('label')}",
                    )
                    if not str(api_record.get("payload", {}).get("page_url", "")).startswith(
                        ("http://", "https://")
                    ):
                        check(f"{case['slug']} page_url 是真实 URL", False)
            except Exception as exc:  # noqa: BLE001 - one page failure must not hide others
                public_record["error"] = f"{type(exc).__name__}: {exc}"
                check(f"{case['slug']} 真实 API 检查", False, public_record["error"])
            finally:
                page.close()
            summary["public_pages"].append(public_record)

        public_ok = sum(
            1
            for item in summary["public_pages"]
            if item.get("api") and not check_api_record(item["api"])
        )
        check("至少 3 个真实公开网页完成 API 核验", public_ok >= 3, f"成功 {public_ok} 个")

        panel.evaluate(
            """async (base) => {
              await chrome.storage.local.set({cg_live_endpoint: "http://127.0.0.1:9"});
              await chrome.storage.local.set({
                cg_live_request: {
                  id: "verify-error-" + Date.now(),
                  claim: "这是一条用于验证错误处理的句子。",
                  pageUrl: base + "/live",
                  pageTitle: "错误处理验证",
                  createdAt: new Date().toISOString(),
                },
              });
            }""",
            base_url,
        )
        try:
            panel.wait_for_function(
                "() => { const node = document.getElementById('state-error'); return node && !node.hidden; }",
                timeout=30_000,
            )
            error_dom = read_panel(panel)
            error_shot = shots_dir / f"{SHOT_PREFIX}error.png"
            panel.screenshot(path=str(error_shot), full_page=True)
            summary["screenshots"].append(
                {
                    "path": str(error_shot.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "what": "侧边栏在本地服务不可达时的真实错误状态",
                }
            )
            summary["error_state"] = {
                "state": error_dom.get("state"),
                "message": error_dom.get("error_message"),
                "screenshot": str(error_shot.relative_to(REPO_ROOT)).replace("\\", "/"),
            }
            check("连接失败时进入错误状态", error_dom.get("state") == "error")
            check(
                "错误状态有中文提示",
                "无法连接本地服务" in str(error_dom.get("error_message", ""))
                or "请求超时" in str(error_dom.get("error_message", "")),
                str(error_dom.get("error_message")),
            )
        except Exception as exc:  # noqa: BLE001 - error handling is part of the contract
            summary["error_state"] = {"exception": f"{type(exc).__name__}: {exc}"}
            check("连接失败时进入错误状态", False, str(exc))
        finally:
            try:
                panel.evaluate(
                    """async (base) => {
                      await chrome.storage.local.set({cg_live_endpoint: base});
                      await chrome.storage.local.remove("cg_live_request");
                    }""",
                    base_url,
                )
            except Exception:  # noqa: BLE001 - cleanup is best-effort
                pass

        summary["screenshots"] = [
            item for item in summary["screenshots"] if (REPO_ROOT / item["path"]).is_file()
        ]
        check("截图文件全部存在", len(summary["screenshots"]) >= 5, f"{len(summary['screenshots'])} 张")
        summary["ok"] = not summary["failures"]
    except Exception as exc:  # noqa: BLE001 - always emit a machine-readable result
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["ok"] = False
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:  # noqa: BLE001 - shutdown is best-effort
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:  # noqa: BLE001 - shutdown is best-effort
                pass
        shutil.rmtree(profile_dir, ignore_errors=True)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
