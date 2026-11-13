"""Extend the 60-item human audit sample to 100 items.

Keeps HS001-HS060 exactly as distributed, adds 40 items (HS061-HS100) so the
label mix is proportional to the 300-item ClaimSupport-CN release:
support 40 / partial 27 / contradict 17 / no_evidence 16.

New items must not reuse a source work already present in the first 60, so the
audit sample stays work-disjoint at the source level.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl"
EXT = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_ext.jsonl"
V2 = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_v2.jsonl"
OLD_SHEET = ROOT / "data" / "audit" / "audit_sheet.csv"
OLD_KEY = ROOT / "data" / "audit" / "audit_key.json"
OUT_SHEET = ROOT / "data" / "audit" / "audit_sheet_100.csv"
OUT_KEY = ROOT / "data" / "audit" / "audit_key_100.json"

LABELS = ("support", "partial", "contradict", "no_evidence")
TARGET = {"support": 40, "partial": 27, "contradict": 17, "no_evidence": 16}


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def source_id(row: dict) -> str:
    src = row.get("claim_source") or {}
    return str(src.get("openalex_id") or "")


def main() -> int:
    pool: list[dict] = []
    for path in (BASE, EXT, V2):
        if path.exists():
            for row in load(path):
                row["_set"] = path.stem
                pool.append(row)

    old_rows = list(csv.DictReader(OLD_SHEET.open(encoding="utf-8-sig", newline="")))
    old_claims = {row["claim"].strip() for row in old_rows}
    old_key = json.loads(OLD_KEY.read_text(encoding="utf-8"))
    old_labels = {item: value["label"] for item, value in old_key["labels"].items()}

    by_claim: dict[str, list[dict]] = {}
    for row in pool:
        by_claim.setdefault(row["claim"].strip(), []).append(row)

    used_sources: set[str] = set()
    old_selected: list[dict] = []
    missing = []
    for row in old_rows:
        claim = row["claim"].strip()
        matches = by_claim.get(claim, [])
        if not matches:
            missing.append(row["item_id"])
            continue
        old_selected.append(matches[0])
        sid = source_id(matches[0])
        if sid:
            used_sources.add(sid)
    if missing:
        raise SystemExit(f"could not map {len(missing)} old items back to the pool: {missing[:5]}")
    if len(old_selected) != 60:
        raise SystemExit(f"expected 60 old items, mapped {len(old_selected)}")

    counts = Counter(old_labels.values())
    needed = {label: TARGET[label] - counts.get(label, 0) for label in LABELS}
    if any(value < 0 for value in needed.values()):
        raise SystemExit(f"old sample already exceeds target: {needed}")

    rng = random.Random(20261114)
    candidates: dict[str, list[dict]] = {label: [] for label in LABELS}
    for row in pool:
        if row["claim"].strip() in old_claims:
            continue
        sid = source_id(row)
        if sid and sid in used_sources:
            continue
        candidates.setdefault(row["label"], []).append(row)
    for bucket in candidates.values():
        rng.shuffle(bucket)

    picked: list[dict] = []
    for label in LABELS:
        take = needed[label]
        if len(candidates[label]) < take:
            raise SystemExit(f"not enough {label} candidates: need {take}, have {len(candidates[label])}")
        picked.extend(candidates[label][:take])
    rng.shuffle(picked)

    # New items appended after HS060, in a stable random order.
    new_rows = []
    for offset, row in enumerate(picked, start=61):
        new_rows.append(
            {
                "item_id": f"HS{offset:03d}",
                "claim": row.get("claim", ""),
                "evidence": row.get("evidence", ""),
                "source_title": "",
                "human_label": "",
                "confidence_1_5": "",
                "note": "",
                "_label": row["label"],
                "_set": row.get("_set", ""),
                "_source": source_id(row),
            }
        )

    all_rows = [
        {
            "item_id": row["item_id"],
            "claim": row["claim"],
            "evidence": row["evidence"],
            "source_title": "",
            "human_label": "",
            "confidence_1_5": "",
            "note": "",
            "_label": old_labels[row["item_id"]],
            "_set": "",
            "_source": "",
        }
        for row in old_rows
    ] + new_rows

    with OUT_SHEET.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["item_id", "claim", "evidence", "source_title", "human_label", "confidence_1_5", "note"],
        )
        writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})

    key = {
        "seed": 20261114,
        "n": len(all_rows),
        "labels": {
            row["item_id"]: {
                "label": row["_label"],
                "set": row["_set"],
                "source_url": row["_source"],
            }
            for row in all_rows
        },
    }
    OUT_KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT_SHEET, len(all_rows))
    print("labels", dict(Counter(row["_label"] for row in all_rows)))
    print("new", len(new_rows), "needed", needed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
