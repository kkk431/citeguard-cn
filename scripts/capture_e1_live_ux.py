"""E1 Live 使用层截图：支持矩阵/三步/失败三动作。"""
import json
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013"
OUT = Path("docs/evidence/shots")
DATA = Path("data/experiments/opt_e1_live_ux_2026-11-26.json")


def snap(page, width):
    page.goto(BASE + "/live", wait_until="networkidle")
    page.wait_for_selector(".live-steps")
    page.screenshot(path=str(OUT / f"opt-E1-live-guide-1.7.45-{width}.png"), full_page=True)
    page.route("**/api/live/check", lambda route: route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": {"code": "judge_unavailable", "message": "上游判官暂时不可用"}})))
    page.fill("#live-claim", "这是一句用于测试失败动作的断言。")
    page.click("#live-btn")
    page.wait_for_selector("#live-error:not([hidden])", timeout=15000)
    page.screenshot(path=str(OUT / f"opt-E1-live-failure-actions-1.7.45-{width}.png"), full_page=True)
    return {"width": width, "error": page.inner_text("#live-error")}


def main():
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        for width, height in ((1440, 1000), (1280, 900)):
            page = browser.new_page(viewport={"width": width, "height": height})
            rows.append(snap(page, width))
            page.close()
        browser.close()
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({"date": str(date.today()), "rows": rows, "assertion": "support matrix + 3-step guide + 3 failure actions"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
