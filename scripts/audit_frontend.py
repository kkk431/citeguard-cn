"""Keyboard/accessibility audit for the desktop web app (1280x800)."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"


def main() -> int:
    jobs = json.load(urllib.request.urlopen(BASE + "/api/jobs?limit=20"))["jobs"]
    report_id = next((j["id"] for j in jobs if j.get("has_report")), None)
    out: dict = {"base": BASE, "report_job": report_id, "checks": []}

    def ck(name: str, ok: bool, detail: object = "") -> None:
        out["checks"].append({"name": name, "ok": bool(ok), "detail": detail})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1.5)
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        ck("home_no_horizontal_overflow_1280",
           page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"))
        ck("home_has_aria_live", page.locator("[aria-live]").count() > 0)
        unnamed = page.evaluate("""() => [...document.querySelectorAll('button,a[href]')]
          .filter(e => !(e.innerText || e.getAttribute('aria-label') || e.title || '').trim()).length""")
        ck("home_all_controls_named", unnamed == 0, unnamed)
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        ck("palette_opens_ctrl_k", page.evaluate("""() => { const e = document.querySelector('#palette');
          return !!e && !e.hasAttribute('hidden'); }"""))
        page.keyboard.press("Escape")

        page.goto(f"{BASE}/report/{report_id}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.keyboard.press("j")
        page.wait_for_timeout(400)
        ck("report_j_focuses_first_row", "ref" in page.evaluate("document.activeElement.className"))
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)
        ck("report_enter_opens_drawer", page.evaluate("""() => { const d = document.getElementById('ref-drawer');
          return !!d && !d.hasAttribute('hidden'); }"""))
        page.screenshot(path="docs/evidence/shots/phase-26-keyboard-a11y-1.0.2.png")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        ck("report_esc_closes_drawer", page.evaluate("""() => { const d = document.getElementById('ref-drawer');
          return !d || d.hasAttribute('hidden'); }"""))
        page.keyboard.press("/")
        page.wait_for_timeout(250)
        ck("report_slash_focuses_search", page.evaluate("document.activeElement.id === 'search'"))
        browser.close()

    target = Path("data/experiments/frontend_audit.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [c for c in out["checks"] if not c["ok"]]
    for c in out["checks"]:
        print(("PASS " if c["ok"] else "FAIL "), c["name"], c["detail"])
    print(f"{len(out['checks']) - len(failed)}/{len(out['checks'])} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
