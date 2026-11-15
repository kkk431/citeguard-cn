"""Extract evidence for atomic CiteMap claims.

Each atomic claim is checked independently against each abstract, with an
independent verification call. Output stays machine-only (verified=false).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"
CACHE = DATA / "atomic_cache"
sys.path.insert(0, str(ROOT / "scripts"))
import extract_citemap_auto_v2 as v2  # noqa: E402


def main() -> int:
    v2._load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", action="append", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out-dir", default=str(DATA / "extractions_atomic"))
    args = ap.parse_args()

    atomic_all = json.loads((DATA / "claims_atomic.json").read_text(encoding="utf-8"))
    abstracts = json.loads((DATA / "abstracts.json").read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    for topic_id in args.topic or ["ai_education", "medical_imaging"]:
        corpus = json.loads((DATA / "corpus" / f"{topic_id}.json").read_text(encoding="utf-8"))
        claims = atomic_all["topics"][topic_id]["claims"]
        papers = corpus["papers"]
        if args.limit:
            papers = papers[: args.limit]

        jobs = []
        for paper in papers:
            abstract = v2._norm(abstracts.get(paper["openalex_id"], {}).get("abstract", ""))
            if not abstract:
                continue
            for claim in claims:
                key = hashlib.sha256(
                    ("atomic-v1" + paper["paper_id"] + claim["atomic_id"] + abstract).encode("utf-8")
                ).hexdigest()[:20]
                cache = CACHE / f"{topic_id}-{paper['paper_id']}-{claim['atomic_id']}-{key}.json"
                jobs.append((paper, abstract, claim, cache))

        def work(job):
            paper, abstract, claim, cache = job
            if cache.exists():
                try:
                    return paper, claim, json.loads(cache.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            check_claim = dict(claim)
            check_claim["claim_id"] = claim["atomic_id"]
            item = v2._extract_claim(check_claim, paper, abstract)
            if not item or not v2._verify(item, check_claim, paper, abstract):
                cache.write_text("null", encoding="utf-8")
                return paper, claim, None
            item["paper_id"] = paper["paper_id"]
            item["atomic_id"] = claim["atomic_id"]
            item["parent_claim_id"] = claim["parent_claim_id"]
            item["extractor"] = "auto:abstract-only:atomic-v1"
            cache.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
            return paper, claim, item

        found = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = [pool.submit(work, job) for job in jobs]
            for fut in as_completed(futures):
                paper, claim, item = fut.result()
                if item:
                    found.append((paper, item))

        evidence = []
        for paper, item in sorted(found, key=lambda x: (x[0]["paper_id"], x[1]["atomic_id"])):
            evidence.append(
                {
                    "evidence_id": f"atom-{item['paper_id']}-{item['atomic_id']}",
                    "atomic_id": item["atomic_id"],
                    "parent_claim_id": item["parent_claim_id"],
                    "claim_id": item["atomic_id"],
                    "paper_id": paper["paper_id"],
                    "stance": item["stance"],
                    "summary": item["summary"],
                    "quote": item["quote"],
                    "locator": "Abstract",
                    "method": item["method"],
                    "sample": item["sample"],
                    "confidence": round(item["confidence"], 3),
                    "verified": False,
                    "extractor": item["extractor"],
                }
            )
        payload = {
            "schema_version": "1.0",
            "topic_id": topic_id,
            "extractor": "auto:atomic-v1",
            "extracted_at": time.strftime("%Y-%m-%d"),
            "protocol": "Atomic claims; per-claim extraction + independent verification; verified=false.",
            "evidence": evidence,
        }
        (out_dir / f"{topic_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"{topic_id}: {len(evidence)} evidence over {len(papers)} papers", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
