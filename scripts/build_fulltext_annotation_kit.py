"""Build a human review kit for the 24 full-text CiteMap evidence items.

Outputs:
  * ``main_24.csv`` — all full-text evidence, empty ``decision``;
  * ``qc_5.csv``   — 20% deterministic QC subset, empty ``decision``;
  * ``README.md``.

Decisions: ``support`` / ``partial`` / ``no_evidence``; see
``docs/citemap_annotation_rubric.md``.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

FIELDS = [
    "seq",
    "evidence_id",
    "topic_id",
    "paper_id",
    "paper_title",
    "atomic_id",
    "claim_text_zh",
    "machine_stance",
    "machine_verdict",
    "evidence_quote",
    "evidence_locator",
    "decision",
    "confidence_1_5",
    "note",
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _claim_texts(path: Path) -> dict[str, str]:
    raw = _load(path)
    out: dict[str, str] = {}
    for topic in raw.get("topics", {}).values():
        for claim in topic.get("claims", []):
            out[claim["atomic_id"]] = claim.get("text", "")
    return out


def _paper_titles(data_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for topic in ("ai_education", "medical_imaging"):
        corpus = _load(data_dir / "corpus" / f"{topic}.json")
        for paper in corpus["papers"]:
            out[paper["paper_id"]] = paper.get("title", "")
    return out


def build(data_dir: Path, out_dir: Path, seed: int = 20261115) -> dict:
    claims = _claim_texts(data_dir / "claims_atomic.json")
    titles = _paper_titles(data_dir)
    rows: list[dict] = []
    for topic in ("ai_education", "medical_imaging"):
        raw = _load(data_dir / "extractions_fulltext" / f"{topic}.json")
        for ev in raw.get("evidence", []):
            atomic = ev.get("atomic_id", "")
            rows.append(
                {
                    "evidence_id": ev["evidence_id"],
                    "topic_id": topic,
                    "paper_id": ev.get("paper_id", ""),
                    "paper_title": titles.get(ev.get("paper_id", ""), ""),
                    "atomic_id": atomic,
                    "claim_text_zh": claims.get(atomic, ""),
                    "machine_stance": ev.get("stance", ""),
                    "machine_verdict": ev.get("fulltext_verdict", ""),
                    "evidence_quote": ev.get("quote", ""),
                    "evidence_locator": ev.get("locator", ""),
                    "decision": "",
                    "confidence_1_5": "",
                    "note": "",
                }
            )
    if len(rows) != 24:
        raise ValueError(f"expected 24 full-text evidence rows, got {len(rows)}")
    rng = random.Random(seed)
    rng.shuffle(rows)
    for i, row in enumerate(rows, 1):
        row["seq"] = i
    qc = rng.sample(rows, 5)
    for i, row in enumerate(qc, 1):
        row["seq"] = i
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("main_24.csv", rows), ("qc_5.csv", qc)):
        with (out_dir / name).open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(data)
    readme = f"""# CiteMap 全文证据人工复核（24 条）

- `main_24.csv`：主标注人，24 条全文证据，`decision` 留空；
- `qc_5.csv`：第二人独立复核的 5 条（20%），不要给主标注人看；
- 判定：`support` / `partial` / `no_evidence`；标准见 `docs/citemap_annotation_rubric.md`；
- 机器列（stance/verdict）仅为参考，不是答案；
- 24 条约 30–40 分钟，QC 5 条约 10 分钟；
- 两份都填完后运行：
  `python scripts/score_citemap_single_qc.py --main main_24.csv --qc qc_5.csv --min-overlap 5 --out agreement.json`

数据源：`data/evidence_map/extractions_fulltext/*.json`（{data_dir}），seed={seed}。
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    return {"main": len(rows), "qc": len(qc), "out": str(out_dir)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/evidence_map")
    ap.add_argument("--out", default="dist/fulltext_annotation")
    ap.add_argument("--seed", type=int, default=20261115)
    args = ap.parse_args()
    print(json.dumps(build(Path(args.data_dir), Path(args.out), args.seed), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
