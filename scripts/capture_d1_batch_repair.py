"""D1: select several references, batch preview/apply, then recheck and undo."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "shots"
JOB = "d73ae2dcd2e9"
BASE = "http://127.0.0.1:8013"


def run() -> dict:
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        for width, height in ((1440, 1000), (1280, 900)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"{BASE}/report/{JOB}", wait_until="networkidle")
            page.wait_for_selector("#report-root[data-ready='1']", timeout=30000)
            page.click('[data-summary-tab="refs"]')
            page.wait_for_selector("#ref-list .ref")
            boxes = page.locator("#ref-list .ref-select")
            boxes.nth(0).check()
            boxes.nth(1).check()
            count = page.inner_text("#repair-selected-count")
            assert count == "2", count
            assert page.is_enabled("#btn-repair-selected")
            page.screenshot(path=str(OUT / f"opt-D1-batch-select-1.7.44-{width}.png"), full_page=True)

            page.click("#btn-repair-selected")
            page.wait_for_selector("#repair-modal:not([hidden])", timeout=15000)
            meta = page.inner_text("#repair-meta")
            page.screenshot(path=str(OUT / f"opt-D1-batch-preview-1.7.44-{width}.png"), full_page=True)
            page.click("#repair-apply")
            page.wait_for_selector("#btn-repair-verify:not([hidden])", timeout=30000)
            page.click("#btn-repair-verify")
            page.wait_for_selector("#repair-verify:not(.hidden)", timeout=30000)
            verify = page.inner_text("#repair-verify")
            assert "修复后复检" in verify or "复检" in verify
            page.screenshot(path=str(OUT / f"opt-D1-verify-1.7.44-{width}.png"), full_page=True)

            page.click("#btn-undo-repair")
            page.wait_for_selector("#btn-repair-all:not([hidden])", timeout=30000)
            rows.append({"viewport": f"{width}x{height}", "selected": count, "preview_meta": meta,
                         "verify": verify, "undone": True})
            page.close()
        browser.close()
    data = {"date": str(date.today()), "job": JOB, "base": BASE, "rows": rows,
            "assertion": "select 2 -> batch preview -> apply -> verify -> undo; no fake result"}
    (ROOT / "data" / "experiments" / "opt_d1_batch_repair_2026-11-26.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


if __name__ == "__main__":
    run()

