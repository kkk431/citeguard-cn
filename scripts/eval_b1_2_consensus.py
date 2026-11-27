"""Evaluate the conservative human-machine consensus on 105 CiteMap cells.

Reads the merged three-reviewer sheet (101 resolved rows), reports the
consensus distribution and the subset that can be promoted to an accepted
machine-evidence edge.  This is a data audit, not a new accuracy claim.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from citeguard.evidence_consensus import accepted_edges, consensus, summarize


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", default="data/experiments/citemap_audit_105/merged.csv")
    ap.add_argument("--out", default="data/experiments/opt_b1_2_consensus_2026-11-27.json")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.merged, encoding="utf-8-sig")))
    summary = summarize(rows)
    edges = accepted_edges(rows)
    by_kind = Counter()
    for row in rows:
        by_kind[(row.get("cell_kind"), consensus(row).status)] += 1
    payload = {
        "source": args.merged,
        "rows": len(rows),
        "summary": summary,
        "machine_evidence_accepted": summary["machine_accepted"],
        "machine_evidence_rejected": summary["machine_rejected"],
        "machine_evidence_contested": summary["machine_evidence"] - summary["machine_accepted"] - summary["machine_rejected"],
        "accepted_machine_edges": edges,
        "by_kind_status": {f"{k[0]}|{k[1]}": v for k, v in sorted(by_kind.items())},
        "rule": "accepted only if all three reviewers say correct; 2:1 is contested; machine confidence cannot self-promote",
        "caveat": "101 resolved rows of the 105-cell grid; not a new product accuracy number",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("rows", "summary", "machine_evidence_accepted", "machine_evidence_rejected", "machine_evidence_contested")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
