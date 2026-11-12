"""Retraction / correction checks for cited DOIs.

OpenAlex exposes ``is_retracted`` on a work; Crossref exposes update relations
(``updated-by`` / ``update-to``) for errata and corrections. Both are queried
through the same cached, rate-limit-aware helper used for metadata verification,
so a report never re-pays for the same DOI and a rate-limited source degrades to
"unknown" instead of pretending the paper is clean.
"""

from __future__ import annotations

import re

from .metadata_verify import _cached_json

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


def normalise_doi(value: str) -> str:
    doi = _DOI_PREFIX.sub("", (value or "").strip()).strip()
    return doi.rstrip(".").strip()


def check_doi(doi: str, check_corrections: bool = True) -> dict:
    """Return ``{status, source, title, detail}`` for one DOI.

    status is one of ``retracted`` / ``corrected`` / ``clean`` / ``error``.
    """
    doi = normalise_doi(doi)
    if not doi:
        return {"status": "error", "source": "", "title": "", "detail": "空 DOI"}
    if not doi.startswith("10."):
        return {"status": "error", "source": "", "title": "", "detail": "不是 DOI"}

    work = _cached_json(f"https://api.openalex.org/works/doi:{doi}")
    if work is None:
        return {"status": "error", "source": "openalex", "title": "", "detail": "OpenAlex 不可用"}
    title = (work.get("title") or work.get("display_name") or "").strip()
    if work.get("is_retracted"):
        return {
            "status": "retracted",
            "source": "openalex",
            "title": title,
            "detail": "OpenAlex 标记为已撤稿",
        }

    if check_corrections:
        record = _cached_json(f"https://api.crossref.org/works/{doi}")
        if record is not None:
            message = record.get("message") or {}
            relation = message.get("relation") or {}
            if relation.get("updated-by") or relation.get("update-to"):
                return {
                    "status": "corrected",
                    "source": "crossref",
                    "title": title or (message.get("title") or [""])[0],
                    "detail": "Crossref 记录了勘误/更新关系",
                }
    return {"status": "clean", "source": "openalex", "title": title, "detail": ""}


def status_label(status: str) -> str:
    return {
        "retracted": "已撤稿",
        "corrected": "有勘误/更新",
        "clean": "未发现撤稿",
        "error": "未完成检查",
    }.get(status, status)


def summarize(items: list[dict]) -> dict:
    counts = {"retracted": 0, "corrected": 0, "clean": 0, "error": 0}
    for item in items:
        status = item.get("status") or "error"
        counts[status] = counts.get(status, 0) + 1
    return {
        "checked": len(items),
        "retracted": counts["retracted"],
        "corrected": counts["corrected"],
        "clean": counts["clean"],
        "error": counts["error"],
    }
