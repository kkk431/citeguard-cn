"""LoRA / QLoRA fine-tune a Qwen3 model for 4-way citation-support classification.

The heavy stack (torch / transformers / peft / datasets) is imported lazily, so
``--dry-run`` works on a laptop without a GPU to sanity-check data and paths.

Usage (GPU host, one card per run):
    CUDA_VISIBLE_DEVICES=1 python scripts/train_support_lora.py \
        --model-size 4b --data data/sft --out out/support_lora_qwen3_4b \
        --epochs 3 --eval-base

    # laptop / CI: validate the data and the resolved model path, no torch needed
    python scripts/train_support_lora.py --model-size 4b --dry-run

Model resolution: ``--model`` wins if given (explicit path or HF id). Otherwise
``--models-dir/Qwen3-<SIZE>`` is used when that directory exists, else the HF id
from ``HF_IDS`` (e.g. ``Qwen/Qwen3-4B``).

Outputs under OUT: adapter/ (PEFT weights + tokenizer), metrics.json (test
macro-F1 / accuracy / confusion, dev, optional base), eval_predictions.jsonl,
run_meta.json (resolved model, data files, hyper-parameters, wall time, peak VRAM).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _utf8_stdout() -> None:
    """Windows consoles default to GBK, but the prompt contains '↔' / '【】'.

    Without this, ``--dry-run`` and log lines raise UnicodeEncodeError on a
    GBK console; reconfiguring the streams keeps the output readable anywhere.
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

LABELS = ["support", "partial", "contradict", "no_evidence"]
MODEL_SIZES = ("1.7b", "4b", "8b", "14b")
HF_IDS = {
    "1.7b": "Qwen/Qwen3-1.7B",
    "4b": "Qwen/Qwen3-4B",
    "8b": "Qwen/Qwen3-8B",
    "14b": "Qwen/Qwen3-14B",
}
SYS = (
    "你是学术引文核验员。判断【证据片段】是否支持【引用句】，四选一："
    "support（完全支持）、partial（部分支持）、contradict（矛盾）、no_evidence（证据不足）。"
    '只输出 JSON：{"label": "..."}。'
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_lf(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def user_text(row: dict) -> str:
    return f"【引用句】{row['claim']}\n【证据片段】{row['evidence']}"


def chat_prompt(messages: list[dict]) -> str:
    """Text form of the training conversation; mirrors what the tokenizer renders."""
    out = []
    for msg in messages:
        out.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
    return "".join(out) + "<|im_start|>assistant\n"


def build_prompt(tok, row: dict) -> str:
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": user_text(row)}]
    try:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def encode(tok, row: dict, max_len: int = 2048) -> dict:
    prompt = build_prompt(tok, row)
    answer = json.dumps({"label": row["label"]}, ensure_ascii=False)
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    a_ids = tok(answer + tok.eos_token, add_special_tokens=False)["input_ids"]
    ids = (p_ids + a_ids)[:max_len]
    labels = ([-100] * len(p_ids) + a_ids)[:max_len]
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": labels}


def parse_label(text: str) -> str:
    m = re.search(r'"label"\s*:\s*"([^"]+)"', text or "")
    if m and m.group(1) in LABELS:
        return m.group(1)
    for label in LABELS:
        if label in (text or ""):
            return label
    return "no_evidence"


def metrics(gold: list[str], pred: list[str]) -> dict:
    idx = {l: i for i, l in enumerate(LABELS)}
    cm = [[0] * 4 for _ in range(4)]
    for g, p in zip(gold, pred):
        cm[idx[g]][idx[p]] += 1
    f1s = []
    per = {}
    for i, l in enumerate(LABELS):
        tp = cm[i][i]
        fp = sum(cm[r][i] for r in range(4)) - tp
        fn = sum(cm[i]) - tp
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        f1s.append(f1)
        per[l] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4)}
    n = len(gold) or 1
    return {
        "macro_f1": round(sum(f1s) / 4, 4),
        "accuracy": round(sum(cm[i][i] for i in range(4)) / n, 4),
        "confusion": cm,
        "per_class": per,
        "n": len(gold),
    }


def evaluate(model, tok, rows: list[dict], batch_size: int = 8, max_new_tokens: int = 24) -> tuple[list[str], list[str]]:
    import torch

    model.eval()
    preds = []
    with torch.inference_mode():
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            prompts = [build_prompt(tok, r) for r in batch]
            enc = tok(prompts, return_tensors="pt", padding=True, truncation=True, max_length=2048).to(model.device)
            out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tok.pad_token_id)
            gen = tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
            preds.extend(parse_label(g) for g in gen)
    return [r["label"] for r in rows], preds


def resolve_model(args) -> str:
    if args.model:
        return args.model
    local = Path(args.models_dir) / f"Qwen3-{args.model_size.upper()}"
    if local.exists():
        return str(local)
    return HF_IDS[args.model_size]


def label_counts(rows: list[dict]) -> dict:
    counts = {label: 0 for label in LABELS}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    return counts


def load_data(data: Path, limit: int = 0) -> tuple[list[dict], list[dict], list[dict]]:
    missing = [name for name in ("train", "dev", "test") if not (data / f"support_{name}.jsonl").exists()]
    if missing:
        raise SystemExit(f"missing split files under {data}: {[f'support_{n}.jsonl' for n in missing]}")
    train = read_jsonl(data / "support_train.jsonl")
    dev = read_jsonl(data / "support_dev.jsonl")
    test = read_jsonl(data / "support_test.jsonl")
    if limit:
        train = train[:limit]
    return train, dev, test


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="explicit local path or HF id; overrides --model-size")
    ap.add_argument("--model-size", choices=MODEL_SIZES, default="1.7b",
                    help="Qwen3 size; 4b is the A3 target")
    ap.add_argument("--models-dir", default=str(ROOT / "models"),
                    help="local model root; Qwen3-<SIZE> subdirectory is preferred over the HF id")
    ap.add_argument("--data", default=str(ROOT / "data" / "sft"))
    ap.add_argument("--out", default=str(ROOT / "out" / "support_lora"))
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--seq-len", type=int, default=2048)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="train on the first N rows only (smoke tests)")
    ap.add_argument("--eval-base", action="store_true", help="evaluate the un-adapted base model on test first")
    ap.add_argument("--dry-run", action="store_true", help="validate data/model resolution and exit (no torch)")
    ap.add_argument("--seed", type=int, default=20261114)
    args = ap.parse_args()

    data = Path(args.data)
    out = Path(args.out)
    model_name = resolve_model(args)
    train_rows, dev_rows, test_rows = load_data(data, args.limit)

    plan = {
        "model_size": args.model_size,
        "model": model_name,
        "model_source": "explicit" if args.model else ("local_dir" if Path(model_name).exists() else "hf_id"),
        "data": str(data),
        "rows": {"train": len(train_rows), "dev": len(dev_rows), "test": len(test_rows)},
        "labels": {"train": label_counts(train_rows)},
        "epochs": args.epochs,
        "lr": args.lr,
        "seq_len": args.seq_len,
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "optimizer_steps": int((len(train_rows) / max(1, args.batch_size * args.grad_accum)) * args.epochs),
    }
    if len(train_rows) < 500 and not args.limit:
        print(f"[warn] train rows {len(train_rows)} < 500 - is this the expanded A3 split?")
    print(json.dumps(plan, ensure_ascii=False, indent=1))
    if args.dry_run:
        print("[dry-run] data and model path look consistent; nothing trained.")
        return 0

    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForSeq2Seq,
        Trainer,
        TrainingArguments,
    )

    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device visible - set CUDA_VISIBLE_DEVICES to a free card")

    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)
    started = time.time()

    tok = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"

    ds = Dataset.from_list([encode(tok, r, args.seq_len) for r in train_rows])
    base = AutoModelForCausalLM.from_pretrained(
        model_name, torch_dtype=torch.bfloat16, trust_remote_code=True
    ).to("cuda")

    result = {
        "model": model_name,
        "model_size": args.model_size,
        "train": len(train_rows),
        "dev": len(dev_rows),
        "test": len(test_rows),
        "epochs": args.epochs,
    }
    if args.eval_base:
        gold, pred = evaluate(base, tok, test_rows)
        result["base"] = metrics(gold, pred)
        print("base", json.dumps(result["base"], ensure_ascii=False))

    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(base, lora)
    model.print_trainable_parameters()
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    print(f"trainable: {n_trainable:,} / {n_total:,} ({n_trainable / n_total * 100:.4f}%)")

    targs = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=5,
        save_strategy="no",
        bf16=True,
        report_to=[],
        remove_unused_columns=False,
        gradient_checkpointing=False,
        optim="adamw_torch",
        seed=args.seed,
    )
    collator = DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100)
    trainer = Trainer(model=model, args=targs, train_dataset=ds, data_collator=collator)
    train_started = time.time()
    trainer.train()
    train_seconds = time.time() - train_started
    model.save_pretrained(out / "adapter")
    tok.save_pretrained(out / "adapter")

    gold, pred = evaluate(model, tok, dev_rows)
    result["dev"] = metrics(gold, pred)
    gold, pred = evaluate(model, tok, test_rows)
    result["test"] = metrics(gold, pred)
    write_lf(
        out / "eval_predictions.jsonl",
        "\n".join(
            json.dumps({"id": r["id"], "gold": g, "pred": p}, ensure_ascii=False)
            for r, g, p in zip(test_rows, gold, pred)
        ) + "\n",
    )
    write_lf(out / "metrics.json", json.dumps(result, ensure_ascii=False, indent=1))

    gpu = torch.cuda.get_device_properties(0)
    run_meta = {
        **plan,
        "seed": args.seed,
        "trainable_params": f"{n_trainable:,} / {n_total:,} ({n_trainable / n_total * 100:.4f}%)",
        "trainable_params_raw": {"trainable": n_trainable, "total": n_total},
        "started_at": dt.datetime.fromtimestamp(started, dt.timezone.utc).isoformat(timespec="seconds"),
        "train_seconds": round(train_seconds, 1),
        "total_seconds": round(time.time() - started, 1),
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1024 ** 3, 2),
        "gpu": {"name": gpu.name, "total_vram_gb": round(gpu.total_memory / 1024 ** 3, 2)},
        "train_loss": [entry["loss"] for entry in trainer.state.log_history if "loss" in entry][-5:],
        "outputs": {"adapter": str(out / "adapter"), "metrics": str(out / "metrics.json")},
    }
    write_lf(out / "run_meta.json", json.dumps(run_meta, ensure_ascii=False, indent=1))
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
