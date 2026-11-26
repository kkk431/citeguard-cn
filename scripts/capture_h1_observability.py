"""H1 证据：请求头/health/metrics + 真实浏览器截图。"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8013"
OUT = Path("docs/evidence/shots")
DATA = Path("data/experiments/opt_h1_observability_2026-11-26.json")


def main():
    health = requests.get(f"{BASE}/api/health", headers={"X-Request-ID": "h1-evidence-health"}, timeout=10)
    metrics = requests.get(f"{BASE}/api/metrics", headers={"X-Request-ID": "h1-evidence-metrics"}, timeout=10)
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        for width, height in ((1440, 900), (1280, 800)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"{BASE}/api/metrics", wait_until="networkidle")
            page.screenshot(path=str(OUT / f"opt-H1-metrics-1.7.47-{width}.png"), full_page=True)
            rows.append({"width": width, "text": page.inner_text("body")[:600]})
            page.close()
        browser.close()
    DATA.write_text(json.dumps({
        "date": datetime.now(timezone.utc).isoformat(),
        "health_status": health.status_code,
        "health_request_id": health.headers.get("x-request-id"),
        "health_latency_ms": health.headers.get("x-response-time-ms"),
        "health": health.json(),
        "metrics_status": metrics.status_code,
        "metrics_request_id": metrics.headers.get("x-request-id"),
        "metrics": metrics.json(),
        "screens": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"health": health.json(), "metrics": metrics.json(), "screens": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
