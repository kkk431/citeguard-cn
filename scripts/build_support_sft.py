"""Assemble the ClaimSupport-CN SFT splits (train/dev/test) for LoRA fine-tuning.

Source: the 100-item constructed benchmark + the 60-item disjoint extension.
Split policy (documented in the model card):
  - train = all 60 extension items + the first 20 official-dev items
  - dev   = the remaining 20 official-dev items
  - test  = the 60 official-test items (never seen in training)
The 100-set has no official train split (official dev 40 + test 60), so the
extension is the main training signal and half of dev is borrowed for training;
test stays untouched. All splits are labelled by construction, not by humans.
We say so in the model card.

Usage:
    python scripts/build_support_sft.py --out data/sft
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl"
EXT = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_ext.jsonl"
SPLIT = ROOT / "data" / "claimsupport_cn" / "split_seed20261024.json"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def slim(row: dict, split: str) -> dict:
    return {
        "id": row["id"],
        "claim": row["claim"],
        "evidence": row["evidence"][:1800],
        "label": row["label"],
        "split": split,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "sft"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    base = load(BASE)
    ext = load(EXT)
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    dev_ids = set(split["dev"])
    test_ids = set(split["test"])

    train, dev, test = [], [], []
    dev_pool = []
    for r in base:
        if r["id"] in dev_ids:
            dev_pool.append(r)
        elif r["id"] in test_ids:
            test.append(slim(r, "test"))
    dev_pool.sort(key=lambda r: r["id"])
    # The 100-set only ships dev+test; borrow half of dev for training so the
    # fine-tune has 80 examples instead of 60 extension-only rows.
    train += [slim(r, "train") for r in dev_pool[:20]]
    dev += [slim(r, "dev") for r in dev_pool[20:]]
    train += [slim(r, "train") for r in ext]

    for name, rows in (("train", train), ("dev", dev), ("test", test)):
        path = out / f"support_{name}.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(name, len(rows), path)

    meta = {
        "dataset": "ClaimSupport-CN SFT splits",
        "source": [str(BASE.relative_to(ROOT)), str(EXT.relative_to(ROOT))],
        "counts": {"train": len(train), "dev": len(dev), "test": len(test)},
        "labels": sorted({r["label"] for r in train + dev + test}),
        "note": "Labels are construction-based, not human-annotated; test split is the official 60 held-out items of the 100 set.",
    }
    (out / "support_sft.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
