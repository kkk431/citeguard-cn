"""Capture B1: history page while a real analysis job is running."""
from __future__ import annotations
import json
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013"
PDF = Path("data/real_corpus/arxiv/1810.04805v2.pdf")
OUT = Path("docs/evidence/shots")
DATA = Path("data/experiments/opt_b1_resume_2026-11-26.json")

with PDF.open("rb") as fh:
    resp = requests.post(
        BASE + "/api/analyze",
        files={"file": (PDF.name, fh, "application/pdf")},
        data={"support_max": "30", "figures": "0"},
        timeout=30,
    )
resp.raise_for_status()
job_id = resp.json()["job_id"]
started = time.time()

shots = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    for width, height in ((1440, 1000), (1280, 900)):
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        page.goto(BASE + "/history?all=1", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#history-live:not([hidden])", timeout=8000)
        path = OUT / f"opt-B1-history-live-1.7.39-{width}.png"
        page.screenshot(path=str(path), full_page=False)
        shots.append(str(path))
        page.close()
    browser.close()

state = requests.get(BASE + f"/api/jobs/{job_id}", timeout=10).json()
payload = {
    "feature": "B1 long-job progress and resume",
    "version": "1.7.39",
    "job_id": job_id,
    "job_status": state.get("status"),
    "progress": state.get("progress"),
    "next_action": state.get("next_action"),
    "retryable": state.get("retryable"),
    "screenshots": shots,
    "captured_after_seconds": round(time.time() - started, 2),
    "note": "真实任务运行中截取；离开页面任务仍在后台继续。",
}
DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))

