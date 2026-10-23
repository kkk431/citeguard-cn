"""Evaluate ClaimSupport-CN with a *local open-source* model (CPU, transformers).

Why: the competition rubric asks for a clear account of which open-source
resources are essential to the AI feature. The production judge can target any
OpenAI-compatible endpoint, including a local Qwen3 server; this script measures
the same 4-way support task with a local Qwen3 model, fully offline after the
model download, so the claim "可换成本地开源模型" is backed by numbers.

Usage:
    python scripts/eval_support_local.py --model Qwen/Qwen3-1.7B --limit 20
    python scripts/eval_support_local.py --model Qwen/Qwen3-1.7B --limit 100
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DATASET = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl"
LABELS = ["support", "partial", "contradict", "no_evidence"]


def load_rows(limit: int = 0) -> list[dict]:
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def metrics(rows: list[dict], preds: list[str]) -> dict:
    index = {label: i for i, label in enumerate(LABELS)}
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for r, p in zip(rows, preds):
        matrix[index[r["label"]]][index[p]] += 1
    f1s, per = [], {}
    for i, label in enumerate(LABELS):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(LABELS))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1s.append(f1)
        per[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
    n = len(rows) or 1
    return {
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "accuracy": round(sum(matrix[i][i] for i in range(len(LABELS))) / n, 4),
        "confusion": matrix,
        "per_class": per,
    }


def parse_label(text: str) -> str:
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            label = data.get("label", "no_evidence")
            return label if label in LABELS else "no_evidence"
        except Exception:
            pass
    for label in LABELS:
        if label in (text or ""):
            return label
    return "no_evidence"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-1.7B")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--max-new-tokens", type=int, default=300)
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--prompt-file", default=str(ROOT / "scripts" / "support_prompt_v3.txt"))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(args.threads)
    slug = args.model.replace("/", "_").replace(".", "_")
    out_path = Path(args.out) if args.out else ROOT / "data" / "experiments" / f"support_local_{slug}.json"
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    rows = load_rows(args.limit)

    print(f"[1/3] loading {args.model} on CPU (threads={args.threads})", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=torch.float32, low_cpu_mem_usage=True, trust_remote_code=True
    )
    model.eval()

    preds: list[str] = []
    details: list[dict] = []
    started = time.time()
    print(f"[2/3] judging {len(rows)} items", flush=True)
    for i, row in enumerate(rows, 1):
        user = prompt + f"\n\n【引用句】{row['claim']}\n【证据片段】{row['evidence']}"
        messages = [
            {"role": "system", "content": "你是严谨的学术引文核验员。"},
            {"role": "user", "content": user},
        ]
        try:
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
        except TypeError:
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        reply = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        label = parse_label(reply)
        preds.append(label)
        details.append(
            {
                "id": row.get("id"),
                "gold": row["label"],
                "pred": label,
                "reply": reply[:800],
            }
        )
        elapsed = time.time() - started
        print(
            f"  {i}/{len(rows)} gold={row['label']:<13} pred={label:<13} "
            f"({elapsed / i:.1f}s/item)",
            flush=True,
        )

    result = metrics(rows, preds)
    result.update(
        {
            "n": len(rows),
            "model": args.model,
            "backend": "transformers-cpu",
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            "max_new_tokens": args.max_new_tokens,
            "elapsed_sec": round(time.time() - started, 1),
            "dry_run": args.limit < 100,
            "details": details,
        }
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[3/3] result:")
    print(json.dumps({k: result[k] for k in ("macro_f1", "accuracy", "n", "model", "elapsed_sec")}, ensure_ascii=False))
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
