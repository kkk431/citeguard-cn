"""Summarise the atomic full-text evaluation against the 105-cell audit.

The audit's 8 "majority correct" evidence cells are the only human-positive
reference we have.  Only two of them have a local full text; this script
reports whether the strict full-text verifier found those two, instead of
pretending 87 claim-paper pairs are all human-labelled.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "experiments" / "citemap_atomic_fulltext.json"
MERGED = ROOT / "data" / "experiments" / "citemap_audit_105" / "merged.csv"
FULLTEXT = ROOT / "data" / "cache" / "citemap_fulltext"
OUT = ROOT / "data" / "experiments" / "citemap_atomic_fulltext_summary.json"


def main() -> int:
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    results = payload["results"]
    rows = list(csv.DictReader(MERGED.read_text(encoding="utf-8-sig").splitlines()))
    fulltext_papers = {p.stem for p in FULLTEXT.glob("*.txt")}
    positives = [r for r in rows if r["majority"] == "correct" and r["cell_kind"] == "机器证据"]
    positive_with_ft = [r for r in positives if r["paper_id"] in fulltext_papers]
    found = {(r["paper_id"], r["parent_claim_id"]): r for r in results if r["verdict"] == "full"}
    audits = []
    for row in positive_with_ft:
        key = (row["paper_id"], row["claim_id"])
        hit = found.get(key)
        audits.append(
            {
                "paper_id": row["paper_id"],
                "claim_id": row["claim_id"],
                "audited_positive": True,
                "fulltext_hit": bool(hit),
                "atomic_id": hit["atomic_id"] if hit else "",
                "quote": hit["evidence"] if hit else "",
            }
        )
    by_topic: dict[str, dict[str, int]] = {}
    for result in results:
        topic = result.get("topic_id") or {
            "edu": "ai_education",
            "med": "medical_imaging",
        }.get(result.get("paper_id", "").split("-")[0], "unknown")
        bucket = by_topic.setdefault(topic, {"full": 0, "partial": 0, "none": 0, "error": 0})
        bucket[result["verdict"]] = bucket.get(result["verdict"], 0) + 1
    summary = {
        "generated_at": payload.get("generated_at"),
        "data_source": payload.get("data_source"),
        "claim_source": payload.get("claim_source"),
        "fulltext_papers": len(fulltext_papers),
        "fulltext_total": 30,
        "boundary": (
            f"Only {len(fulltext_papers)}/30 papers have local OA full text; "
            f"{len(results)} claim-paper pairs are not a human-labelled accuracy set."
        ),
        "pairs": len(results),
        "verdicts": payload.get("summary"),
        "by_topic": by_topic,
        "audited_positive_with_fulltext": audits,
        "audited_positive_with_fulltext_recall": (
            round(sum(1 for a in audits if a["fulltext_hit"]) / len(audits), 4) if audits else 0.0
        ),
        "full_verdict_precision_on_audited": (
            round(sum(1 for a in audits if a["fulltext_hit"]) / max(1, sum(1 for r in results if r["verdict"] == "full")), 4)
        ),
        "note": "Full verdicts not covered by a human-positive cell are not claimed as correct; they remain unlabelled candidates.",
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
