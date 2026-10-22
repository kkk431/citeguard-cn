"""Smoke-test the running web app (local or server)."""
import json
import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def main() -> None:
    print("health:", requests.get(BASE + "/api/health", timeout=10).json())
    text = open("web/static/samples/sample_paper.txt", encoding="utf-8").read()
    resp = requests.post(BASE + "/api/analyze", data={"text": text}, timeout=30)
    print("analyze:", resp.status_code, resp.text[:120])
    job_id = resp.json()["job_id"]
    for _ in range(80):
        job = requests.get(f"{BASE}/api/jobs/{job_id}", timeout=10).json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(3)
    print("job:", job["status"], job.get("error", ""))
    if job["status"] != "done":
        return
    report = requests.get(f"{BASE}/api/report/{job_id}", timeout=20).json()
    print("stats:", json.dumps(report["stats"], ensure_ascii=False))
    for path in ["/", f"/report/{job_id}", "/benchmark", "/about", "/static/css/app.css"]:
        r = requests.get(BASE + path, timeout=15)
        print(f"{path}: {r.status_code} ({len(r.content)} bytes)")


if __name__ == "__main__":
    main()
