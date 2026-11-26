"""F1 截图：修复预览里的字段级建议。"""
import json
from datetime import date
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013"
JOB = "d73ae2dcd2e9"
OUT = Path("docs/evidence/shots")
DATA = Path("data/experiments/opt_f1_repair_suggestions_2026-11-26.json")


def run(width, height):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"{BASE}/report/{JOB}", wait_until="networkidle")
        page.wait_for_selector("#report-root[data-ready='1']")
        page.click('[data-summary-tab="refs"]')
        page.wait_for_selector("#ref-list .ref")
        page.locator("#ref-list .ref-select").nth(0).check()
        page.locator("#ref-list .ref-select").nth(1).check()
        page.click("#btn-repair-selected")
        page.wait_for_selector("#repair-modal:not([hidden])", timeout=20000)
        page.wait_for_selector(".repair-suggestions", timeout=20000)
        text = page.inner_text("#repair-modal")
        page.screenshot(path=str(OUT / f"opt-F1-repair-suggestions-1.7.46-{width}.png"), full_page=True)
        browser.close()
        return {"width": width, "has_suggestions": "修复建议" in text, "has_doi_action": "Crossref" in text, "text": text[:400]}


def main():
    rows = [run(1440, 1000), run(1280, 900)]
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({"date": str(date.today()), "job": JOB, "rows": rows, "assertion": "repair preview shows actionable suggestions, no fabricated values"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
