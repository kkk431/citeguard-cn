"""Summarise the atomic full-text evaluation against the 105-cell audit.

The human audit's positive evidence cells are the only human-positive
reference we have.  This script reports two different numbers:

* full support recall: how many audited-positive cells the strict verifier
  found with a ``full`` verdict;
* any support recall: how many were found with ``full`` or ``partial``.

Both are small-sample descriptive statistics, not an accuracy benchmark.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "experiments" / "citemap_atomic_fulltext_v3.json"
FALLBACK = ROOT / "data" / "experiments" / "citemap_atomic_fulltext.json"
MERGED = ROOT / "data" / "experiments" / "citemap_audit_105" / "merged.csv"
FULLTEXT = ROOT / "data" / "cache" / "citemap_fulltext"
OUT = ROOT / "data" / "experiments" / "citemap_atomic_fulltext_v3_summary.json"

_RANK = {"full": 3, "partial": 2, "none": 1, "error": 0}


def main() -> int:
    path = RESULTS if RESULTS.exists() else FALLBACK
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = payload["results"]
    rows = list(csv.DictReader(MERGED.read_text(encoding="utf-8-sig").splitlines()))
    fulltext_papers = {p.stem for p in FULLTEXT.glob("*.txt")}
    audited = []
    for row in rows:
        if row["majority"] != "correct" or row["cell_kind"] != "机器证据":
            continue
        if row["paper_id"] not in fulltext_papers:
            continue
        matches = [
            r for r in results
            if r["paper_id"] == row["paper_id"] and r["parent_claim_id"] == row["claim_id"]
        ]
        best = max((r["verdict"] for r in matches), key=lambda v: _RANK.get(v, 0), default="none")
        full = [r for r in matches if r["verdict"] == "full"]
        audited.append({
            "paper_id": row["paper_id"],
            "claim_id": row["claim_id"],
            "best_verdict": best,
            "fulltext_hit": bool(full),
            "support_hit": best in {"full", "partial"},
            "atomic_id": full[0]["atomic_id"] if full else "",
            "quote": full[0]["evidence"] if full else "",
        })
    full_hits = sum(1 for a in audited if a["fulltext_hit"])
    support_hits = sum(1 for a in audited if a["support_hit"])
    full_verdicts = [r for r in results if r["verdict"] == "full"]
    audited_full = sum(1 for r in full_verdicts if any(
        a["paper_id"] == r["paper_id"] and a["claim_id"] == r["parent_claim_id"] for a in audited
    ))
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
        "result_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "fulltext_papers": len(fulltext_papers),
        "fulltext_total": 30,
        "pairs": len(results),
        "verdicts": payload.get("summary"),
        "by_topic": by_topic,
        "audited_positive_with_fulltext": audited,
        "audited_positive_n": len(audited),
        "audited_positive_full_hits": full_hits,
        "audited_positive_support_hits": support_hits,
        "audited_positive_full_recall": round(full_hits / len(audited), 4) if audited else 0.0,
        "audited_positive_support_recall": round(support_hits / len(audited), 4) if audited else 0.0,
        "full_verdict_precision_on_audited": round(audited_full / max(1, len(full_verdicts)), 4),
        "boundary": (
            f"Only {len(fulltext_papers)}/30 papers have local OA full text; "
            f"{len(audited)} audited-positive cells overlap those papers. "
            "Support recall counts full+partial; full recall counts only full. "
            "Neither is a full human-labelled accuracy set."
        ),
        "note": "Full verdicts not covered by a human-positive cell are not claimed as correct.",
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
