"""Filter v1 CiteMap candidate evidence through a strict second-model check.

The v1 extractor over-generated: a quote may be on-topic but not support the
claim. This script keeps only candidates that an independent strict reviewer
accepts with the same stance. Output is still machine-generated and
``verified=false``; it is not a human audit.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"
sys.path.insert(0, str(ROOT / "scripts"))
import extract_citemap_auto_v2 as v2  # noqa: E402


def main() -> int:
    v2._load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out-dir", default=str(DATA / "extractions_strict"))
    args = ap.parse_args()

    abstracts = json.loads((DATA / "abstracts.json").read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = DATA / "strict_cache"
    cache.mkdir(parents=True, exist_ok=True)

    for topic_id in ("ai_education", "medical_imaging"):
        corpus = json.loads((DATA / "corpus" / f"{topic_id}.json").read_text(encoding="utf-8"))
        manual = json.loads((DATA / "extractions" / f"{topic_id}.json").read_text(encoding="utf-8"))
        candidates = json.loads(
            (DATA / "extractions_auto" / f"{topic_id}.json").read_text(encoding="utf-8")
        )
        papers = {p["paper_id"]: p for p in corpus["papers"]}
        claims = {c["claim_id"]: c for c in manual["claims"]}

        jobs = []
        for ev in candidates.get("evidence", []):
            paper = papers.get(ev["paper_id"])
            claim = claims.get(ev["claim_id"])
            if not paper or not claim:
                continue
            abstract = v2._norm(
                abstracts.get(paper["openalex_id"], {}).get("abstract", "")
            )
            if not abstract:
                continue
            cache_file = cache / f"{topic_id}-{ev['evidence_id']}.json"
            jobs.append((ev, paper, claim, abstract, cache_file))

        def check(job):
            ev, paper, claim, abstract, cache_file = job
            if cache_file.exists():
                try:
                    return ev, json.loads(cache_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            try:
                obj = v2._post(
                    v2.VERIFY_SYSTEM,
                    v2.VERIFY_TMPL.format(
                        claim=claim["text"],
                        quote=ev["quote"],
                        title=paper["title"],
                        abstract=abstract,
                    ),
                    max_tokens=300,
                )
                ok = bool(obj.get("valid")) and str(obj.get("stance", "")).lower() == ev["stance"]
                decision = {"keep": ok, "reason": str(obj.get("reason", ""))[:400]}
            except Exception as exc:  # noqa: BLE001 - keep batch alive
                decision = {"keep": False, "reason": f"error: {exc}"}
            cache_file.write_text(json.dumps(decision, ensure_ascii=False), encoding="utf-8")
            return ev, decision

        decisions = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = [pool.submit(check, job) for job in jobs]
            for fut in as_completed(futures):
                decisions.append(fut.result())

        kept = []
        for ev, decision in decisions:
            if decision.get("keep"):
                item = dict(ev)
                item["extractor"] = "strict-verifier:v1"
                item["verifier_reason"] = decision.get("reason", "")
                kept.append(item)
        kept.sort(key=lambda e: (e["paper_id"], e["claim_id"], e["evidence_id"]))
        payload = {
            "schema_version": "1.0",
            "topic_id": topic_id,
            "extractor": "strict-verifier:v1",
            "extracted_at": time.strftime("%Y-%m-%d"),
            "protocol": "v1 abstract candidates filtered by an independent strict reviewer; machine-only, verified=false.",
            "evidence": kept,
        }
        (out_dir / f"{topic_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"{topic_id}: kept {len(kept)} / {len(jobs)} candidates", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
