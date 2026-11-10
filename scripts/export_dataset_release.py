"""Build the redistributable ClaimSupport-CN release (300 items).

Merges the three construction batches, checks id/source hygiene, and writes:

- ``data/claimsupport_cn/claimsupport_cn_300.jsonl``
- ``data/claimsupport_cn/claimsupport_cn_300.stats.json``

The annotation labels are rule-constructed, not human labels; the card says so.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "claimsupport_cn"
BATCHES = [
    ("v1", DATA / "claimsupport_cn.jsonl"),
    ("ext", DATA / "claimsupport_cn_ext.jsonl"),
    ("v2", DATA / "claimsupport_cn_v2.jsonl"),
]
OUT = DATA / "claimsupport_cn_300.jsonl"
STATS = DATA / "claimsupport_cn_300.stats.json"
LABELS = ("support", "partial", "contradict", "no_evidence")


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def source_work(row: dict, field: str) -> str:
    src = row.get(field) or {}
    return str(src.get("openalex_id") or src.get("doi") or src.get("title") or "")


def main() -> None:
    merged: list[dict] = []
    seen_ids: set[str] = set()
    per_batch: dict[str, int] = {}
    for batch, path in BATCHES:
        rows = load(path)
        per_batch[batch] = len(rows)
        for row in rows:
            rid = str(row.get("id") or "")
            if not rid:
                raise SystemExit(f"{path}: row without id")
            if rid in seen_ids:
                raise SystemExit(f"duplicate id: {rid}")
            seen_ids.add(rid)
            row = dict(row)
            row["batch"] = batch
            if row.get("label") not in LABELS:
                raise SystemExit(f"{rid}: bad label {row.get('label')!r}")
            merged.append(row)

    # No work may appear in more than one batch, except the deliberate
    # no_evidence pairing (claim source != evidence source).
    batch_works: dict[str, set[str]] = {}
    for row in merged:
        batch_works.setdefault(row["batch"], set()).add(source_work(row, "claim_source"))
        batch_works.setdefault(row["batch"], set()).add(source_work(row, "evidence_source"))
    batches = sorted(batch_works)
    for i, left in enumerate(batches):
        for right in batches[i + 1 :]:
            shared = batch_works[left] & batch_works[right]
            if shared:
                raise SystemExit(f"{left}/{right} share {len(shared)} source works")

    merged.sort(key=lambda r: str(r["id"]))
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in merged) + "\n"
    OUT.write_text(payload, encoding="utf-8")

    labels = Counter(r["label"] for r in merged)
    constructions = Counter(str(r.get("construction", "")).split(":")[0] for r in merged)
    years = Counter(
        (r.get("claim_source") or {}).get("year") for r in merged
    )
    stats = {
        "name": "ClaimSupport-CN",
        "version": "2026-11-11",
        "items": len(merged),
        "labels": {k: labels.get(k, 0) for k in LABELS},
        "batches": per_batch,
        "construction_families": dict(constructions),
        "claim_year_range": [
            min(y for y in years if isinstance(y, int)),
            max(y for y in years if isinstance(y, int)),
        ],
        "unique_source_works": len(
            {source_work(r, f) for r in merged for f in ("claim_source", "evidence_source")}
        ),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "labels_are": "rule-constructed, not human annotations",
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
