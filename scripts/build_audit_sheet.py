"""Build a blind human-audit sheet for ClaimSupport-CN.

Stratified sample (by gold label) from the 100-item set and the 60-item
extension. The CSV an annotator sees has no labels; the answer key stays in
a separate JSON file so the sample stays blind.

    python scripts/build_audit_sheet.py --n 60 --seed 20261111
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl"
EXT = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_ext.jsonl"
V2 = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_v2.jsonl"
OUT_DIR = ROOT / "data" / "audit"

LABELS = ["support", "partial", "contradict", "no_evidence"]


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def stratified(rows: list[dict], n: int, rng: random.Random) -> list[dict]:
    buckets: dict[str, list[dict]] = {label: [] for label in LABELS}
    for row in rows:
        buckets.setdefault(row["label"], []).append(row)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    total = sum(len(b) for b in buckets.values())
    picked: list[dict] = []
    # proportional allocation, then fill up to n from the largest remainder
    raw = {k: n * len(v) / total for k, v in buckets.items()}
    quota = {k: int(raw[k]) for k in buckets}
    for k in sorted(buckets, key=lambda k: raw[k] - quota[k], reverse=True):
        if sum(quota.values()) >= n:
            break
        quota[k] += 1
    for label, q in quota.items():
        picked.extend(buckets[label][:q])
    rng.shuffle(picked)
    return picked[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    rows = []
    for path in (BASE, EXT, V2):
        if path.exists():
            for row in load(path):
                row.setdefault("_set", path.stem)
                rows.append(row)
    if not rows:
        raise SystemExit("no ClaimSupport-CN rows found")

    rng = random.Random(args.seed)
    sample = stratified(rows, args.n, rng)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sheet = out_dir / "audit_sheet.csv"
    with sheet.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["item_id", "claim", "evidence", "source_title",
             "human_label", "confidence_1_5", "note"]
        )
        for i, row in enumerate(sample, start=1):
            writer.writerow([
                f"HS{i:03d}", row.get("claim", ""), row.get("evidence", ""),
                row.get("source_title", ""), "", "", "",
            ])

    key = {
        "seed": args.seed,
        "n": len(sample),
        "labels": {
            f"HS{i:03d}": {
                "label": row["label"],
                "set": row.get("_set", ""),
                "source_url": row.get("source_url", ""),
            }
            for i, row in enumerate(sample, start=1)
        },
    }
    (out_dir / "audit_key.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    counts = {label: sum(1 for r in sample if r["label"] == label) for label in LABELS}
    print(f"wrote {sheet} ({len(sample)} items)")
    print("label counts:", counts)


if __name__ == "__main__":
    main()
