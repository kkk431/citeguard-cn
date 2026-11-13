"""Deterministic "fix" pass for parsed references.

The product already tells a user *what* is wrong. This module turns the parsed
fields back into a GB/T 7714-style entry so the user can copy a corrected
reference list without retyping it. It is deliberately conservative: it only
re-typesets fields the parser recovered, never invents authors, venues or
years, and every entry carries warnings for the fields that were missing.

The repair loop (``build_patch`` / ``apply_patch`` / ``undo_patch``) is the pure
data layer behind "one-click fix all + diff + undo": it computes a reversible
patch, records the fixed text next to the untouched original, and can remove
that record again. None of these functions touch disk or global state; the web
layer owns persistence, routes, and the undo time window.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
from types import SimpleNamespace
from typing import Any

from .format_gbt import format_from_reference

_MISSING_LABELS = {
    "authors": "作者",
    "title": "题名",
    "venue": "来源",
    "year": "年份",
    "doi": "DOI",
}


def _parsed(ref: dict) -> SimpleNamespace:
    data = ref.get("parsed") or {}
    return SimpleNamespace(**{k: v for k, v in data.items() if not k.startswith("_")})


def _issues(before: str, after: str, parsed: SimpleNamespace) -> list[str]:
    """Human-readable list of what the reformat changed and what is missing."""
    fixes: list[str] = []
    if not re.search(r"\[[A-Z]{1,3}(?:/OL)?\]", before) and re.search(r"\[[A-Z]{1,3}(?:/OL)?\]", after):
        fixes.append("补文献类型码")
    if re.search(r"\(\s*\d{4}\s*\)", before) and "(" not in after:
        fixes.append("年份不再放在括号里")
    if ";" in before and ";" not in after:
        fixes.append("作者分隔符统一为逗号")
    if re.search(r"[.。]{2,}", before):
        fixes.append("去掉重复句点")
    if getattr(parsed, "doi", "") and "DOI:" not in before and "doi:" not in before.lower():
        fixes.append("DOI 统一为「DOI: …」")
    if before.strip() and before.strip() != before:
        fixes.append("去掉首尾空白")
    if not before.rstrip().endswith((".", "。", "．")):
        fixes.append("补结尾句点")
    return fixes


def _clean_parsed(parsed: SimpleNamespace) -> SimpleNamespace:
    """Move volume/pages that the parser left inside the venue string.

    PDF references often parse as ``venue="Journal, 12, 138-150"`` with pages
    already captured separately. Rendering that verbatim duplicates the pages
    ("12, 138-150, 2025: 138-150"), so peel the tail back into fields first.
    """
    venue = (getattr(parsed, "venue", "") or "").strip()
    pages = (getattr(parsed, "pages", "") or "").strip()
    article = re.search(
        r"[,;]\s*(\d{1,4})\s*,\s*Article ID:\s*(\d+)\s*$", venue, re.IGNORECASE
    )
    if article:
        # "Journal, 238, Article ID: 121801": volume 238, article number 121801.
        if not getattr(parsed, "volume", ""):
            parsed.volume = article.group(1)
        parsed.pages = article.group(2)
        venue = venue[: article.start()]
    elif venue and pages:
        tail = re.search(
            r"[,;]\s*(\d{1,4})(?:\s*\((\d{1,3})\))?\s*[,:]\s*" + re.escape(pages) + r"\s*$",
            venue,
        )
        if tail:
            if not getattr(parsed, "volume", ""):
                parsed.volume = tail.group(1)
            if tail.group(2) and not getattr(parsed, "issue", ""):
                parsed.issue = tail.group(2)
            venue = venue[: tail.start()]
        elif venue.rstrip().endswith(pages):
            venue = venue.rstrip()[: -len(pages)].rstrip(" ,;:，：")
    venue = re.sub(r"[,;]?\s*(?:19|20)\d{2}\s*$", "", venue).strip(" ,;:，：")
    parsed.venue = venue
    return parsed


def fix_entry(index: int, ref: dict) -> dict:
    parsed = _clean_parsed(_parsed(ref))
    before = (ref.get("raw") or "").strip()
    after = format_from_reference(parsed)
    missing = [
        label
        for field, label in _MISSING_LABELS.items()
        if field != "doi" and not getattr(parsed, field, None)
    ]
    # "safe" means the entry has enough recovered fields to be worth copying;
    # it is still a suggestion, not a guaranteed-correct citation.
    safe = bool(parsed.title) and bool(parsed.authors) and bool(parsed.year)
    return {
        "index": index,
        "before": before,
        "after": after,
        "fixes": _issues(before, after, parsed),
        "missing": missing,
        "safe": safe,
        "changed": bool(after) and after != before,
    }


def fix_report(report: dict) -> dict:
    refs = report.get("references") or []
    items = [fix_entry(i, ref) for i, ref in enumerate(refs, 1)]
    changed = [it for it in items if it["changed"]]
    safe = [it for it in changed if it["safe"]]
    return {
        "summary": {
            "total": len(items),
            "changed": len(changed),
            "safe": len(safe),
            "with_missing": len([it for it in items if it["missing"]]),
        },
        "items": items,
    }


def as_text(fixed: dict) -> str:
    """Plain-text reference list (UTF-8 BOM added by the web layer when sending)."""
    items = fixed.get("items") or []
    lines = [
        "引证卫士 · 修订后的参考文献表",
        "说明：仅按已解析字段重新排版（GB/T 7714 风格），未补全缺失字段；"
        "带 * 的条目字段不完整，请对照原文核对。",
        "",
    ]
    for item in items:
        if not item.get("after"):
            continue
        mark = " *" if item.get("missing") else ""
        lines.append(f"[{item['index']}]{mark} {item['after']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Repair loop data layer (C1a): reversible patch + apply + undo.
#
# The patch is a JSON-serialisable document. Applying it never rewrites the
# original ``raw`` / ``parsed`` fields: the fixed text is stored under
# ``references[i]["repair"]``, so undo only has to drop that record and the
# report is byte-for-byte back to its original shape. The web layer decides
# where a patch/repair state is persisted and how long undo stays available.
# ---------------------------------------------------------------------------

REPAIR_SCHEMA = "citeguard.repair_patch/1"
REPAIR_STATE_SCHEMA = "citeguard.repair_state/1"
REPAIR_KEY = "repair"
REPAIR_STATES = ("unfixed", "fixed")
REPAIR_STATE_LABELS = {"unfixed": "未修", "fixed": "已修", "reverted": "已撤销"}
REPAIR_UNDO_TTL_SECONDS = 30 * 60


def _is_index(value: Any) -> bool:
    """True for a stable 1-based reference number (``True`` is not an index)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _references(report: Any) -> list[dict]:
    if not isinstance(report, dict):
        raise ValueError("report 必须是 dict")
    refs = report.get("references")
    if refs is None:
        return []
    if not isinstance(refs, list):
        raise ValueError("report['references'] 必须是列表")
    for position, ref in enumerate(refs, 1):
        if not isinstance(ref, dict):
            raise ValueError(f"第 {position} 条参考文献不是对象")
    return refs


def _index_map(report: Any) -> dict[int, dict]:
    """Map each reference to its stable number, preferring its own ``index``.

    Well-formed reports already carry ``index`` 1..N. A report missing an index
    (or carrying a duplicate) falls back to the positional number, matching
    ``fix_report``; only a duplicate *positional* number is an error.
    """
    refs = _references(report)
    by_index: dict[int, dict] = {}
    pending: list[tuple[int, dict]] = []
    for position, ref in enumerate(refs, 1):
        declared = ref.get("index")
        if _is_index(declared) and declared not in by_index:
            by_index[declared] = ref
        else:
            pending.append((position, ref))
    for position, ref in pending:
        if position in by_index:
            raise ValueError(f"报告里存在重复的条目序号 {position}，无法建立稳定映射")
        by_index[position] = ref
    return dict(sorted(by_index.items()))


def _repair_of(ref: dict) -> dict | None:
    record = ref.get(REPAIR_KEY)
    return record if isinstance(record, dict) else None


def _report_fingerprint(report: dict) -> str:
    """Hash the fields a patch depends on, so a stale patch can be rejected."""
    payload = [
        {"index": index, "raw": ref.get("raw") or "", "parsed": ref.get("parsed") or {}}
        for index, ref in _index_map(report).items()
    ]
    blob = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return "rf-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _selected_indexes(
    report: dict,
    indexes: list[int] | tuple[int, ...] | set[int] | frozenset[int] | None,
) -> list[int]:
    """Validate the requested 1-based numbers and return them in report order."""
    by_index = _index_map(report)
    if indexes is None:
        return list(by_index)
    if isinstance(indexes, (str, bytes)) or not isinstance(
        indexes, (list, tuple, set, frozenset)
    ):
        raise ValueError("indexes 必须是条目序号列表或 None")
    chosen: set[int] = set()
    for value in indexes:
        if not _is_index(value):
            raise ValueError(f"非法条目序号 {value!r}：必须是 ≥1 的整数")
        if value not in by_index:
            raise ValueError(f"条目序号 {value} 不在报告中（共 {len(by_index)} 条）")
        chosen.add(value)
    return [index for index in by_index if index in chosen]


def _diff_segments(before: str, after: str) -> list[dict]:
    """Character-level opcodes so the UI can highlight exact changes.

    Each segment keeps both sides (``before`` / ``after``); concatenating the
    ``after`` sides rebuilds the fixed text and concatenating ``before``
    rebuilds the original. Character granularity works for CJK and Latin text
    without a tokenizer.
    """
    if before == after:
        return []
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    return [
        {"op": tag, "before": before[i1:i2], "after": after[j1:j2]}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
    ]


def build_patch(report: dict, indexes: list[int] | None = None) -> dict:
    """Build a reversible repair patch without touching ``report``.

    ``indexes`` selects 1-based reference numbers; ``None`` selects every
    reference. Only entries whose reformatted text differs from the original
    and that are not already fixed produce ``ops``. The returned document is
    JSON-serialisable and is the only argument ``apply_patch`` / ``undo_patch``
    need.
    """
    by_index = _index_map(report)
    selected = _selected_indexes(report, indexes)
    entries: list[dict] = []
    ops: list[dict] = []
    for index in selected:
        ref = by_index[index]
        item = fix_entry(index, ref)
        previous = _repair_of(ref)
        previous_state = (
            "fixed" if previous and previous.get("state") == "fixed" else "unfixed"
        )
        already_fixed = (
            previous_state == "fixed" and previous.get("after") == item["after"]
        )
        changed = bool(item["changed"])
        if already_fixed:
            state = "fixed"
        elif changed:
            state = "pending"
        else:
            state = "unchanged"
        entries.append(
            {
                "index": index,
                "state": state,
                "previous_state": previous_state,
                "changed": changed,
                "already_fixed": already_fixed,
                "before": item["before"],
                "after": item["after"],
                "fixes": list(item["fixes"]),
                "missing": list(item["missing"]),
                "safe": bool(item["safe"]),
                "diff": _diff_segments(item["before"], item["after"]) if changed else [],
            }
        )
        if changed and not already_fixed:
            ops.append(
                {
                    "op": "set_repair",
                    "index": index,
                    "before": item["before"],
                    "after": item["after"],
                    "fixes": list(item["fixes"]),
                    "missing": list(item["missing"]),
                    "safe": bool(item["safe"]),
                }
            )
    fingerprint = _report_fingerprint(report)
    digest = hashlib.sha1(
        json.dumps(
            {"schema": REPAIR_SCHEMA, "report_fingerprint": fingerprint, "ops": ops},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:12]
    summary = {
        "total": len(by_index),
        "selected": len(selected),
        "changed": sum(1 for entry in entries if entry["changed"]),
        "to_apply": len(ops),
        "already_fixed": sum(1 for entry in entries if entry["already_fixed"]),
        "unchanged": sum(1 for entry in entries if not entry["changed"]),
        "safe": sum(1 for entry in entries if entry["changed"] and entry["safe"]),
        "with_missing": sum(
            1 for entry in entries if entry["changed"] and entry["missing"]
        ),
    }
    return {
        "schema": REPAIR_SCHEMA,
        "patch_id": f"rp-{digest}",
        "reversible": True,
        "report_fingerprint": fingerprint,
        "report_total": len(by_index),
        "indexes": selected,
        "before": [
            {
                "index": entry["index"],
                "entry": entry["before"],
                "state": entry["previous_state"],
            }
            for entry in entries
        ],
        "after": [
            {"index": entry["index"], "entry": entry["after"]} for entry in entries
        ],
        "entries": entries,
        "ops": ops,
        "summary": summary,
    }


def _patch_parts(patch: Any) -> tuple[list[dict], str, str]:
    """Validate a patch document and return ``(ops, patch_id, fingerprint)``."""
    if not isinstance(patch, dict):
        raise ValueError("patch 必须是 build_patch 返回的对象")
    ops = patch.get("ops")
    if not isinstance(ops, list):
        raise ValueError("patch 缺少 ops 列表")
    for op in ops:
        if not isinstance(op, dict):
            raise ValueError(f"patch 里的操作必须是对象：{op!r}")
    patch_id = patch.get("patch_id")
    if not isinstance(patch_id, str) or not patch_id:
        raise ValueError("patch 缺少 patch_id")
    fingerprint = patch.get("report_fingerprint")
    return ops, patch_id, fingerprint if isinstance(fingerprint, str) else ""


def apply_patch(report: dict, patch: dict) -> dict:
    """Return a deep copy of ``report`` with the patch's repairs recorded.

    The original ``raw`` / ``parsed`` fields are never rewritten: the fixed text
    lives in ``references[i]["repair"]["after"]`` so undo can drop the record and
    restore the exact original object. Applying the same patch twice yields the
    same report (idempotent); a patch built for a different report is rejected
    via ``report_fingerprint``.
    """
    ops, patch_id, fingerprint = _patch_parts(patch)
    if fingerprint and fingerprint != _report_fingerprint(report):
        raise ValueError("报告已更新，修复预览已过期，请重新生成修复预览")
    by_index = _index_map(report)
    repaired = copy.deepcopy(report)
    repaired_map = _index_map(repaired)
    seen: set[int] = set()
    for op in ops:
        if not isinstance(op, dict) or op.get("op") != "set_repair":
            raise ValueError(f"不支持的 patch 操作：{op!r}")
        index = op.get("index")
        if not _is_index(index):
            raise ValueError(f"patch 里的条目序号不合法：{index!r}")
        if index in seen:
            raise ValueError(f"patch 里条目 {index} 重复出现")
        seen.add(index)
        if index not in by_index:
            raise ValueError(f"条目序号 {index} 不在报告中（报告可能已更新）")
        after = op.get("after")
        if not isinstance(after, str) or not after.strip():
            raise ValueError(f"patch 里第 {index} 条缺少修订后的文本")
        repaired_map[index][REPAIR_KEY] = {
            "state": "fixed",
            "patch_id": patch_id,
            "before": str(op.get("before") or ""),
            "after": after,
            "fixes": [str(fix) for fix in (op.get("fixes") or [])],
            "missing": [str(miss) for miss in (op.get("missing") or [])],
            "safe": bool(op.get("safe")),
        }
    return repaired


def undo_patch(
    report: dict,
    patch: dict | None = None,
    indexes: list[int] | None = None,
) -> dict:
    """Return a deep copy with repair records removed（撤销）.

    - ``patch`` given: only entries recorded by that patch (matching
      ``patch_id``) are reverted; entries fixed by another patch are skipped.
    - ``indexes`` given: restrict the undo to those reference numbers.
    - Neither: revert every repair in the report.

    Reverting an entry that is already unfixed is a no-op, so calling undo twice
    is safe. The returned report is byte-for-byte identical to the pre-apply
    report when the patch was applied to a pristine copy.
    """
    by_index = _index_map(report)
    target: set[int] | None = None
    patch_id = ""
    if patch is not None:
        ops, patch_id, fingerprint = _patch_parts(patch)
        if fingerprint and fingerprint != _report_fingerprint(report):
            raise ValueError("报告已更新，撤销窗口已结束，请重新分析后再试")
        declared = [op.get("index") for op in ops]
        expected = patch.get("indexes")
        candidates = expected if isinstance(expected, list) else declared
        target = {value for value in candidates if _is_index(value) and value in by_index}
    if indexes is not None:
        selected = set(_selected_indexes(report, indexes))
        target = selected if target is None else target & selected
    if target is None:
        target = set(by_index)
    restored = copy.deepcopy(report)
    restored_map = _index_map(restored)
    for index in sorted(target):
        record = _repair_of(restored_map[index])
        if not record or record.get("state") != "fixed":
            continue
        if patch is not None and record.get("patch_id") != patch_id:
            continue
        restored_map[index].pop(REPAIR_KEY, None)
    return restored


def revert_patch(
    report: dict,
    patch: dict | None = None,
    indexes: list[int] | None = None,
) -> dict:
    """Alias of :func:`undo_patch`（撤销）, kept for the API naming discussion."""
    return undo_patch(report, patch=patch, indexes=indexes)


def repair_state(report: dict) -> dict:
    """Aggregate the persisted repair state for the report page / API."""
    by_index = _index_map(report)
    entries: list[dict] = []
    fixed = 0
    patch_ids: set[str] = set()
    for index, ref in by_index.items():
        record = _repair_of(ref)
        state = "fixed" if record and record.get("state") == "fixed" else "unfixed"
        if state == "fixed":
            fixed += 1
            patch_id = record.get("patch_id")
            if isinstance(patch_id, str) and patch_id:
                patch_ids.add(patch_id)
        entries.append(
            {
                "index": index,
                "state": state,
                "patch_id": (record or {}).get("patch_id") or "",
                "before": (record or {}).get("before") or "",
                "after": (record or {}).get("after") or "",
            }
        )
    total = len(by_index)
    if total and fixed == total:
        overall = "fixed"
    elif fixed:
        overall = "partially_fixed"
    else:
        overall = "unfixed"
    return {
        "schema": REPAIR_STATE_SCHEMA,
        "state": overall,
        "label": {
            "unfixed": "未修",
            "partially_fixed": "部分已修",
            "fixed": "已修",
        }[overall],
        "total": total,
        "fixed": fixed,
        "unfixed": total - fixed,
        "patch_ids": sorted(patch_ids),
        "entries": entries,
    }
