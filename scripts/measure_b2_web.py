"""Measure the B2 result cache through the real web /api/analyze path."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8013"
PDF = Path("data/real_corpus/hanspub_152575.pdf")


def one() -> dict:
    started = time.perf_counter()
    with PDF.open("rb") as fh:
        r = requests.post(
            BASE + "/api/analyze",
            files={"file": (PDF.name, fh, "application/pdf")},
            data={"support_max": "0", "figures": "false"},
            timeout=60,
        )
    r.raise_for_status()
    job = r.json()["job_id"]
    while True:
        s = requests.get(BASE + f"/api/jobs/{job}", timeout=10).json()
        if s.get("status") in {"done", "error", "cancelled"}:
            break
        time.sleep(0.2)
    elapsed = time.perf_counter() - started
    rep = requests.get(BASE + f"/api/report/{job}", timeout=10)
    body = rep.json() if rep.ok else {}
    return {
        "job_id": job,
        "status": s.get("status"),
        "elapsed_seconds": round(elapsed, 3),
        "references": len(body.get("references") or []),
        "cache": body.get("cache", {}).get("status"),
        "cache_key": (body.get("cache") or {}).get("key"),
        "input": body.get("input"),
    }


first = one()
second = one()
out = {"pdf": str(PDF), "pdf_sha256_size": PDF.stat().st_size, "runs": [first, second],
       "cold_seconds": first["elapsed_seconds"], "hot_seconds": second["elapsed_seconds"]}
Path("data/experiments").mkdir(exist_ok=True)
Path("data/experiments/opt_b2_web_2026-11-27.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(out, ensure_ascii=False, indent=2))
