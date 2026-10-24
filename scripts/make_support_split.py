"""Create a fixed, stratified dev/test split for ClaimSupport-CN.

Tuning on the dev half and reporting the untouched test half keeps prompt
iteration from overfitting the 100-case benchmark. The split is committed so
every later run can be reproduced.

Usage:
    PYTHONPATH=src python3 scripts/make_support_split.py
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl"
OUT = ROOT / "data" / "claimsupport_cn" / "split_seed20261024.json"
SEED = 20261024
DEV_RATIO = 0.4
LABELS = ["support", "partial", "contradict", "no_evidence"]


def main() -> None:
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_label: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_label[row["label"]].append(row["id"])

    rng = random.Random(SEED)
    dev: list[str] = []
    test: list[str] = []
    for label in LABELS:
        ids = sorted(by_label[label])
        rng.shuffle(ids)
        cut = round(len(ids) * DEV_RATIO)
        dev.extend(ids[:cut])
        test.extend(ids[cut:])

    dev_set, test_set = set(dev), set(test)
    assert not (dev_set & test_set)
    assert len(dev_set) + len(test_set) == len(rows)

    payload = {
        "dataset": "ClaimSupport-CN",
        "seed": SEED,
        "dev_ratio": DEV_RATIO,
        "n": len(rows),
        "dev": sorted(dev),
        "test": sorted(test),
        "counts": {
            "dev": {label: sum(1 for i in dev if i in by_label[label]) for label in LABELS},
            "test": {label: sum(1 for i in test if i in by_label[label]) for label in LABELS},
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} dev={len(dev)} test={len(test)}")
    print(json.dumps(payload["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
