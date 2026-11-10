"""Evaluate the local adapter judge through the *product* support prompt.

The server (scripts/adapter_judge_server.py) receives exactly what
``citeguard.support._chat_json`` would send, extracts the claim/evidence and
answers with the SFT adapter. This measures the end-to-end support path, not
just the SFT harness.

    python scripts/eval_support_adapter.py --endpoint http://127.0.0.1:8101/v1
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from citeguard import support as support_mod  # noqa: E402

LABELS = ["support", "partial", "contradict", "no_evidence"]


def macro_f1(gold: list[str], pred: list[str]) -> dict:
    n = len(gold)
    cm = [[0] * 4 for _ in range(4)]
    idx = {l: i for i, l in enumerate(LABELS)}
    for g, p in zip(gold, pred):
        cm[idx[g]][idx[p]] += 1
    per, f1s = {}, []
    for i, label in enumerate(LABELS):
        tp = cm[i][i]
        fp = sum(cm[j][i] for j in range(4)) - tp
        fn = sum(cm[i][j] for j in range(4)) - tp
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[label] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4)}
        f1s.append(f1)
    return {
        "macro_f1": round(sum(f1s) / 4, 4),
        "accuracy": round(sum(cm[i][i] for i in range(4)) / n, 4),
        "confusion": cm,
        "per_class": per,
        "n": n,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8101/v1")
    ap.add_argument("--data", default=str(ROOT / "data" / "sft" / "support_test.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "out" / "support_adapter_eval.json"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.data).read_text(encoding="utf-8").splitlines() if l.strip()]
    gold, pred = [], []
    for i, row in enumerate(rows):
        user = f"【引用句】{row['claim']}\n【证据片段】{row['evidence']}"
        resp = requests.post(
            args.endpoint + "/chat/completions",
            json={
                "model": "qwen3-1.7b-support-lora",
                "messages": [
                    {"role": "system", "content": "你是严谨的学术引文核验员。"},
                    {"role": "user", "content": support_mod.PROMPT + "\n\n" + user},
                ],
                "temperature": 0,
                "max_tokens": 40,
            },
            timeout=120,
        )
        label = "no_evidence"
        try:
            content = resp.json()["choices"][0]["message"]["content"]
            label = json.loads(content).get("label") or "no_evidence"
        except Exception:  # noqa: BLE001
            pass
        if label not in LABELS:
            label = "no_evidence"
        gold.append(row["label"])
        pred.append(label)
        print(i, row["label"], label, flush=True)
    result = macro_f1(gold, pred)
    result["endpoint"] = args.endpoint
    result["errors"] = [(rows[i]["id"], gold[i], pred[i]) for i in range(len(rows)) if gold[i] != pred[i]]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("macro_f1", "accuracy", "confusion", "n")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
