"""Five-dimension citation health profile.

Rule-based, deliberately transparent: every dimension exposes the counts it was
computed from, and dimensions that were not evaluated (for example support when
no judge key is configured) are excluded from the weighted total instead of
being treated as zero.  This is a triage score, not a journal or reviewer
standard; the UI says so next to the number.
"""
from __future__ import annotations

from typing import Any

# Weights are fixed and sum to 100 when every dimension is available.
WEIGHTS = {
    "authenticity": 25,
    "support": 25,
    "relevance": 20,
    "coverage": 15,
    "compliance": 15,
}

LABELS = {
    "authenticity": "真实性",
    "support": "支持度",
    "relevance": "相关性",
    "coverage": "覆盖度",
    "compliance": "规范性",
}

# Status -> score. Unverified and Unknown are caution states, not accusations:
# they score lower because the citation still needs a human look, not because
# it is presumed fake.
AUTH_SCORE = {"Exact": 100, "Minor": 75, "Unverified": 35, "Unknown": 35, "Major": 0}
SUPPORT_SCORE = {"support": 100, "partial": 60, "contradict": 0, "no_evidence": 15}
SUPPORT_LABEL = {
    "support": "支持",
    "partial": "部分支持",
    "contradict": "矛盾",
    "no_evidence": "无依据",
}

GRADES = ((95, "A"), (85, "B"), (75, "C"), (60, "D"))


def _grade(score: float) -> str:
    for cut, letter in GRADES:
        if score >= cut:
            return letter
    return "E"


def _dimension(key: str, score: float | None, detail: dict, note: str = "") -> dict:
    return {
        "key": key,
        "label": LABELS[key],
        "weight": WEIGHTS[key],
        "score": None if score is None else round(max(0.0, min(100.0, score)), 1),
        "available": score is not None,
        "detail": detail,
        "note": note,
    }


def compute_health(report: dict) -> dict:
    stats = report.get("stats") or {}
    refs = report.get("references") or []
    citations = report.get("citations") or {}
    total = int(stats.get("total") or len(refs) or 0)

    dims: list[dict] = []

    # 1. Authenticity: weighted average over verification statuses.
    counts = {k: int(stats.get(k) or 0) for k in ("Exact", "Minor", "Unverified", "Unknown", "Major")}
    if total:
        weighted = sum(counts[k] * AUTH_SCORE[k] for k in AUTH_SCORE)
        auth = weighted / total
        note = ""
        unresolved = counts["Unverified"] + counts["Unknown"]
        if unresolved and unresolved / total >= 0.5:
            note = "半数以上条目未找到或未完成核验：先看数据源是否可用，不等于文献造假"
        dims.append(_dimension("authenticity", auth, counts, note))
    else:
        dims.append(_dimension("authenticity", None, counts))

    # 2. Support: only judged references count; not_checked is not a failure.
    support = stats.get("support") or {}
    support_counts = {k: int(support.get(k) or 0) for k in ("support", "partial", "contradict", "no_evidence", "not_checked")}
    checked = sum(v for k, v in support_counts.items() if k != "not_checked")
    if checked:
        sup = sum(support_counts[k] * SUPPORT_SCORE[k] for k in SUPPORT_SCORE) / checked
        dims.append(
            _dimension(
                "support",
                sup,
                {"checked": checked, "total": total, **support_counts},
                "" if checked >= total * 0.8 else f"仅 {checked}/{total} 条有摘要可判，支持度只代表这部分",
            )
        )
    else:
        dims.append(_dimension("support", None, support_counts, "本次没有可判定的支持度（缺摘要或未配置模型）"))

    # 3. Relevance: how many listed references are actually cited in the body.
    coverage = citations.get("coverage") or {}
    ratio = coverage.get("ratio")
    cited_refs = int(coverage.get("cited") or 0)
    if refs and ratio is not None and int(coverage.get("refs") or 0) > 0:
        dims.append(
            _dimension(
                "relevance",
                float(ratio) * 100,
                {"cited_refs": cited_refs, "total": total, "citations": int((citations.get("summary") or {}).get("total") or 0)},
                "" if cited_refs else "正文里没有找到编号引用，可能用了作者-年制或其他标法",
            )
        )
    else:
        dims.append(_dimension("relevance", None, {"cited_refs": cited_refs, "total": total}, "没有可匹配的正文引用"))

    # 4. Coverage: every body citation resolves to a reference entry (the other
    # direction from relevance). Only numeric styles can be checked exactly.
    consistency = report.get("citation_consistency") or {}
    missing_numbers = consistency.get("missing_numbers") or []
    distinct = int(consistency.get("distinct_numbers") or 0)
    if consistency.get("numeric_style") and distinct:
        dims.append(
            _dimension(
                "coverage",
                (distinct - len(missing_numbers)) / distinct * 100,
                {
                    "numbers": distinct,
                    "missing": [int(x) for x in missing_numbers[:50]],
                    "inversions": int(consistency.get("order_inversions") or 0),
                },
            )
        )
    else:
        dims.append(_dimension("coverage", None, {}, "没有编号引用，无法计算覆盖度"))

    # 5. Compliance: GB/T 7714 average from the format checker.
    avg = stats.get("avg_compliance")
    if avg is not None and total:
        dims.append(
            _dimension(
                "compliance",
                float(avg),
                {"avg": avg, "total": total},
            )
        )
    else:
        dims.append(_dimension("compliance", None, {}))

    available = [d for d in dims if d["available"]]
    weight_sum = sum(d["weight"] for d in available)
    overall = (
        sum(d["score"] * d["weight"] for d in available) / weight_sum if weight_sum else 0.0
    )
    confidence = round(weight_sum / 100, 2)

    return {
        "overall": round(overall, 1),
        "grade": _grade(overall),
        "confidence": confidence,
        "dimensions": dims,
        "top_fixes": _top_fixes(report, counts, support_counts, consistency),
        "disclaimer": "规则加权分（真实性25/支持度25/相关性20/覆盖15/规范性15），未检测的维度不计入；不是期刊或评审标准。",
    }


def _top_fixes(report: dict, counts: dict, support: dict, consistency: dict) -> list[dict]:
    stats = report.get("stats") or {}
    refs = report.get("references") or []
    total = int(stats.get("total") or len(refs) or 0)
    fixes: list[dict] = []

    if counts.get("Major"):
        fixes.append(
            {
                "severity": "high",
                "title": f"{counts['Major']} 条疑似错配或虚构",
                "detail": "题名/DOI 与真实文献对不上，优先逐条核对。",
            }
        )
    if support.get("contradict"):
        fixes.append(
            {
                "severity": "high",
                "title": f"{support['contradict']} 条引用与被引原文矛盾",
                "detail": "正文论点可能站不住，先看原文再改表述。",
            }
        )
    missing = consistency.get("missing_numbers") or []
    if isinstance(missing, list) and missing:
        fixes.append(
            {
                "severity": "high",
                "title": f"{len(missing)} 个正文编号在参考文献表中缺失",
                "detail": "编号 " + "、".join(str(x) for x in missing[:8]) + ("…" if len(missing) > 8 else ""),
            }
        )
    unresolved = counts.get("Unverified", 0) + counts.get("Unknown", 0)
    if unresolved:
        fixes.append(
            {
                "severity": "medium",
                "title": f"{unresolved} 条未找到或未完成核验",
                "detail": "未找到不等于造假；先确认来源是否可用，再人工核对。",
            }
        )
    uncited = consistency.get("uncited_numbers") or []
    if isinstance(uncited, list) and uncited:
        fixes.append(
            {
                "severity": "low",
                "title": f"{len(uncited)} 条参考文献没在正文里被引用",
                "detail": "可能是凑数文献或引注漏标，建议逐条确认。",
            }
        )
    fields: dict[str, int] = {}
    for item in refs:
        comp = item.get("compliance") or {}
        for issue in comp.get("issues") or []:
            if issue.get("level") == "info":
                continue
            field = issue.get("field") or "其他"
            fields[field] = fields.get(field, 0) + 1
    if fields:
        top = sorted(fields.items(), key=lambda kv: -kv[1])[:3]
        fixes.append(
            {
                "severity": "medium",
                "title": f"{sum(fields.values())} 处格式问题",
                "detail": "集中在 " + "、".join(f"{k}（{v}）" for k, v in top),
            }
        )
    if not fixes:
        fixes.append({"severity": "low", "title": "没有发现需要优先处理的问题", "detail": "仍建议抽查关键引用。"})
    fixes.sort(key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f["severity"], 3))
    return fixes[:3]
