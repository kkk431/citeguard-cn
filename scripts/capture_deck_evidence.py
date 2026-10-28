"""Capture the evidence drawer for deck page 06 (entry [2])."""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("out/shots")
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8010/report/226077f3736d"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True, args=["--disable-gpu", "--hide-scrollbars"])
    page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(700)
    page.locator("[data-summary-tab='refs']").click()
    page.wait_for_timeout(400)
    page.locator(".ref").nth(1).click()
    page.wait_for_timeout(600)
    drawer = page.locator("#ref-drawer")
    drawer.screenshot(path=str(OUT / "deck_evidence_entry2.png"))
    browser.close()
print("saved", (OUT / "deck_evidence_entry2.png").stat().st_size)
