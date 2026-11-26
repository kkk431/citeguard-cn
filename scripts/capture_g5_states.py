"""Capture G5: a 503 becomes a next-step message, never raw HTTP text."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "shots"
BASE = "http://127.0.0.1:8013"
BODY = {"detail": "HTTP 503 上游判官暂时不可用，请稍后重试"}

def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        for width, height in ((1440, 1000), (1280, 900)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/support/check", lambda route: route.fulfill(
                status=503, content_type="application/json", body=json.dumps(BODY)))
            page.goto(BASE + "/support", wait_until="networkidle")
            page.fill("#sp-claim", "该方法的准确率比基线高 2.3%。")
            page.fill("#sp-evidence", "Our approach improves accuracy by 2.1% over the baseline.")
            page.click("#sp-submit")
            page.wait_for_function("() => document.querySelector('#sp-empty').textContent.includes('核验失败')", timeout=10000)
            text = page.inner_text("#sp-result")
            assert "HTTP" not in text, text
            assert page.eval_on_selector("#sp-submit", "el => !el.disabled")
            shot = OUT / f"opt-G5-human-error-1.7.42-{width}.png"
            page.screenshot(path=str(shot), full_page=True)
            rows.append({"viewport": f"{width}x{height}", "shot": str(shot.relative_to(ROOT)),
                         "error_text": page.inner_text("#sp-empty"), "result_text": text})
            page.close()
        browser.close()
    data = {"date": str(date.today()), "base": BASE, "injected": BODY, "rows": rows,
            "assertion": "no raw HTTP in visible result"}
    path = ROOT / "data" / "experiments" / "opt_g5_states_2026-11-26.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data

if __name__ == "__main__":
    run()
