"""Aggregate several finished reports into one cohort view.

Used by the history page ("聚合所选") for classes / labs that upload a batch of
papers and want one screen: average health, five-dimension averages, the most
common problems, and a per-paper ranking. Everything is computed from the
stored report JSON, so the numbers stay reproducible after the fact.
"""

from __future__ import annotations

import csv
import io
from collections import Counter


DIM_LABELS = {
    "authenticity": "真实性",
    "support": "支持度",
    "relevance": "相关性",
    "coverage": "覆盖",
    "compliance": "规范性",
}

GRADE_ORDER = ("A", "B", "C", "D", "E", "未评")


def _refs(report: dict) -> list[dict]:
    return [r for r in report.get("references") or [] if isinstance(r, dict)]


def _support_counts(report: dict) -> Counter:
    counts = Counter()
    stats = (report.get("stats") or {}).get("support") or {}
    for key in ("support", "partial", "contradict", "no_evidence", "not_checked"):
        counts[key] = int(stats.get(key) or 0)
    if not counts:
        for ref in _refs(report):
            label = ((ref.get("support") or {}).get("label") or "not_checked")
            counts[label] += 1
    return counts


def _format_field_counts(report: dict) -> Counter:
    counts = Counter()
    for ref in _refs(report):
        for issue in ((ref.get("compliance") or {}).get("issues") or []):
            if issue.get("level") == "info":
                continue
            field = issue.get("field") or "其他"
            counts[field] += 1
    return counts


def _row(job_id: str, name: str, report: dict) -> dict:
    stats = report.get("stats") or {}
    health = report.get("health") or {}
    refs = _refs(report)
    support = _support_counts(report)
    uncited = ((report.get("citations") or {}).get("coverage") or {}).get("uncited") or []
    missing = (report.get("citation_consistency") or {}).get("missing_numbers") or []
    format_fields = _format_field_counts(report)
    retracted = sum(
        1 for ref in refs
        if ((ref.get("retraction") or {}).get("status") == "retracted")
    )
    dims = {}
    for dim in (health.get("dimensions") or []):
        key = dim.get("key")
        if key and dim.get("available"):
            dims[key] = dim.get("score")
    return {
        "job_id": job_id,
        "name": name,
        "health": health.get("overall"),
        "grade": health.get("grade") or "未评",
        "confidence": health.get("confidence"),
        "refs": int(stats.get("total") or len(refs)),
        "exact": int(stats.get("Exact") or 0),
        "minor": int(stats.get("Minor") or 0),
        "unverified": int(stats.get("Unverified") or 0),
        "unknown": int(stats.get("Unknown") or 0),
        "major": int(stats.get("Major") or 0),
        "format_issues": sum(format_fields.values()),
        "format_fields": dict(format_fields),
        "contradict": support.get("contradict", 0),
        "partial": support.get("partial", 0),
        "no_evidence": support.get("no_evidence", 0),
        "uncited": len(uncited),
        "missing_citations": len(missing),
        "retracted": retracted,
        "dims": dims,
    }


def _issue_rows(rows: list[dict], reports: list[dict]) -> list[dict]:
    """Count problems across papers, not raw issue instances."""
    counters: Counter = Counter()
    for row in rows:
        if row["major"]:
            counters["真实性：疑似错配/虚构（Major）"] += 1
        if row["unverified"] + row["unknown"]:
            counters["真实性：未核验/无法核验"] += 1
        if row["contradict"]:
            counters["支持度：证据矛盾"] += 1
        if row["partial"]:
            counters["支持度：只有部分支持"] += 1
        if row["no_evidence"]:
            counters["支持度：缺少证据"] += 1
        if row["uncited"]:
            counters["相关性：正文未引用"] += 1
        if row["missing_citations"]:
            counters["覆盖：正文引注编号缺失"] += 1
        if row["retracted"]:
            counters["撤稿：引用了已撤稿文献"] += 1
        for field in row["format_fields"]:
            counters[f"规范性：{field}"] += 1
    top = [{"label": label, "count": count} for label, count in counters.most_common(5)]
    return top


def aggregate(reports: list[tuple[str, str, dict]]) -> dict:
    rows = [_row(job_id, name, report) for job_id, name, report in reports]
    scored = [r for r in rows if isinstance(r["health"], (int, float))]
    dim_sums: Counter = Counter()
    dim_counts: Counter = Counter()
    for row in rows:
        for key, score in row["dims"].items():
            if isinstance(score, (int, float)):
                dim_sums[key] += score
                dim_counts[key] += 1
    dims = [
        {
            "key": key,
            "label": DIM_LABELS.get(key, key),
            "average": round(dim_sums[key] / dim_counts[key], 1) if dim_counts[key] else None,
            "papers": dim_counts[key],
        }
        for key in DIM_LABELS
    ]
    grades = Counter(r["grade"] for r in rows)
    coverage = len(scored) / len(rows) if rows else 0.0
    return {
        "summary": {
            "papers": len(rows),
            "scored": len(scored),
            "coverage": round(coverage, 3),
            "avg_health": round(sum(r["health"] for r in scored) / len(scored), 1) if scored else None,
            "min_health": min((r["health"] for r in scored), default=None),
            "max_health": max((r["health"] for r in scored), default=None),
            "avg_refs": round(sum(r["refs"] for r in rows) / len(rows), 1) if rows else 0,
            "refs": sum(r["refs"] for r in rows),
            "major": sum(r["major"] for r in rows),
            "contradict": sum(r["contradict"] for r in rows),
            "format_issues": sum(r["format_issues"] for r in rows),
        },
        "grades": [{"grade": grade, "count": grades.get(grade, 0)} for grade in GRADE_ORDER],
        "dimensions": dims,
        "top_issues": _issue_rows(rows, [report for _, _, report in reports]),
        "papers": sorted(
            rows,
            key=lambda r: (-(r["health"] if isinstance(r["health"], (int, float)) else -1), r["name"]),
        ),
        "note": "聚合只统计已存报告；健康分为规则加权分，不是期刊或评审标准；未检测维度不计入平均。",
    }


def to_csv(data: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "job_id", "论文", "健康分", "等级", "置信权重", "参考文献", "真实一致",
        "元数据偏差", "未核验", "无法核验", "疑似错配", "格式问题", "证据矛盾",
        "部分支持", "缺少证据", "正文未引用", "引注编号缺失", "撤稿",
    ])
    for row in data.get("papers") or []:
        writer.writerow([
            row["job_id"], row["name"], row["health"], row["grade"], row["confidence"],
            row["refs"], row["exact"], row["minor"], row["unverified"], row["unknown"],
            row["major"], row["format_issues"], row["contradict"], row["partial"],
            row["no_evidence"], row["uncited"], row["missing_citations"], row["retracted"],
        ])
    return buf.getvalue()
