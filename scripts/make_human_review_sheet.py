"""Blind review sheet for a human-labelled subset of ClaimSupport-CN.

The sheet hides the original label and model prediction: the reviewer only sees
claim + evidence and fills one of support/partial/contradict/no_evidence.
Usage:
  python scripts/make_human_review_sheet.py --out data/claimsupport_cn/human_review_40.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/claimsupport_cn/claimsupport_cn.jsonl"
SPLIT = ROOT / "data/claimsupport_cn/split_seed20261024.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/claimsupport_cn/human_review_40.csv")
    ap.add_argument("--seed", type=int, default=20261025)
    args = ap.parse_args()

    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    ids = list(split["dev"])
    random.Random(args.seed).shuffle(ids)
    rows = {row["id"]: row for row in map(json.loads, DATASET.read_text(encoding="utf-8").splitlines()) if row}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "claim", "evidence", "your_label", "note"])
        for cid in ids:
            row = rows[cid]
            writer.writerow([cid, row["claim"], row["evidence"], "", ""])
    print(f"wrote {len(ids)} blinded rows -> {out}")
    print("labels: support | partial | contradict | no_evidence")


if __name__ == "__main__":
    main()
