"""报告内的三张真图（纯数据，无前端依赖）。

图表只用报告自身的数字，不引入外部统计；前端用 CSS 条形图渲染，
并在每张图下提供同数据的表格视图（可访问性 + 精确值）。

- ``status``：核验结论分布（Exact/Minor/Unverified/Unknown/Major）
- ``support``：支持度四档（含未判定）
- ``compliance``：GB/T 格式问题字段 Top-N
"""
from __future__ import annotations

_STATUS_ORDER = ["Exact", "Minor", "Unverified", "Unknown", "Major"]
_STATUS_LABELS = {
    "Exact": "完全匹配",
    "Minor": "轻微差异",
    "Unverified": "未收录/无法核验",
    "Unknown": "数据源不可用",
    "Major": "严重不符",
}
_SUPPORT_ORDER = ["support", "partial", "contradict", "no_evidence", "not_checked"]
_SUPPORT_LABELS = {
    "support": "支持",
    "partial": "部分支持",
    "contradict": "矛盾",
    "no_evidence": "无证据",
    "not_checked": "未判定",
}


def _rows(order, labels, counts: dict) -> list[dict]:
    total = sum(int(counts.get(k) or 0) for k in order)
    rows = []
    for key in order:
        value = int(counts.get(key) or 0)
        rows.append({
            "key": key,
            "label": labels[key],
            "value": value,
            "pct": round(value * 100.0 / total, 1) if total else 0.0,
        })
    return rows


def build_charts(report: dict) -> list[dict]:
    refs = report.get("references") or []
    stats = report.get("stats") or {}

    status_counts = {k: int(stats.get(k) or 0) for k in _STATUS_ORDER}
    status_total = sum(status_counts.values()) or int(stats.get("total") or 0)
    charts = [{
        "id": "status",
        "title": "核验结论分布",
        "subtitle": f"共 {status_total} 条引用；结论来自题录比对，不是引用支持度",
        "total": status_total,
        "rows": _rows(_STATUS_ORDER, _STATUS_LABELS, status_counts),
        "note": "Unverified 指公开数据源未收录，Unknown 指数据源不可用，两者都不等于“造假”。",
    }]

    support_counts = stats.get("support") or {}
    support_total = sum(int(support_counts.get(k) or 0) for k in _SUPPORT_ORDER)
    charts.append({
        "id": "support",
        "title": "引用支持度四档",
        "subtitle": f"已判定 {support_total} 条（未判定 {int(support_counts.get('not_checked') or 0)} 条）",
        "total": support_total,
        "rows": _rows(_SUPPORT_ORDER, _SUPPORT_LABELS, support_counts),
        "note": "支持度只回答“证据是否支持这句话”，与文献是否存在无关。",
    })

    field_counts: dict[str, int] = {}
    issue_total = 0
    for ref in refs:
        for issue in ((ref.get("compliance") or {}).get("issues") or []):
            if issue.get("level") == "info":
                continue
            issue_total += 1
            field = str(issue.get("field") or "其他")
            field_counts[field] = field_counts.get(field, 0) + 1
    top = sorted(field_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    charts.append({
        "id": "compliance",
        "title": "GB/T 格式问题 Top 字段",
        "subtitle": f"共 {issue_total} 条 warning/error（info 级提示不计入）",
        "total": issue_total,
        "rows": [
            {"key": f, "label": f, "value": n,
             "pct": round(n * 100.0 / issue_total, 1) if issue_total else 0.0}
            for f, n in top
        ],
        "note": "只看字段分布，不代表投稿会被拒；最终以目标期刊要求为准。",
    })
    return charts
