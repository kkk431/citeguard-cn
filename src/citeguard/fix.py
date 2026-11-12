"""Deterministic "fix" pass for parsed references.

The product already tells a user *what* is wrong. This module turns the parsed
fields back into a GB/T 7714-style entry so the user can copy a corrected
reference list without retyping it. It is deliberately conservative: it only
re-typesets fields the parser recovered, never invents authors, venues or
years, and every entry carries warnings for the fields that were missing.
"""

from __future__ import annotations

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
