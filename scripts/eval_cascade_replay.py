"""Replay the cascade policy on two recorded 60-item runs.

This is deliberately a replay, not a new model run: the 1.7B LoRA predictions
and the 14B 4-bit predictions were produced earlier on the same test split.
It answers one honest question — on this split, does escalating from 1.7B to
14B help, and how often would the policy escalate?
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.model_cascade import CascadeConfig, numeric_conflict  # noqa: E402

LABELS = ("support", "partial", "contradict", "no_evidence")


def macro_f1(gold: list[str], pred: list[str]) -> tuple[float, float]:
    correct = sum(g == p for g, p in zip(gold, pred))
    acc = correct / len(gold) if gold else 0.0
    scores = []
    for label in LABELS:
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return round(acc, 4), round(sum(scores) / len(scores), 4)


def _raw_confidence(raw: str, default: float = 0.8) -> float:
    try:
        obj = json.loads(raw or "{}")
        return float(obj.get("confidence", default))
    except Exception:
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary", default="data/experiments/support_lora_qwen3_1.7b_test_predictions.json")
    ap.add_argument("--escalation", default="data/experiments/support_local_qwen3_14b_4bit_test.json")
    ap.add_argument("--test", default="data/sft/support_test.jsonl")
    ap.add_argument("--out", default="data/experiments/opt_b0_cascade_replay_2026-11-27.json")
    ap.add_argument("--threshold", type=float, default=0.80)
    args = ap.parse_args()

    primary = json.loads((ROOT / args.primary).read_text(encoding="utf-8"))["predictions"]
    escalation = json.loads((ROOT / args.escalation).read_text(encoding="utf-8"))["predictions"]
    test_rows = {r["id"]: r for r in (json.loads(line) for line in (ROOT / args.test).read_text(encoding="utf-8").splitlines() if line.strip())}
    esc = {r["id"]: r for r in escalation}
    cfg = CascadeConfig(confidence_threshold=args.threshold)

    gold, p_pred, e_pred, routed_pred = [], [], [], []
    routed = []
    reasons: dict[str, int] = {}
    for row in primary:
        item = test_rows.get(row["id"])
        if not item or row["id"] not in esc:
            continue
        gold.append(row["gold"])
        p_pred.append(row["pred"])
        e_pred.append(esc[row["id"]]["pred"])
        conf = _raw_confidence(row.get("raw", ""))
        reason = ""
        if conf < cfg.confidence_threshold:
            reason = "low_confidence"
        elif len(item.get("evidence") or "") > cfg.max_primary_evidence_chars:
            reason = "long_evidence"
        elif numeric_conflict(item.get("claim", ""), item.get("evidence", "")):
            reason = "numeric_conflict"
        # A missing/invalid primary label also escalates.
        if row["pred"] not in LABELS:
            reason = "invalid_label"
        if reason:
            routed.append(row["id"])
            routed_pred.append(esc[row["id"]]["pred"])
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            routed_pred.append(row["pred"])

    p_acc, p_f1 = macro_f1(gold, p_pred)
    e_acc, e_f1 = macro_f1(gold, e_pred)
    r_acc, r_f1 = macro_f1(gold, routed_pred)
    out = {
        "generated_at": "2026-11-27",
        "kind": "recorded_replay_not_a_new_model_run",
        "n": len(gold),
        "primary": {"model": "qwen3-1.7b-lora", "accuracy": p_acc, "macro_f1": p_f1},
        "escalation": {"model": "qwen3-14b-4bit", "accuracy": e_acc, "macro_f1": e_f1},
        "oracle_escalation_all": {"accuracy": e_acc, "macro_f1": e_f1},
        "cascade": {"accuracy": r_acc, "macro_f1": r_f1, "routed": len(routed), "route_reasons": reasons},
        "config": {"confidence_threshold": cfg.confidence_threshold, "max_primary_evidence_chars": cfg.max_primary_evidence_chars},
        "conclusion": "no measured gain" if r_f1 <= p_f1 else "escalation improved the replay",
    }
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
