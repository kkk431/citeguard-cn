"""Evaluate the local adapter judge through the *product* support prompt.

The server (scripts/adapter_judge_server.py) receives exactly what
``citeguard.support._chat_json`` would send, extracts the claim/evidence and
answers with the SFT adapter. This measures the end-to-end support path, not
just the SFT harness.

    python scripts/eval_support_adapter.py --model-size 4b \
        --endpoint http://127.0.0.1:8101/v1 --data data/sft --split test

``--model-size`` only selects the served model name recorded in the request and
in the result file (``qwen3-4b-support-lora`` for a 4B adapter); the prompt and
parsing path stay identical to the product ``citeguard.support`` call, so numbers
are comparable across 1.7B / 4B runs.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def _utf8_stdout() -> None:
    """Windows consoles default to GBK, but the product prompt contains '↔'.

    ``--dry-run`` prints that prompt, so force UTF-8 on the console streams.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - redirected streams
            pass


_utf8_stdout()

sys.path.insert(0, str(ROOT / "src"))
from citeguard import support as support_mod  # noqa: E402

LABELS = ["support", "partial", "contradict", "no_evidence"]
MODEL_SIZES = ("1.7b", "4b", "8b", "14b")
SERVED_NAMES = {size: f"qwen3-{size}-support-lora" for size in MODEL_SIZES}
SYSTEM = "你是严谨的学术引文核验员。"


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


def resolve_data(data: str, split: str) -> Path:
    path = Path(data)
    if path.is_dir():
        return path / f"support_{split}.jsonl"
    return path


def ask(endpoint: str, model: str, row: dict) -> tuple[str, dict]:
    """One product-prompt request; returns (label, debug info)."""
    user = f"【引用句】{row['claim']}\n【证据片段】{row['evidence']}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": support_mod.PROMPT + "\n\n" + user},
        ],
        "temperature": 0,
        "max_tokens": 40,
    }
    last_error = ""
    for attempt in range(3):
        try:
            resp = requests.post(endpoint + "/chat/completions", json=payload, timeout=120)
            content = resp.json()["choices"][0]["message"]["content"]
            label = json.loads(content).get("label") or "no_evidence"
            return (label if label in LABELS else "no_evidence"), {"raw": content[:120]}
        except Exception as exc:  # noqa: BLE001 - a bad row must not kill the run
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(1.5 * (attempt + 1))
    return "no_evidence", {"raw": "", "error": last_error}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8101/v1")
    ap.add_argument("--data", default=str(ROOT / "data" / "sft"),
                    help="split directory or a single jsonl file")
    ap.add_argument("--split", choices=("test", "dev", "train"), default="test")
    ap.add_argument("--model-size", choices=MODEL_SIZES, default="1.7b")
    ap.add_argument("--model", default="", help="served model name; defaults to qwen3-<size>-support-lora")
    ap.add_argument("--limit", type=int, default=0, help="evaluate the first N rows only")
    ap.add_argument("--out", default=str(ROOT / "out" / "support_adapter_eval.json"))
    ap.add_argument("--dry-run", action="store_true", help="print the first request payload and exit")
    args = ap.parse_args()

    rows = [json.loads(l) for l in resolve_data(args.data, args.split).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    model = args.model or SERVED_NAMES[args.model_size]
    plan = {
        "model_size": args.model_size,
        "served_model": model,
        "endpoint": args.endpoint,
        "split": args.split,
        "rows": len(rows),
        "labels": dict(Counter(r["label"] for r in rows)),
    }
    print(json.dumps(plan, ensure_ascii=False, indent=1))
    if args.dry_run:
        first = rows[0]
        print(json.dumps({
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": support_mod.PROMPT + "\n\n" + f"【引用句】{first['claim']}\n【证据片段】{first['evidence']}"},
            ],
            "model": model,
            "temperature": 0,
            "max_tokens": 40,
        }, ensure_ascii=False, indent=1)[:1200])
        print("[dry-run] no request sent.")
        return 0

    gold, pred, details = [], [], []
    started = time.time()
    for i, row in enumerate(rows):
        label, info = ask(args.endpoint, model, row)
        gold.append(row["label"])
        pred.append(label)
        details.append({"id": row["id"], "gold": row["label"], "pred": label, **info})
        print(i, row["label"], label, flush=True)
    result = macro_f1(gold, pred)
    result.update({
        "model_size": args.model_size,
        "model": model,
        "endpoint": args.endpoint,
        "data": str(resolve_data(args.data, args.split)),
        "split": args.split,
        "elapsed_sec": round(time.time() - started, 1),
        "errors": [(rows[i]["id"], gold[i], pred[i]) for i in range(len(rows)) if gold[i] != pred[i]],
        "request_errors": [d for d in details if d.get("error")],
        "predictions": details,
    })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json.dumps(result, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps({k: result[k] for k in ("macro_f1", "accuracy", "confusion", "n")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
