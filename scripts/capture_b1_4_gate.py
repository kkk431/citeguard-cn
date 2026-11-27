"""Capture the CiteMap high-confidence gate at 1440 and 1280."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013/citemap?topic=ai_education"
OUT = Path("docs/evidence/shots")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for width in (1440, 1280):
            page = browser.new_page(viewport={"width": width, "height": 1000}, device_scale_factor=1)
            page.goto(BASE, wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#ctm-graph-toggle') !== null")
            page.evaluate("document.querySelector('#ctm-graph-toggle').click()")
            page.wait_for_function("document.querySelectorAll('#ctm-graph-svg path').length > 0", timeout=20000)
            page.wait_for_timeout(500)
            before = page.evaluate("document.querySelector('#ctm-graph-summary').textContent")
            page.evaluate("document.querySelector('#ctm-gate-high').click()")
            page.wait_for_timeout(600)
            after = page.evaluate("document.querySelector('#ctm-graph-summary').textContent")
            path = OUT / f"opt-B1.4-citemap-gate-1.7.51-{width}.png"
            page.screenshot(path=str(path), full_page=False)
            print(width, path, before.strip(), "=>", after.strip())
            page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
