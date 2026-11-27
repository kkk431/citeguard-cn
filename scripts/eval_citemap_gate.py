"""Evaluate confidence gating for CiteMap machine evidence (B1.4).

Baseline: all 31 machine-evidence cells, precision 8/31 = 25.8%.
The gate is evaluated against the 3-reviewer majority labels in the frozen
105-cell audit.  This is an audit, not a new human annotation.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from citeguard.citemap_gate import evaluate

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/experiments/citemap_audit_105"


def main() -> int:
    merged = list(csv.DictReader((AUDIT / "merged.csv").open(encoding="utf-8-sig")))
    key = {r["cell_id"]: r for r in csv.DictReader((AUDIT / "key.csv").open(encoding="utf-8-sig"))}
    rows = []
    for r in merged:
        if r.get("cell_kind") != "机器证据":
            continue
        k = key.get(r["cell_id"], {})
        rows.append({**r, "confidence": float(k.get("machine_confidence") or 0.0)})

    baseline_correct = sum(1 for r in rows if r["majority"] == "correct")
    baseline = {
        "n": len(rows),
        "correct": baseline_correct,
        "precision": round(baseline_correct / len(rows), 4) if rows else 0.0,
    }
    by_threshold = {str(t): evaluate(rows, threshold=t).as_dict() for t in (0.7, 0.8, 0.9, 0.95)}
    best = max(by_threshold.items(), key=lambda kv: (kv[1]["f1"], kv[1]["precision"]))
    payload = {
        "schema": "citemap_gate_eval_v1",
        "baseline_all_machine": baseline,
        "by_threshold": by_threshold,
        "best_by_f1": {"threshold": best[0], **best[1]},
        "boundary": "human labels are 3-reviewer majority; machine confidence is not a calibrated probability",
        "rows": [{k: r[k] for k in ("cell_id", "majority", "confidence", "machine_stance")} for r in rows],
    }
    out = ROOT / "data/experiments/opt_b1_4_citemap_gate_2026-11-27.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Batch 1.4 CiteMap 机器证据置信门禁",
        "",
        f"- 机器证据 {baseline['n']} 格；全部展示时 precision **{baseline['correct']}/{baseline['n']} = {baseline['precision']:.4f}**。",
        "",
        "| 阈值 | 展示 | 正确 | precision | recall | F1 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for t, m in by_threshold.items():
        md.append(f"| {t} | {m['shown']} | {m['correct']} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} |")
    md += [
        "",
        f"按 F1 选阈值 **{best[0]}**：precision {best[1]['precision']:.4f}，recall {best[1]['recall']:.4f}。",
        "结论：高置信子集精度提升明显但召回下降；只能作为“高置信候选”展示/筛选，不能把门禁后的子集说成全面机器证据精度。",
        "",
        "复现：`PYTHONPATH=src python scripts/eval_citemap_gate.py`",
    ]
    (ROOT / "docs/optimization/b1_4_citemap_gate.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"baseline": baseline, "by_threshold": by_threshold}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
