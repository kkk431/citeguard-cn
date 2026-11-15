"""Score a single-primary-annotator CiteMap sheet against a blind QC subset."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

DECISIONS = ("support", "partial", "no_evidence")
LABELS = {"support": "完整支持", "partial": "部分支持", "no_evidence": "无证据"}


def read_sheet(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out: dict[str, str] = {}
    for row in rows:
        cell = (row.get("cell_id") or "").strip()
        decision = (row.get("decision") or "").strip().lower()
        if not cell:
            continue
        if decision and decision not in DECISIONS:
            raise ValueError(f"{path}: invalid decision {decision!r} for {cell}")
        out[cell] = decision
    return out


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    expected = sum((ca[k] / n) * (cb[k] / n) for k in DECISIONS)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def score(main: dict[str, str], qc: dict[str, str], min_overlap: int = 10) -> dict:
    overlap = sorted(
        cell
        for cell in qc
        if cell in main and main[cell] and qc[cell]
    )
    if len(overlap) < min_overlap:
        raise ValueError(f"only {len(overlap)} completed overlapping cells (need {min_overlap})")
    pairs = [(main[c], qc[c]) for c in overlap]
    observed = sum(a == b for a, b in pairs) / len(pairs)
    confused = Counter(pairs)
    per_class = {}
    for label in DECISIONS:
        tp = sum(1 for a, b in pairs if a == label and b == label)
        fp = sum(1 for a, b in pairs if a != label and b == label)
        fn = sum(1 for a, b in pairs if a == label and b != label)
        per_class[label] = {
            "label_zh": LABELS[label],
            "main_count": sum(1 for a, _ in pairs if a == label),
            "qc_count": sum(1 for _, b in pairs if b == label),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
    main_done = sum(1 for cell in main if main[cell])
    qc_done = sum(1 for cell in qc if qc[cell])
    return {
        "main_cells": len(main),
        "main_completed": main_done,
        "qc_cells": len(qc),
        "qc_completed": qc_done,
        "overlap_completed": len(pairs),
        "agreement": round(observed, 4),
        "cohen_kappa": None if kappa(pairs) is None else round(kappa(pairs), 4),
        "confusion": {f"{a}->{b}": v for (a, b), v in sorted(confused.items())},
        "per_class": per_class,
        "note": "单人主标 + 20% 双盲复核；一致性只在这 21 格上计算，不是全量信度。",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", required=True)
    ap.add_argument("--qc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-overlap", type=int, default=10)
    args = ap.parse_args()
    result = score(read_sheet(Path(args.main)), read_sheet(Path(args.qc)), args.min_overlap)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
