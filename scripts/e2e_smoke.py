"""End-to-end smoke test against a running CiteGuard-CN instance.

Covers: health -> upload -> job -> report -> annotated PDF -> exports
(RIS/EndNote/BibTeX/CSL/reference text) -> evidence bundle -> diff.

Usage:
  python scripts/e2e_smoke.py --base http://127.0.0.1:8013 \
      --pdf data/real_corpus/hanspub_152575.pdf --out data/experiments/e2e_smoke.json

Requires `requests` (already a web dependency).
"""
from __future__ import annotations

import argparse
import json
import time
import zipfile
from io import BytesIO
from pathlib import Path

import requests

TIMEOUT = 240


def poll(base: str, job_id: str, timeout: int = TIMEOUT) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = requests.get(f"{base}/api/jobs/{job_id}", timeout=15).json()
        if data.get("status") in ("done", "error", "cancelled"):
            return data
        time.sleep(2)
    raise TimeoutError(f"job {job_id} did not finish in {timeout}s")


def analyze(base: str, pdf: Path) -> str:
    with pdf.open("rb") as fh:
        resp = requests.post(
            f"{base}/api/analyze",
            files={"file": (pdf.name, fh, "application/pdf")},
            data={"support_max": "0", "figures": "0"},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()["job_id"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8013")
    ap.add_argument("--pdf", default="data/real_corpus/hanspub_152575.pdf")
    ap.add_argument("--out", default="data/experiments/e2e_smoke.json")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    pdf = Path(args.pdf)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail=None) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    health = requests.get(f"{base}/api/health", timeout=15).json()
    check("health", health.get("ok") is True, {"version": health.get("version")})

    job_id = analyze(base, pdf)
    job = poll(base, job_id)
    check("job_done", job.get("status") == "done", {"job": job_id, "status": job.get("status")})
    if job.get("status") != "done":
        Path(args.out).write_text(json.dumps({"checks": checks}, ensure_ascii=False, indent=1), encoding="utf-8")
        return 1

    report = requests.get(f"{base}/api/report/{job_id}", timeout=30).json()
    refs = report.get("references") or []
    cites = report.get("citations") or {}
    check("report_references", len(refs) > 0, {"references": len(refs)})
    check("report_citations", (cites.get("summary") or {}).get("total", 0) > 0,
          {"citations": (cites.get("summary") or {}).get("total")})
    check("report_captions", (cites.get("captions") or {}).get("unique", 0) > 0,
          {"caption_labels": (cites.get("captions") or {}).get("unique")})
    check("report_cited_in", any(r.get("cited_in") for r in refs),
          {"refs_with_cited_in": sum(1 for r in refs if r.get("cited_in"))})

    ann = requests.get(f"{base}/api/report/{job_id}/annotated", timeout=60)
    check("annotated_pdf", ann.status_code == 200 and len(ann.content) > 10000,
          {"bytes": len(ann.content), "x_annotated": ann.headers.get("x-annotated"),
           "x_citations": ann.headers.get("x-citations-annotated")})

    for fmt in ("ris", "enw", "bibtex", "csl", "refs"):
        r = requests.get(f"{base}/api/report/{job_id}/export", params={"format": fmt}, timeout=30)
        check(f"export_{fmt}", r.status_code == 200 and len(r.content) > 0,
              {"bytes": len(r.content)})

    bundle = requests.get(f"{base}/api/report/{job_id}/bundle", timeout=120)
    names = []
    if bundle.status_code == 200 and bundle.content:
        with zipfile.ZipFile(BytesIO(bundle.content)) as zf:
            names = zf.namelist()
    check("evidence_bundle", any(n.endswith("manifest.json") for n in names) and any(n.endswith("report.ris") for n in names),
          {"files": len(names), "sample": names[:8]})

    diff = requests.get(f"{base}/api/report/{job_id}/diff", params={"against": job_id}, timeout=30)
    check("diff_self", diff.status_code == 200 and "summary" in diff.json(),
          {"status": diff.status_code})

    result = {
        "base": base,
        "pdf": str(pdf),
        "job": job_id,
        "version": health.get("version"),
        "checks": checks,
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": [c["check"] for c in checks if not c["ok"]],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("job", "version", "passed")}, ensure_ascii=False))
    print("failed:", result["failed"])
    for c in checks:
        print(("PASS " if c["ok"] else "FAIL ") + c["check"], c["detail"])
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
