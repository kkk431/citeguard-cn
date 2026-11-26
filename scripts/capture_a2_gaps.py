"""Capture the A2 coverage-gap dashboard (real UI, real local library)."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013"
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
            page.click("#library-gaps-btn")
            page.wait_for_function(
                "() => { const el=document.querySelector('#library-gaps-modal');"
                " return el && !el.hidden && document.querySelectorAll('#gaps-body tr').length >= 2; }",
                timeout=15000,
            )
            page.wait_for_timeout(300)
            summary = page.locator("#gaps-body > p").first.inner_text()
            table = page.locator("#gaps-body table").inner_text()
            rows = page.locator(".lib-gap-row").count()
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            csv = page.evaluate(
                "async () => { const r = await fetch('/api/library/gaps.csv');"
                " return {status: r.status, type: r.headers.get('content-type'), text: (await r.text()).slice(0, 80)}; }"
            )
            path = SHOTS / f"opt-A2-library-gaps-1.7.38-{width}.png"
            page.screenshot(path=str(path), full_page=False)
            results.append(
                {
                    "width": width,
                    "height": height,
                    "summary": summary,
                    "language_table": table,
                    "sample_rows": rows,
                    "csv": csv,
                    "horizontal_overflow": overflow,
                    "console_errors": errors,
                    "screenshot": str(path),
                }
            )
            page.close()
        browser.close()
    out = Path("data/experiments/opt_a2_library_gaps_ui_2026-11-26.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
