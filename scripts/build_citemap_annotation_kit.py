"""Build a single-primary-annotator kit with a 20% blind QC sheet.

Source: ``dist/citemap_audit_full/full_grid_105_optional.csv`` (105 cells,
already enriched with paper title/abstract and machine evidence).  The kit is:
  * ``main_105.csv`` — all cells, primary annotator, empty ``decision``;
  * ``qc_21.csv``   — 20% stratified sample, independent labeler, empty
    ``decision``; the primary annotator must not see this sheet.

Decisions: ``support`` / ``partial`` / ``no_evidence``;
see ``docs/citemap_annotation_rubric.md``.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

FIELDS = [
    "seq",
    "cell_id",
    "topic_id",
    "paper_id",
    "paper_title",
    "claim_id",
    "claim_text_zh",
    "cell_kind",
    "machine_stance",
    "evidence_quote",
    "evidence_locator",
    "paper_abstract",
    "decision",
    "confidence_1_5",
    "note",
]


def _read_grid(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "cell_id": row["cell_id"],
                "topic_id": row["topic_id"],
                "paper_id": row["paper_id"],
                "paper_title": row.get("paper_title", ""),
                "claim_id": row["claim_id"],
                "claim_text_zh": row.get("claim_text_zh", ""),
                "cell_kind": row.get("cell_kind", ""),
                "machine_stance": row.get("machine_stance", ""),
                "evidence_quote": row.get("evidence_quote", ""),
                "evidence_locator": row.get("evidence_locator", ""),
                "paper_abstract": (row.get("paper_abstract", "") or "")[:4000],
                "decision": "",
                "confidence_1_5": "",
                "note": "",
            }
        )
    return out


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build(grid_path: Path, out_dir: Path, seed: int = 20261115) -> dict:
    rows = _read_grid(grid_path)
    if len(rows) != 105:
        raise ValueError(f"expected 105 cells, got {len(rows)}")
    rng = random.Random(seed)
    by_topic: dict[str, list[dict]] = {}
    for row in rows:
        by_topic.setdefault(row["topic_id"], []).append(row)
    qc_ids: set[str] = set()
    for topic, items in sorted(by_topic.items()):
        items = list(items)
        rng.shuffle(items)
        qc_ids.update(c["cell_id"] for c in items[: max(1, round(len(items) * 0.2))])
    while len(qc_ids) < 21:
        qc_ids.add(rng.choice([r["cell_id"] for r in rows if r["cell_id"] not in qc_ids]))
    while len(qc_ids) > 21:
        qc_ids.pop()

    main_rows = list(rows)
    rng.shuffle(main_rows)
    for i, row in enumerate(main_rows, 1):
        row["seq"] = i
    qc_rows = [dict(r) for r in rows if r["cell_id"] in qc_ids]
    rng.shuffle(qc_rows)
    for i, row in enumerate(qc_rows, 1):
        row["seq"] = i

    _write(out_dir / "main_105.csv", main_rows)
    _write(out_dir / "qc_21.csv", qc_rows)
    readme = f"""# CiteMap 单人主标 + 20% 双盲复核包

- `main_105.csv`：主标注人，105 格，`decision` 留空。
- `qc_21.csv`：第二人独立复核的 21 格（20% 抽样，与 main 的 id 集合相同），不要让主标注人看。
- 判定只有三种：`support`（完整支持）、`partial`（部分支持）、`no_evidence`（无证据）。
- 标准见 `docs/citemap_annotation_rubric.md`。
- 两表都填完后运行：
  `python scripts/score_citemap_single_qc.py --main main_105.csv --qc qc_21.csv --out agreement.json`
- 本包由 {grid_path} 生成，seed={seed}；机器证据仅作参考，不是答案。
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    return {"main": len(main_rows), "qc": len(qc_rows), "qc_ids": sorted(qc_ids), "out": str(out_dir)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid-csv", default="dist/citemap_audit_full/full_grid_105_optional.csv")
    ap.add_argument("--out", default="dist/citemap_annotation")
    ap.add_argument("--seed", type=int, default=20261115)
    args = ap.parse_args()
    result = build(Path(args.grid_csv), Path(args.out), args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
