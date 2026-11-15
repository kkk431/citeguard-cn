"""Build offline CSV packs for CiteMap human verification.

The 60-cell packet produced by ``build_citemap_verification.py`` is the
sampled audit.  This script turns it into reviewer-friendly CSV files and an
optional full 105-cell grid.  Reviewer files never contain the machine
``verified`` flag as an answer; the organizer key is written separately.

Usage:
    python scripts/build_citemap_audit_csv.py --out dist/citemap_audit
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date
from pathlib import Path

TOPICS = ("ai_education", "medical_imaging")
REVIEWER_IDS = ("A", "B", "C")
COLUMNS = [
    "seq",
    "cell_id",
    "reviewer_id",
    "topic_id",
    "topic_name_zh",
    "paper_id",
    "paper_title",
    "paper_year",
    "doi",
    "openalex_id",
    "claim_id",
    "claim_text_zh",
    "cell_kind",
    "machine_stance",
    "machine_confidence",
    "evidence_quote",
    "evidence_locator",
    "machine_summary_zh",
    "machine_method",
    "machine_sample",
    "paper_abstract",
    "verify_verdict",
    "issue_type",
    "verify_note",
    "reviewer_confidence_1_5",
]


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _paper_index(corpus: dict) -> dict:
    return {p["paper_id"]: p for p in corpus["papers"]}


def _claim_index(extractions: dict) -> dict:
    return {c["claim_id"]: c for c in extractions["claims"]}


def _abstract_index(path: Path) -> dict:
    raw = _read_json(path)
    out: dict[str, str] = {}
    for work_id, row in raw.items():
        if isinstance(row, dict):
            out[work_id] = row.get("abstract", "") or ""
    return out


def _base_row(
    topic_id: str,
    topic_name: str,
    paper: dict,
    claim: dict,
    abstract: str,
) -> dict:
    return {
        "topic_id": topic_id,
        "topic_name_zh": topic_name,
        "paper_id": paper["paper_id"],
        "paper_title": paper.get("title", ""),
        "paper_year": paper.get("year", ""),
        "doi": paper.get("doi", ""),
        "openalex_id": paper.get("openalex_id", ""),
        "claim_id": claim["claim_id"],
        "claim_text_zh": claim.get("text", ""),
        "paper_abstract": abstract,
        "verify_verdict": "",
        "issue_type": "",
        "verify_note": "",
        "reviewer_confidence_1_5": "",
    }


def _machine_fields(row: dict, ev: dict | None) -> None:
    if ev:
        row.update(
            {
                "cell_kind": "机器证据",
                "machine_stance": ev.get("stance", ""),
                "machine_confidence": ev.get("confidence", ""),
                "evidence_quote": ev.get("quote", ""),
                "evidence_locator": ev.get("locator", ""),
                "machine_summary_zh": ev.get("summary", ""),
                "machine_method": ev.get("method", ""),
                "machine_sample": ev.get("sample", ""),
            }
        )
        return
    row.update(
        {
            "cell_kind": "无机器证据",
            "machine_stance": "",
            "machine_confidence": "",
            "evidence_quote": "",
            "evidence_locator": "",
            "machine_summary_zh": "",
            "machine_method": "",
            "machine_sample": "",
        }
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _shuffle(rows: list[dict], reviewer: str, seed: int) -> list[dict]:
    rng = random.Random(f"{seed}-{reviewer}")
    out = list(rows)
    rng.shuffle(out)
    for i, row in enumerate(out, 1):
        row["seq"] = i
        row["reviewer_id"] = reviewer
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/evidence_map")
    ap.add_argument("--out", default="dist/citemap_audit")
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument(
        "--grid",
        choices=["sampled", "full"],
        default="sampled",
        help="reviewer files use the 60-cell stratified sample (default) or the full 105-cell grid",
    )
    args = ap.parse_args()

    data = Path(args.data_dir)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    abstracts = _abstract_index(data / "abstracts.json")
    packet = _read_json(data / "verification_packet.json")
    packet_by_id = {c["cell_id"]: c for c in packet["cells"]}

    topics: list[dict] = []
    auto_by_key: dict[tuple[str, str], list[dict]] = {}
    auto_by_id: dict[str, dict] = {}
    for topic_id in TOPICS:
        corpus = _read_json(data / "corpus" / f"{topic_id}.json")
        manual = _read_json(data / "extractions" / f"{topic_id}.json")
        auto = _read_json(data / "extractions_auto" / f"{topic_id}.json")
        topics.append(
            {
                "topic_id": topic_id,
                "topic": corpus["topic"],
                "papers": _paper_index(corpus),
                "claims": _claim_index(manual),
            }
        )
        for ev in auto.get("evidence", []):
            auto_by_id[ev["evidence_id"]] = ev
            auto_by_key.setdefault((ev["paper_id"], ev["claim_id"]), []).append(ev)

    # ---- sampled packet rows ------------------------------------------------
    sampled: list[dict] = []
    for cell in packet["cells"]:
        topic = next(t for t in topics if t["topic_id"] == cell["topic_id"])
        paper = topic["papers"][cell["paper_id"]]
        claim = topic["claims"][cell["claim_id"]]
        ev = auto_by_id.get(cell.get("evidence_id", ""))
        row = _base_row(
            cell["topic_id"],
            topic["topic"]["name_zh"],
            paper,
            claim,
            abstracts.get(paper.get("openalex_id", ""), ""),
        )
        row["cell_id"] = cell["cell_id"]
        _machine_fields(row, ev)
        # Packet cells are authoritative about the sampled kind.
        if cell.get("kind") == "no-evidence":
            _machine_fields(row, None)
        sampled.append(row)

    for reviewer in REVIEWER_IDS:
        rows = _shuffle([dict(r) for r in sampled], reviewer, args.seed)
        _write_csv(out / f"reviewer_{reviewer}.csv", rows)

    # ---- full grid (105 cells: 15 papers x claims per topic) ----------------
    full: list[dict] = []
    for topic in topics:
        topic_id = topic["topic_id"]
        topic_name = topic["topic"]["name_zh"]
        for paper_id, paper in topic["papers"].items():
            for claim_id, claim in topic["claims"].items():
                row = _base_row(
                    topic_id,
                    topic_name,
                    paper,
                    claim,
                    abstracts.get(paper.get("openalex_id", ""), ""),
                )
                candidates = auto_by_key.get((paper_id, claim_id), [])
                ev = candidates[0] if candidates else None
                row["cell_id"] = f"full-{topic_id}-{paper_id}-{claim_id}"
                _machine_fields(row, ev)
                full.append(row)
    _write_csv(out / "full_grid_105_optional.csv", _shuffle(full, "FULL", args.seed))

    if args.grid == "full":
        for reviewer in REVIEWER_IDS:
            rows = _shuffle([dict(r) for r in full], reviewer, args.seed)
            _write_csv(out / f"reviewer_{reviewer}.csv", rows)
        reviewer_cells = len(full)
    else:
        reviewer_cells = len(sampled)

    # ---- organizer key ------------------------------------------------------
    key_cols = [
        "cell_id",
        "topic_id",
        "paper_id",
        "claim_id",
        "cell_kind",
        "machine_stance",
        "machine_confidence",
        "evidence_id",
        "evidence_quote",
        "sampled_60",
        "full_grid_105",
    ]
    if args.grid == "full":
        key_rows = [
            {
                "cell_id": row["cell_id"],
                "topic_id": row["topic_id"],
                "paper_id": row["paper_id"],
                "claim_id": row["claim_id"],
                "cell_kind": row["cell_kind"],
                "machine_stance": row["machine_stance"],
                "machine_confidence": row["machine_confidence"],
                "evidence_id": "",
                "evidence_quote": row["evidence_quote"],
                "sampled_60": "",
                "full_grid_105": "1",
            }
            for row in full
        ]
    else:
        key_rows = []
        for row in sampled:
            cell = packet_by_id[row["cell_id"]]
            key_rows.append(
                {
                    "cell_id": row["cell_id"],
                    "topic_id": row["topic_id"],
                    "paper_id": row["paper_id"],
                    "claim_id": row["claim_id"],
                    "cell_kind": row["cell_kind"],
                    "machine_stance": row["machine_stance"],
                    "machine_confidence": row["machine_confidence"],
                    "evidence_id": cell.get("evidence_id", ""),
                    "evidence_quote": row["evidence_quote"],
                    "sampled_60": "1",
                    "full_grid_105": "0",
                }
            )
        for row in full:
            if row["cell_id"] in packet_by_id:
                continue
            key_rows.append(
                {
                    "cell_id": row["cell_id"],
                    "topic_id": row["topic_id"],
                    "paper_id": row["paper_id"],
                    "claim_id": row["claim_id"],
                    "cell_kind": row["cell_kind"],
                    "machine_stance": row["machine_stance"],
                    "machine_confidence": row["machine_confidence"],
                    "evidence_id": "",
                    "evidence_quote": row["evidence_quote"],
                    "sampled_60": "0",
                    "full_grid_105": "1",
                }
            )
    with (out / "_organizer_only_key.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as fh:
        writer = csv.DictWriter(fh, fieldnames=key_cols)
        writer.writeheader()
        writer.writerows(key_rows)

    # ---- adjudication template ---------------------------------------------
    with (out / "adjudication_sheet.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "cell_id",
                "topic_id",
                "paper_title",
                "claim_text_zh",
                "evidence_quote",
                "reviewer_A_verdict",
                "reviewer_A_issue",
                "reviewer_B_verdict",
                "reviewer_B_issue",
                "reviewer_C_verdict",
                "reviewer_C_issue",
                "final_verdict",
                "final_issue_type",
                "adjudicator",
                "adjudication_note",
            ]
        )

    (out / "README_核对说明.md").write_text(
        _instructions(reviewer_cells, len(full), date.today().isoformat(), args.grid),
        encoding="utf-8",
    )
    summary = {
        "generated_at": date.today().isoformat(),
        "sampled_cells": len(sampled),
        "full_grid_cells": len(full),
        "reviewer_files": [f"reviewer_{r}.csv" for r in REVIEWER_IDS],
        "columns": COLUMNS,
    }
    (out / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {out}: sampled={len(sampled)} full={len(full)} "
        f"reviewers={len(REVIEWER_IDS)}"
    )
    return 0


def _instructions(reviewer_cells: int, full: int, generated: str, grid: str = "sampled") -> str:
    if grid == "full":
        scope = f"本包是**全量 {full} 格**（2 主题 × 15 篇 × 该主题断言数），不是抽样。"
        time_hint = f"大概 2.5–3 小时/{full} 格。可以分 2–3 次，但不要隔太多天，避免口径漂移。"
    else:
        scope = f"本包是 **{reviewer_cells}/{full} 格分层抽样**（约 57%），不是全量。"
        time_hint = "大概 1.5–2 小时/60 格。可以分两次，但不要隔太多天，避免口径漂移。"
    return f"""# CiteMap 人工核对包（CSV 版）

生成日期：{generated}

> {scope}

## 文件

- `reviewer_A.csv` / `reviewer_B.csv` / `reviewer_C.csv`：**发给核对人**。每份 {reviewer_cells} 格，顺序不同，内容相同；不需要 C 就只发 A/B。
- `full_grid_105_optional.csv`：全量网格（{full} 格 = 2 主题 × 15 篇 × 该主题断言数）。
- `_organizer_only_key.csv`：**只自己保留**，含机器证据、置信度、抽样标记，不要发给核对人。
- `adjudication_sheet.csv`：两人结果不一致时的仲裁表，空白模板。
- `manifest.json`：生成信息。

## 核对人怎么做

1. 只打开自己那份 `reviewer_X.csv`，不要看别人的文件，不要互相讨论。
2. 每行是一格：论文标题、断言、机器抽出的证据句、论文摘要。
3. 只回答三列：
   - `verify_verdict`：`正确` / `有问题` / `跳过`
   - `issue_type`：仅当 `有问题` 时填：`引用句不存在` / `断言错配` / `立场错` / `方法或样本错` / `论文信息错` / `其他`
   - `verify_note`：有问题或跳过的原因，一句话；正确可留空。
   - `reviewer_confidence_1_5`（可选）：1–5，表示自己判断的确定程度。
4. 判定口径：
   - **机器证据格**：证据句必须能在 `paper_abstract` 中**逐字找到**；还要对得上断言、立场、方法/样本。全对才填“正确”。
   - **无机器证据格**：看摘要里是否其实存在能支持/反驳该断言的证据。确实没有 → `正确`；其实有 → `有问题` 且 issue_type 填 `断言错配`；摘要不足 → `跳过`。
5. {time_hint}

## 回收后怎么算

1. 收齐 A/B（可选 C）的 CSV。
2. 运行：

```bash
python scripts/score_citemap_csv.py \\
  --key dist/citemap_audit/_organizer_only_key.csv \\
  --reviewer dist/citemap_audit/reviewer_A.csv \\
  --reviewer dist/citemap_audit/reviewer_B.csv \\
  --out dist/citemap_audit/_results
```

3. 脚本输出：
   - `agreement.json`：一致率、Cohen's κ / Fleiss κ、证据精确率、无证据误报率、Wilson 95% CI；
   - `adjudication.csv`：只列两人判不一致的格；
   - `merged.csv`：逐格多数票结果，供做表/画图。

## 边界（写报告时必须带）

- 60 格是分层抽样，不是全量；不能写“30 篇论文全部已验证”。
- 两人独立核对 + 仲裁，才能叫“双人核对”；一人只能叫“单人抽样核对”。
- 机器抽取只读摘要，没有读全文/结果页；即使人工判“正确”，也只证明摘要级抽取正确。
- 没有做 60 格之前，`verification_state.json` 的 `checked` 必须保持 0，不能写成已验证。
"""


if __name__ == "__main__":
    raise SystemExit(main())
