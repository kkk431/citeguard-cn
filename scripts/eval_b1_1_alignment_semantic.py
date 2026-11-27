"""Evaluate assertion-level alignment with the real semantic judge.

The 31 machine-evidence cells in the 105-cell CiteMap audit have a human
majority label (correct / issue).  This script compares:

1. a direct claim-vs-quote judge (the existing product-like baseline), and
2. assertion-level alignment (decompose + judge each sub-claim).

Both are mapped to a binary "evidence is acceptable" decision and compared to
the human majority.  It is a small internal audit, not a new accuracy claim.
"""

from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from pathlib import Path

from citeguard.atomic_alignment import align_claim


def _claims(base: str, topic: str) -> dict[str, str]:
    with urllib.request.urlopen(f"{base}/api/citemap/{topic}", timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return {c["claim_id"]: c["text"] for c in payload.get("claims", [])}


_CACHE: dict[tuple[str, str], dict] = {}


def _judge(claim: str, evidence: str) -> dict | None:
    key = (claim, evidence)
    if key in _CACHE:
        return _CACHE[key]
    body = json.dumps({"claim": claim, "evidence": evidence}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8013/api/support/check",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    _CACHE[key] = out
    return out


def _positive(label: str) -> bool:
    return label in {"support", "partial"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8013")
    ap.add_argument("--key", default="data/experiments/citemap_audit_105/key.csv")
    ap.add_argument("--merged", default="data/experiments/citemap_audit_105/merged.csv")
    ap.add_argument("--out", default="data/experiments/opt_b1_1_alignment_semantic_2026-11-27.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    claims = {}
    for topic in ("ai_education", "medical_imaging"):
        claims.update(_claims(args.base, topic))

    key = {r["cell_id"]: r for r in csv.DictReader(open(args.key, encoding="utf-8-sig"))}
    merged = {r["cell_id"]: r for r in csv.DictReader(open(args.merged, encoding="utf-8-sig"))}
    rows = [r for r in key.values() if r.get("cell_kind") == "机器证据" and r.get("evidence_quote")]
    if args.limit:
        rows = rows[: args.limit]

    items = []
    for row in rows:
        claim = claims.get(row["claim_id"], "")
        evidence = row["evidence_quote"]
        human_correct = merged.get(row["cell_id"], {}).get("majority") == "correct"
        direct = _judge(claim, evidence) or {}
        aligned = align_claim(claim, evidence, judge=_judge)
        items.append({
            "cell_id": row["cell_id"],
            "claim_id": row["claim_id"],
            "human_majority": "correct" if human_correct else "issue",
            "direct_label": direct.get("label", "unavailable"),
            "direct_positive": _positive(str(direct.get("label", ""))),
            "alignment_label": aligned.label,
            "alignment_positive": _positive(aligned.label),
            "subclaims": [x.label for x in aligned.subclaims],
            "coverage": aligned.coverage,
        })

    def metrics(key_name: str) -> dict:
        tp = sum(1 for x in items if x[key_name] and x["human_majority"] == "correct")
        fp = sum(1 for x in items if x[key_name] and x["human_majority"] == "issue")
        fn = sum(1 for x in items if not x[key_name] and x["human_majority"] == "correct")
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}

    payload = {
        "source_key": args.key,
        "source_merged": args.merged,
        "rows": len(items),
        "human_correct": sum(1 for x in items if x["human_majority"] == "correct"),
        "direct": metrics("direct_positive"),
        "alignment": metrics("alignment_positive"),
        "items": items,
        "caveat": "Human majority labels judge whether the machine quote is acceptable, not whether the compound claim is fully supported; binary mapping is a proxy.",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("rows", "human_correct", "direct", "alignment")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
