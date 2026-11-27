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


def _short_openalex_id(value: str) -> str:
    """Normalise ``https://openalex.org/W123`` and ``W123`` to ``W123``."""
    value = (value or "").strip().rstrip("/")
    return value.rsplit("/", 1)[-1] if value else ""


def check_chain(doi: str, max_refs: int = 20, *, max_hops: int = 1, hop2_limit: int = 3) -> dict:
    """Check whether a cited work references an already-retracted work.

    The default is one hop.  ``max_hops=2`` additionally checks the references
    of up to ``hop2_limit`` clean direct references, bounded so a chain query
    cannot explode.  ``coverage`` still says how many direct references
    OpenAlex returned; a clean result is never presented as "the whole chain is
    clean".

    Returns ``{status, checked, coverage, retracted, second_degree, ...}`` where
    status is ``indirect`` / ``clean`` / ``no_references`` / ``error``.
    """
    doi = normalise_doi(doi)
    if not doi or not doi.startswith("10."):
        return {
            "status": "error",
            "checked": 0,
            "coverage": 0.0,
            "retracted": [],
            "title": "",
            "detail": "不是有效 DOI",
        }
    work = _cached_json(f"https://api.openalex.org/works/doi:{doi}")
    if work is None:
        return {
            "status": "error",
            "checked": 0,
            "coverage": 0.0,
            "retracted": [],
            "title": "",
            "detail": "OpenAlex 不可用",
        }
    title = (work.get("title") or work.get("display_name") or "").strip()
    referenced = [_short_openalex_id(x) for x in (work.get("referenced_works") or [])]
    referenced = [x for x in referenced if x.startswith("W")]
    if not referenced:
        return {
            "status": "no_references",
            "checked": 0,
            "coverage": 0.0,
            "retracted": [],
            "title": title,
            "detail": "OpenAlex 未收录这篇文献的参考文献表",
        }
    sample = referenced[:max(1, max_refs)]
    filt = "|".join(sample)
    url = (
        "https://api.openalex.org/works"
        f"?filter=openalex_id:{filt}"
        "&select=id,doi,title,is_retracted,referenced_works&per-page=50"
    )
    batch = _cached_json(url)
    if batch is None:
        return {
            "status": "error",
            "checked": 0,
            "coverage": 0.0,
            "retracted": [],
            "title": title,
            "detail": "引用列表查询失败",
        }
    results = batch.get("results") or []
    retracted = [
        {
            "id": _short_openalex_id(item.get("id") or ""),
            "doi": item.get("doi") or "",
            "title": (item.get("title") or item.get("display_name") or "").strip(),
        }
        for item in results
        if item.get("is_retracted")
    ]
    second_degree: list[dict] = []
    second_sampled = 0
    if max_hops >= 2:
        sources = [
            item for item in results
            if not item.get("is_retracted") and (item.get("referenced_works") or [])
        ][: max(1, hop2_limit)]
        second_ids: list[str] = []
        for item in sources:
            for ref in item.get("referenced_works") or []:
                ref_id = _short_openalex_id(ref)
                if ref_id.startswith("W") and ref_id not in second_ids:
                    second_ids.append(ref_id)
        second_ids = second_ids[:20]
        second_sampled = len(second_ids)
        if second_ids:
            second_batch = _cached_json(
                "https://api.openalex.org/works"
                f"?filter=openalex_id:{'|'.join(second_ids)}"
                "&select=id,doi,title,is_retracted&per-page=50"
            )
            for item in (second_batch or {}).get("results") or []:
                if item.get("is_retracted"):
                    second_degree.append({
                        "id": _short_openalex_id(item.get("id") or ""),
                        "doi": item.get("doi") or "",
                        "title": (item.get("title") or item.get("display_name") or "").strip(),
                    })
    return {
        "status": "indirect" if (retracted or second_degree) else "clean",
        "sampled": len(sample),
        "checked": len(results),
        "coverage": round(len(results) / len(sample), 3) if sample else 0.0,
        "retracted": retracted,
        "second_degree": second_degree,
        "second_sampled": second_sampled,
        "max_hops": max_hops,
        "title": title,
        "detail": (
            f"抽样的 {len(results)} 条引用文献中，{len(retracted)} 条被撤稿"
            if retracted
            else (
                f"直接引用未发现撤稿；2 跳抽样 {second_sampled} 条中 {len(second_degree)} 条被撤稿"
                if second_degree
                else "本次抽样未发现撤稿"
            )
        ),
    }


def summarize_chain(items: list[dict]) -> dict:
    counts = {"indirect": 0, "clean": 0, "no_references": 0, "error": 0}
    total_checked = 0
    total_sampled = 0
    total_retracted = 0
    coverage: list[float] = []
    for item in items:
        status = item.get("status") or "error"
        counts[status] = counts.get(status, 0) + 1
        total_checked += int(item.get("checked") or 0)
        total_sampled += int(item.get("sampled") or item.get("checked") or 0)
        total_retracted += len(item.get("retracted") or [])
        if status in ("indirect", "clean") and item.get("coverage") is not None:
            coverage.append(float(item.get("coverage") or 0.0))
    return {
        "checked": len(items),
        "references_sampled": total_sampled,
        "references_checked": total_checked,
        "retracted_found": total_retracted,
        "indirect": counts["indirect"],
        "clean": counts["clean"],
        "no_references": counts["no_references"],
        "error": counts["error"],
        "average_coverage": round(sum(coverage) / len(coverage), 3) if coverage else 0.0,
    }


def status_label(status: str) -> str:
    return {
        "retracted": "已撤稿",
        "corrected": "有勘误/更新",
        "clean": "未发现撤稿",
        "error": "未完成检查",
        "indirect": "间接引用了撤稿文献",
        "no_references": "未收录参考文献表",
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
