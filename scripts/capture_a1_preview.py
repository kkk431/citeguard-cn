"""Capture the A1 library import preview at desktop widths (real UI, no mocking)."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013"
RIS = Path("samples/a1_preview_demo.ris").resolve()
SHOTS = Path("docs/evidence/shots")
SHOTS.mkdir(parents=True, exist_ok=True)


def main() -> None:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        for width, height in ((1440, 1000), (1280, 900)):
            page = browser.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.goto(BASE + "/library", wait_until="domcontentloaded")
            page.set_input_files("#library-file", str(RIS))
            page.wait_for_function(
                "() => { const el=document.querySelector('#library-preview');"
                " return el && !el.hidden && !document.querySelector('#library-preview-summary').textContent.includes('正在'); }",
                timeout=15000,
            )
            page.wait_for_timeout(300)
            page.evaluate(
                "() => { const el=document.getElementById('library-form');"
                " window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 90); }"
            )
            page.wait_for_timeout(200)
            summary = page.locator("#library-preview-summary").inner_text()
            stats = page.locator("#library-preview-stats").inner_text()
            gaps = page.locator("#library-preview-gaps").inner_text()
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            path = SHOTS / f"opt-A1-library-import-preview-1.7.36-{width}.png"
            page.screenshot(path=str(path), full_page=False)
            results.append(
                {
                    "width": width,
                    "height": height,
                    "summary": summary,
                    "stats": stats,
                    "gaps": gaps,
                    "horizontal_overflow": overflow,
                    "console_errors": errors,
                    "screenshot": str(path),
                }
            )
            page.close()
        browser.close()
    out = Path("data/experiments/opt_a1_import_preview_ui_2026-11-26.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
