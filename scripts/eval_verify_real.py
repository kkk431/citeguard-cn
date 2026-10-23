"""Measure verification verdicts on real references taken from published papers.

The corpus is a set of reference lists printed by real Chinese journals; every
entry was published, so a ``Major`` verdict on one of them is a candidate false
positive of the verifier (the source paper may still contain errors, but the
base rate is low). Majors are split by evidence type so we can see whether they
come from a dead DOI (strong) or from a plain title search miss (weak).

Usage:
    python scripts/eval_verify_real.py [--limit 0]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.metadata_verify import verify_many  # noqa: E402
from citeguard.reference_parser import parse_reference_list  # noqa: E402

CORPUS = ROOT / "data" / "real_corpus"
OUT = ROOT / "data" / "experiments" / "verify_real.json"


def load_refs() -> list[dict]:
    items: list[dict] = []
    hans = CORPUS / "hanspub_manifest.json"
    if hans.exists():
        for item in json.loads(hans.read_text(encoding="utf-8")):
            refs_file = item.get("refs_file")
            if refs_file and Path(refs_file).exists():
                items.append({"title": item.get("title", ""), "text": Path(refs_file).read_text(encoding="utf-8")})
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="limit papers (0 = all)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    papers = load_refs()
    if args.limit:
        papers = papers[: args.limit]

    rows: list[dict] = []
    status = Counter()
    major_reasons = Counter()
    # `[EB/OL]` citations are checked against their URL; record how it went.
    url_checks: Counter = Counter()
    for paper in papers:
        refs = parse_reference_list(paper["text"])
        results = verify_many(refs)
        for ref, res in zip(refs, results):
            status[res.status] += 1
            row = {
                "paper": paper["title"][:40],
                "raw": ref.raw[:220],
                "title": ref.title[:120],
                "authors": ref.authors[:3],
                "year": ref.year,
                "venue": ref.venue[:60],
                "doi": ref.doi,
                "status": res.status,
                "doi_status": res.doi_status,
                "title_sim": res.title_sim,
                "mismatches": res.mismatches,
                "notes": res.notes[:4],
                "sources": res.sources,
            }
            url_source = next((x for x in res.sources if x.startswith("url:")), "")
            if url_source:
                url_checks[url_source.split(":", 1)[1]] += 1
            if res.status == "Major":
                if res.doi_status == "not_found":
                    reason = "doi_404"
                elif res.mismatches and "title" in res.mismatches:
                    reason = "title_mismatch"
                elif not res.best:
                    reason = "no_candidate"
                else:
                    reason = "other"
                row["major_reason"] = reason
                major_reasons[reason] += 1
            rows.append(row)
        print(f"  {len(refs):3d} refs  {paper['title'][:36]}")

    total = sum(status.values()) or 1
    summary = {
        "papers": len(papers),
        "refs": sum(status.values()),
        "status": dict(status),
        "major_reasons": dict(major_reasons),
        "major_rate": round(status["Major"] / total, 4),
        "unknown_rate": round(status["Unknown"] / total, 4),
        "url_checks": dict(url_checks),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n== verification on real references ==")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if url_checks:
        print("\nWeb links checked:")
        for state, count in sorted(url_checks.items()):
            print(f"  {state:10s} {count}")
    print("\nMajors (candidate false positives):")
    for row in rows:
        if row["status"] == "Major":
            print(f"  [{row.get('major_reason')}] {row['raw'][:130]}")
    print(f"\nreport -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
