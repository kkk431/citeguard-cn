"""C1: figure preflight shows service state, and a failed call keeps input + offers retry."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "shots"
BASE = "http://127.0.0.1:8013"
IMG = ROOT / "out" / "figtest_real" / "images" / "hanspub_152575_p3_1.png"
BODY = {"ok": False, "error": "HTTP 502 视觉模型暂时不可用，请稍后重试"}


def run() -> dict:
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        for width, height in ((1440, 1000), (1280, 900)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(BASE + "/figure", wait_until="networkidle")
            status = page.locator("#figure-service-status").inner_text()
            assert "视觉模型已就绪" in status, status
            page.screenshot(path=str(OUT / f"opt-C1-figure-ready-1.7.43-{width}.png"), full_page=True)

            page.route("**/api/figure-check", lambda route: route.fulfill(
                status=502, content_type="application/json", body=json.dumps(BODY, ensure_ascii=False)))
            page.set_input_files("#figure-file", str(IMG))
            page.fill("#figure-claim", "图中 2025 年的发文量最高，为 195 篇。")
            page.click("#figure-check-btn")
            page.wait_for_selector("#figure-retry", timeout=15000)
            text = page.inner_text("#figure-result")
            assert "HTTP" not in text, text
            assert page.input_value("#figure-claim").startswith("图中 2025")
            page.screenshot(path=str(OUT / f"opt-C1-figure-retry-1.7.43-{width}.png"), full_page=True)
            rows.append({"viewport": f"{width}x{height}", "status": status,
                         "error_text": text, "claim_kept": page.input_value("#figure-claim")})
            page.close()
        browser.close()
    data = {"date": str(date.today()), "base": BASE, "injected": BODY, "rows": rows,
            "assertion": "status visible; input kept; retry offered; no raw HTTP"}
    (ROOT / "data" / "experiments" / "opt_c1_figure_states_2026-11-26.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


if __name__ == "__main__":
    run()
