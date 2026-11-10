"""QLoRA/LoRA fine-tune Qwen3-1.7B for 4-way citation-support classification.

Usage (on the GPU host):
    CUDA_VISIBLE_DEVICES=1 python scripts/train_support_lora.py \
        --model models/Qwen3-1.7B --data data/sft --out out/support_lora \
        --epochs 3 --eval-base

Outputs: adapter + tokenizer under OUT, metrics.json (test macro-F1 / accuracy /
confusion), eval_predictions.jsonl.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]
LABELS = ["support", "partial", "contradict", "no_evidence"]
SYS = (
    "你是学术引文核验员。判断【证据片段】是否支持【引用句】，四选一："
    "support（完全支持）、partial（部分支持）、contradict（矛盾）、no_evidence（证据不足）。"
    '只输出 JSON：{"label": "..."}。'
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def user_text(row: dict) -> str:
    return f"【引用句】{row['claim']}\n【证据片段】{row['evidence']}"


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


@torch.inference_mode()
def evaluate(model, tok, rows: list[dict], batch_size: int = 8, max_new_tokens: int = 24) -> tuple[list[str], list[str]]:
    model.eval()
    preds = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        prompts = [build_prompt(tok, r) for r in batch]
        enc = tok(prompts, return_tensors="pt", padding=True, truncation=True, max_length=2048).to(model.device)
        out = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tok.pad_token_id)
        gen = tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        preds.extend(parse_label(g) for g in gen)
    return [r["label"] for r in rows], preds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", default=str(ROOT / "data" / "sft"))
    ap.add_argument("--out", default=str(ROOT / "out" / "support_lora"))
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--seq-len", type=int, default=2048)
    ap.add_argument("--eval-base", action="store_true")
    args = ap.parse_args()
    data = Path(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"
    train_rows = read_jsonl(data / "support_train.jsonl")
    dev_rows = read_jsonl(data / "support_dev.jsonl")
    test_rows = read_jsonl(data / "support_test.jsonl")

    ds = Dataset.from_list([encode(tok, r, args.seq_len) for r in train_rows])
    base = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16, trust_remote_code=True).to("cuda")

    result = {"model": args.model, "train": len(train_rows), "dev": len(dev_rows), "test": len(test_rows), "epochs": args.epochs}
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

    targs = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
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
    )
    collator = DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100)
    trainer = Trainer(model=model, args=targs, train_dataset=ds, data_collator=collator)
    trainer.train()
    model.save_pretrained(out / "adapter")
    tok.save_pretrained(out / "adapter")

    gold, pred = evaluate(model, tok, dev_rows)
    result["dev"] = metrics(gold, pred)
    gold, pred = evaluate(model, tok, test_rows)
    result["test"] = metrics(gold, pred)
    (out / "eval_predictions.jsonl").write_text(
        "\n".join(json.dumps({"id": r["id"], "gold": g, "pred": p}, ensure_ascii=False) for r, g, p in zip(test_rows, gold, pred)) + "\n",
        encoding="utf-8",
    )
    (out / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
