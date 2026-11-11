"""复检 diff（Phase 2 · 修复闭环）。

比较同一篇论文两份报告（修正前 vs 修正后），按参考文献逐条给出：

- 已解决：旧问题消失，且新状态为 Exact；
- 仍存在：字段级问题键相同；
- 新增：修正过程中引入的新问题；
- 状态变化：Exact/Minor/Major/Unverified/Unknown 的迁移。

匹配以参考文献序号为主；序号缺失时按规范化题名兜底。
只比较报告里已有的字段，不重新联网、不调用模型。
"""
from __future__ import annotations

import re

_STATUS_ORDER = {"Exact": 0, "Minor": 1, "Unverified": 2, "Unknown": 3, "Major": 4}


def _norm_title(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)
    return text[:80]


def _issue_key(issue: dict) -> tuple:
    return (
        str(issue.get("level") or ""),
        str(issue.get("field") or ""),
        str(issue.get("message") or ""),
    )


def _issues(ref: dict) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for issue in ((ref.get("compliance") or {}).get("issues") or []):
        if issue.get("level") == "info":
            continue
        out[_issue_key(issue)] = issue
    return out


def _status(ref: dict) -> str:
    return str((ref.get("verify") or {}).get("status") or "Unknown")


def _label(ref: dict) -> str:
    return str((ref.get("support") or {}).get("label") or "")


def _index_map(report: dict) -> dict:
    out: dict = {}
    for i, ref in enumerate(report.get("references") or [], 1):
        idx = ref.get("index") or i
        out[("index", idx)] = ref
        title = _norm_title((ref.get("parsed") or {}).get("title") or "")
        if title:
            out.setdefault(("title", title), ref)
    return out


def diff_reports(old: dict, new: dict) -> dict:
    old_map = _index_map(old)
    new_refs = new.get("references") or []
    items: list[dict] = []
    resolved = still = added = status_changed = support_changed = 0

    for i, ref in enumerate(new_refs, 1):
        idx = ref.get("index") or i
        prev = old_map.get(("index", idx))
        if prev is None:
            title = _norm_title((ref.get("parsed") or {}).get("title") or "")
            prev = old_map.get(("title", title)) if title else None
        if prev is None:
            continue
        old_issues = _issues(prev)
        new_issues = _issues(ref)
        fixed_keys = [k for k in old_issues if k not in new_issues]
        fresh_keys = [k for k in new_issues if k not in old_issues]
        kept_keys = [k for k in new_issues if k in old_issues]
        old_status, new_status = _status(prev), _status(ref)
        status_moved = old_status != new_status
        support_moved = _label(prev) != _label(ref)

        if fixed_keys and not new_issues and new_status == "Exact":
            kind = "resolved"
            resolved += 1
        elif fresh_keys:
            kind = "new"
            added += 1
        elif kept_keys:
            kind = "still"
            still += 1
        elif status_moved:
            kind = "status"
            status_changed += 1
        else:
            kind = "unchanged"
        if support_moved:
            support_changed += 1

        if kind != "unchanged":
            items.append({
                "index": idx,
                "title": (ref.get("parsed") or {}).get("title") or (prev.get("parsed") or {}).get("title") or "",
                "kind": kind,
                "status": {"old": old_status, "new": new_status},
                "support": {"old": _label(prev), "new": _label(ref)},
                "fixed": [{"level": k[0], "field": k[1], "message": k[2]} for k in fixed_keys],
                "new": [{"level": k[0], "field": k[1], "message": k[2]} for k in fresh_keys],
                "still": [{"level": k[0], "field": k[1], "message": k[2]} for k in kept_keys],
                "compliance": {
                    "old": (prev.get("compliance") or {}).get("score"),
                    "new": (ref.get("compliance") or {}).get("score"),
                },
            })

    return {
        "summary": {
            "old_total": len(old.get("references") or []),
            "new_total": len(new_refs),
            "resolved": resolved,
            "still": still,
            "new": added,
            "status_changed": status_changed,
            "support_changed": support_changed,
            "changed": len(items),
        },
        "items": items,
        "note": "diff 只比较两份报告里已有的字段，不重新联网核验；Exact 仍以数据源当时返回为准。",
    }
