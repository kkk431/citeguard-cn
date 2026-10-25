"""Score the filled blind-review sheet against gold labels and the model.

Usage:
  python scripts/check_human_labels.py data/claimsupport_cn/human_review_40.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ("support", "partial", "contradict", "no_evidence")


def macro_f1(gold: list[str], pred: list[str]) -> float:
    scores = []
    for label in LABELS:
        tp = sum(1 for g, p in zip(gold, pred) if g == label and p == label)
        fp = sum(1 for g, p in zip(gold, pred) if g != label and p == label)
        fn = sum(1 for g, p in zip(gold, pred) if g == label and p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    args = ap.parse_args()

    dataset = {
        row["id"]: row
        for row in map(json.loads, (ROOT / "data/claimsupport_cn/claimsupport_cn.jsonl").read_text(encoding="utf-8").splitlines())
        if row
    }
    model = {}
    results = ROOT / "data/claimsupport_cn/results.json"
    if results.exists():
        data = json.loads(results.read_text(encoding="utf-8"))
        for row in data.get("predictions", []):
            model[row["id"]] = row["pred"]

    filled = []
    with Path(args.sheet).open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            label = (row.get("your_label") or "").strip()
            if label:
                if label not in LABELS:
                    raise SystemExit(f"bad label {label!r} for {row['id']}")
                filled.append((row["id"], label))
    if not filled:
        raise SystemExit("sheet has no filled your_label values yet")

    ids = [cid for cid, _ in filled]
    human = [label for _, label in filled]
    gold = [dataset[cid]["label"] for cid in ids]
    agree = sum(1 for g, h in zip(gold, human) if g == h) / len(ids)
    print(f"reviewed {len(ids)}/40 rows; human-vs-gold agreement {agree:.3f}")
    m = [model.get(cid) for cid in ids]
    if all(m):
        print(f"model-vs-gold macro-F1 on reviewed subset: {macro_f1(gold, m):.4f}")
        print(f"model-vs-human agreement: {sum(1 for h, p in zip(human, m) if h == p) / len(ids):.3f}")
        print("confusion gold->human:", {g: human.count(g) for g in LABELS})
        print("model confusion gold->model:", {g: sum(1 for gg, pp in zip(gold, m) if gg == g and pp == g) for g in LABELS})


if __name__ == "__main__":
    main()
