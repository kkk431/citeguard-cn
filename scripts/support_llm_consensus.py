#!/usr/bin/env python
"""Build an LLM-consensus audit track for ClaimSupport-CN.

Reads the per-annotator audit files written by `scripts/llm_annotate_support.py`
plus the shipped product predictions (`results.json`), then reports:

- pairwise Cohen's kappa between independent LLM annotators;
- majority-label agreement with the programmatically constructed labels;
- product accuracy/macro-F1 against the majority labels;
- the disagreement list (candidate label noise).

This is an *LLM-consensus audit*, not a human-labeled gold set.

Usage:
  python scripts/support_llm_consensus.py                 # all 100
  python scripts/support_llm_consensus.py --split test    # held-out 60
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "claimsupport_cn"
LABELS = ["support", "partial", "contradict", "no_evidence"]


def kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    if not n:
        return 0.0
    observed = sum(1 for a, b in pairs if a == b) / n
    ca: dict[str, int] = {}
    cb: dict[str, int] = {}
    for a, _ in pairs:
        ca[a] = ca.get(a, 0) + 1
    for _, b in pairs:
        cb[b] = cb.get(b, 0) + 1
    expected = sum((ca.get(lab, 0) / n) * (cb.get(lab, 0) / n) for lab in LABELS)
    if expected >= 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def f1_macro(gold: list[str], pred: list[str]) -> tuple[float, dict[str, dict]]:
    per_class = {}
    for lab in LABELS:
        tp = sum(1 for g, p in zip(gold, pred) if g == lab and p == lab)
        fp = sum(1 for g, p in zip(gold, pred) if g != lab and p == lab)
        fn = sum(1 for g, p in zip(gold, pred) if g == lab and p != lab)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[lab] = {"precision": round(precision, 4), "recall": round(recall, 4),
                          "f1": round(f1, 4), "support": sum(1 for g in gold if g == lab)}
    return sum(v["f1"] for v in per_class.values()) / len(LABELS), per_class


def split_ids(split: str) -> set[str] | None:
    if split == "all":
        return None
    data = json.loads((DATA / "split_seed20261024.json").read_text(encoding="utf-8"))
    return set(data[split])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["all", "dev", "test"], default="all",
                        help="which held-out split to audit (default: all 100)")
    args = parser.parse_args()

    rows = [json.loads(line) for line in (DATA / "claimsupport_cn.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    wanted = split_ids(args.split)
    gold = {r["id"]: r["label"] for r in rows if wanted is None or r["id"] in wanted}
    ids = sorted(gold)
    suffix = "" if args.split == "all" else f"-{args.split}"

    annotators: dict[str, dict[str, str]] = {}
    for path in sorted(DATA.glob(f"llm_annotation_*{suffix}.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        preds = {p["id"]: p["pred"] for p in run["predictions"] if p["id"] in gold}
        if len(preds) < len(ids) * 0.9:
            print(f"skip {path.name}: only {len(preds)}/{len(ids)} predictions", file=sys.stderr)
            continue
        annotators[run["tag"]] = preds
    if len(annotators) < 2:
        sys.exit("need at least two complete annotator runs")

    product = {}
    results_path = DATA / "results.json"
    if results_path.exists():
        res = json.loads(results_path.read_text(encoding="utf-8"))
        product = {p["id"]: p["pred"] for p in res["predictions"] if p["id"] in gold}

    # pairwise annotator agreement (only ids both annotators cover)
    pairwise = {}
    for a, b in combinations(annotators, 2):
        common = [i for i in ids if i in annotators[a] and i in annotators[b]]
        pairs = [(annotators[a][i], annotators[b][i]) for i in common]
        agreement = sum(1 for x, y in pairs if x == y) / len(pairs) if pairs else 0.0
        pairwise[f"{a}__{b}"] = {"n": len(pairs), "agreement": round(agreement, 4),
                                 "kappa": round(kappa(pairs), 4)}

    # majority vote (ties -> reasoner if available, else first annotator, else "tie")
    priority = [t for t in ("deepseek-reasoner", "deepseek", "qwen3-8b") if t in annotators]
    majority: dict[str, str] = {}
    ties = []
    for i in ids:
        votes = [annotators[t][i] for t in annotators if i in annotators[t]]
        if len(votes) < 2:
            majority[i] = gold[i]
            ties.append(i)
            continue
        counts = {lab: votes.count(lab) for lab in LABELS}
        top = max(counts.values())
        winners = [lab for lab, c in counts.items() if c == top]
        if len(winners) == 1:
            majority[i] = winners[0]
        else:
            ties.append(i)
            majority[i] = next((annotators[t][i] for t in priority
                                if i in annotators[t] and annotators[t][i] in winners), winners[0])

    constructed_vs_majority = [(gold[i], majority[i]) for i in ids]
    metrics = {
        "split": args.split,
        "n": len(ids),
        "annotators": list(annotators),
        "pairwise": pairwise,
        "majority_vs_constructed": {
            "agreement": round(sum(1 for g, m in constructed_vs_majority if g == m) / len(ids), 4),
            "kappa": round(kappa(constructed_vs_majority), 4),
            "ties": ties,
        },
    }
    if product:
        gold_list = [gold[i] for i in ids]
        maj_list = [majority[i] for i in ids]
        prod_list = [product[i] for i in ids]
        macro, per_class = f1_macro(maj_list, prod_list)
        metrics["product"] = {
            "accuracy_vs_constructed": round(sum(1 for g, p in zip(gold_list, prod_list) if g == p) / len(ids), 4),
            "accuracy_vs_majority": round(sum(1 for g, p in zip(maj_list, prod_list) if g == p) / len(ids), 4),
            "macro_f1_vs_majority": round(macro, 4),
            "per_class_vs_majority": per_class,
        }

    noise = [{"id": i, "constructed": gold[i], "majority": majority[i],
              "votes": {t: annotators[t][i] for t in annotators if i in annotators[t]},
              "product": product.get(i, "")}
             for i in ids if gold[i] != majority[i]]
    out = {"generated_by": "scripts/support_llm_consensus.py", "split": args.split,
           "metrics": metrics, "disagreements": noise,
           "items": [{"id": i, "constructed": gold[i], "majority": majority[i],
                      "annotator_votes": {t: annotators[t][i] for t in annotators if i in annotators[t]},
                      "product": product.get(i, "")} for i in ids]}
    out_path = DATA / f"llm_consensus{suffix}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print("\nconstructed-label disagreements:", len(noise))
    for row in noise[:15]:
        print(" ", row["id"], row["constructed"], "->", row["majority"],
              "votes", row["votes"], "product", row["product"])
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
