"""Capture the pages reviewers actually look at, at a fixed 1920x1080.

    python scripts/capture_evidence.py --base http://127.0.0.1:8013

Writes PNGs to ``docs/evidence/shots/captured/`` and prints one line per page
with its title, console error count and output path.  A non-zero exit means at
least one page failed to load or logged a console error, so this doubles as a
cheap visual regression sweep.

This is a capture helper, not a source of truth: it does not fabricate data.
Pages that need a job id (the report page) are skipped unless ``--job`` is
given; pages that require network data show whatever the running instance
really has.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCENES = [
    ("home", "/", "h1"),
    ("support", "/support", "h1"),
    ("library", "/library", "h1"),
    ("discover", "/discover", "h1"),
    ("compare", "/compare", "h1"),
    ("figure", "/figure", "h1"),
    ("batch", "/batch", "h1"),
    ("benchmark", "/benchmark", "h1"),
    ("history", "/history", "h1"),
    ("models", "/settings/models", "h1"),
    ("about", "/about", "h1"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8013")
    ap.add_argument("--out", default="docs/evidence/shots/captured")
    ap.add_argument("--job", help="also capture /report/<job>")
    ap.add_argument("--only", nargs="*", help="subset of scene names")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scenes = [(name, path, sel) for name, path, sel in SCENES
              if not args.only or name in args.only]
    if args.job:
        scenes.append(("report", f"/report/{args.job}", "#report-root[data-ready='1']"))

    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        for name, path, selector in scenes:
            errors.clear()
            try:
                page.goto(args.base.rstrip("/") + path, wait_until="networkidle", timeout=45000)
                page.wait_for_selector(selector, timeout=15000)
                target = out / f"{name}.png"
                page.screenshot(path=str(target), full_page=False)
                title = page.title()
                status = "OK" if not errors else f"CONSOLE {len(errors)}"
                print(f"{status:12} {name:10} {title[:40]:42} {target}")
                if errors:
                    failures.append(f"{name}: {errors[0][:120]}")
            except Exception as exc:  # noqa: BLE001 - report and continue
                failures.append(f"{name}: {exc}")
                print(f"FAIL         {name:10} {exc}")
        browser.close()

    if failures:
        print("\nfailures:")
        for failure in failures:
            print(" -", failure)
        return 1
    print(f"\n{len(scenes)} pages captured under {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
