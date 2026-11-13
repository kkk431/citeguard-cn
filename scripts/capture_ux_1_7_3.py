"""Capture the 1.7.3 pager and report-checks drawer for evidence.

Run with the demo server on 127.0.0.1:8013:
    PLAYWRIGHT_BROWSERS_PATH=%LOCALAPPDATA%\\ms-playwright \
      python scripts/capture_ux_1_7_3.py
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013"
OUT = Path("docs/evidence/shots")
JOB = "96511af51c97"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)

        page.goto(BASE + "/history", wait_until="networkidle")
        page.wait_for_selector("#history-pager .pager-btn")
        # [prev, 1, 2, next] -> the third button is page 2
        page.locator("#history-pager .pager-btn").nth(2).click()
        page.wait_for_timeout(250)
        page.screenshot(path=str(OUT / "phase-47-history-pager-1.7.3.png"))

        page.goto(BASE + "/library", wait_until="networkidle")
        page.wait_for_selector("#library-pager .pager-btn")
        page.screenshot(path=str(OUT / "phase-47-library-pager-1.7.3.png"))

        page.goto(BASE + f"/report/{JOB}", wait_until="networkidle")
        page.wait_for_selector("#report-root[data-ready='1']")
        page.click("#open-checks")
        page.wait_for_selector("#checks-drawer:not([hidden])")
        page.wait_for_timeout(350)
        page.screenshot(path=str(OUT / "phase-47-report-checks-1.7.3.png"))

        charts_tab = page.locator('.checks-tab[data-checks-tab="charts"]:not([hidden])')
        if charts_tab.count():
            charts_tab.first.click()
            page.wait_for_timeout(450)
            page.screenshot(path=str(OUT / "phase-47-report-checks-charts-1.7.3.png"))

        browser.close()


if __name__ == "__main__":
    main()
