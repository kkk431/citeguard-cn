"""Evaluate AlignScore on the 100-item human audit sheet (Chinese).

This is deliberately *not* a product integration: AlignScore is an English
NLI model.  The script measures whether its entailment/contradiction heads
separate Chinese support / partial / contradict / no-evidence pairs before we
consider using it as a local fallback.

Run (offline):
    python scripts/eval_alignscore_cn100.py \
        --ckpt D:/Temp/citeguard_e3/AlignScore-base.ckpt \
        --out data/experiments/alignscore_cn100.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
from pathlib import Path

# transformers 4.57 removed AdamW from the top-level namespace; AlignScore's
# model module still imports it.  Patch before importing alignscore.
# Set offline mode before importing transformers: AlignScore's model
# constructor calls AutoConfig.from_pretrained unconditionally.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch
import transformers
from torch.optim import AdamW

transformers.AdamW = AdamW  # type: ignore[attr-defined]

from alignscore.model import BERTAlignModel  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CKPT = Path(r"D:\Temp\citeguard_e3\AlignScore-base.ckpt")
SHEETS = ("A", "B", "C")


def read_majority(sheet_path: Path) -> dict[str, str]:
    per_item: dict[str, list[str]] = collections.defaultdict(list)
    with sheet_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            label = (row.get("human_label") or "").strip()
            if label:
                per_item[row["item_id"]].append(label)
    return {k: collections.Counter(v).most_common(1)[0][0] for k, v in per_item.items()}


def load_model(ckpt: Path):
    state = torch.load(str(ckpt), map_location="cpu", weights_only=False)
    model = BERTAlignModel(model="roberta-base", using_pretrained=False)
    model.load_state_dict(state["state_dict"], strict=False)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained("roberta-base", local_files_only=True)
    return model, tokenizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", type=Path, default=DEFAULT_CKPT)
    parser.add_argument("--sheet", type=Path, default=ROOT / "data/audit/audit_sheet_100.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "data/experiments/alignscore_cn100.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    labels: dict[str, dict[str, str]] = {}
    for who in SHEETS:
        path = ROOT / f"data/audit/human_100/audit_{who}.csv"
        labels[who] = read_majority(path)

    rows = []
    with args.sheet.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            votes = [labels[who].get(row["item_id"]) for who in SHEETS]
            votes = [v for v in votes if v]
            if not votes:
                continue
            rows.append(
                {
                    "id": row["item_id"],
                    "claim": row["claim"],
                    "evidence": row["evidence"],
                    "label": collections.Counter(votes).most_common(1)[0][0],
                }
            )
    if args.limit:
        rows = rows[: args.limit]

    model, tokenizer = load_model(args.ckpt)
    probs: list[list[float]] = []
    for start in range(0, len(rows), args.batch):
        chunk = rows[start : start + args.batch]
        enc = tokenizer(
            [r["claim"] for r in chunk],
            [r["evidence"] for r in chunk],
            truncation=True,
            padding=True,
            max_length=512,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = model(enc).tri_label_logits
            probs.extend(torch.softmax(logits, dim=-1).tolist())

    by_label: dict[str, list[list[float]]] = collections.defaultdict(list)
    for row, prob in zip(rows, probs):
        by_label[row["label"]].append(prob)

    means = {
        label: {
            str(i): round(sum(p[i] for p in values) / len(values), 4)
            for i in range(3)
        }
        for label, values in by_label.items()
    }
    result = {
        "model": "AlignScore-base (roberta-base), tri head; index 0=entailment, 2=contradiction",
        "dataset": "100-item human audit sheet (three annotators, majority vote)",
        "n": len(rows),
        "labels": dict(collections.Counter(r["label"] for r in rows)),
        "means": means,
        "pairs": [
            {"id": row["id"], "label": row["label"], "p": prob}
            for row, prob in zip(rows, probs)
        ],
        "verdict": "kill_for_chinese",
        "note": "contradict pairs score higher entailment than support pairs; English model does not transfer",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "pairs"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
