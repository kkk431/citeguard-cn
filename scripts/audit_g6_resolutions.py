"""G6: responsive/accessibility smoke at 1280, 1440 and 1920 widths."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8013"
OUT = Path("docs/evidence/shots")
OUT.mkdir(parents=True, exist_ok=True)
PAGES = [
    ("/workspace", "workspace"),
    ("/library", "library"),
    ("/figure", "figure"),
    ("/live", "live"),
    ("/citemap", "citemap"),
    ("/benchmark", "benchmark"),
]
WIDTHS = [("1280", 1280, 800), ("1440", 1440, 900), ("1920", 1920, 1080)]


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        checks: list[dict] = []
        for label, width, height in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": height})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            for path, name in PAGES:
                errors.clear()
                page.goto(BASE + path, wait_until="domcontentloaded")
                page.wait_for_timeout(500)
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
                )
                unnamed = page.evaluate(
                    """() => [...document.querySelectorAll('button,a[href]')]
                      .filter(e => e.getClientRects().length > 0)
                      .filter(e => !((e.getAttribute('aria-label') || e.title || e.innerText || '').trim())).length"""
                )
                checks.append(
                    {
                        "width": label,
                        "page": name,
                        "no_horizontal_overflow": not overflow,
                        "all_controls_named": unnamed == 0,
                        "no_console_errors": not errors,
                    }
                )
                if name in ("workspace", "library") and label in ("1440", "1920"):
                    page.screenshot(path=str(OUT / f"opt-G6-{name}-{label}.png"), full_page=False)
            page.close()
        browser.close()
    data = {
        "base": BASE,
        "viewports": [w[0] for w in WIDTHS],
        "checks": checks,
        "passed": all(
            c["no_horizontal_overflow"] and c["all_controls_named"] and c["no_console_errors"]
            for c in checks
        ),
        "count": len(checks),
    }
    Path("data/experiments").mkdir(parents=True, exist_ok=True)
    Path("data/experiments/opt_g6_resolutions_2026-11-27.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    failed = [c for c in checks if not (c["no_horizontal_overflow"] and c["all_controls_named"] and c["no_console_errors"])]
    print(json.dumps({"passed": data["passed"], "checks": len(checks), "failed": failed[:5]}, ensure_ascii=False))
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
