"""Topic → literature discovery over OpenAlex (module E).

Given a research topic, query the OpenAlex works index and return a ranked,
readable candidate list that can be imported into the local reference library.

This is a *discovery* helper, not a verification source: records are shown as
OpenAlex returns them. The ranking is a transparent heuristic (OpenAlex
relevance order + query overlap + citations + recency + open access), not a
learned ranker. It deliberately does not fetch or redistribute full texts.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import requests

from . import config
from .local_library import Library, LibraryEntry

OPENALEX_WORKS = "https://api.openalex.org/works"
MAX_RESULTS = 30
CACHE_TTL = 7 * 24 * 3600  # discovery results change slowly; a week is plenty
_TYPE_MAP = {
    "article": "J",
    "book-chapter": "M",
    "book": "M",
    "proceedings-article": "C",
    "dissertation": "D",
    "report": "R",
    "posted-content": "EB",
    "dataset": "DS",
}


class DiscoverError(RuntimeError):
    """Raised when the discovery source is unavailable or misbehaves."""


# ---------------------------------------------------------------------------
# Small cached GET (kept local so discovery can be tested without the verifier)
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    path = config.CACHE_DIR / "discover"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(url: str, params: dict) -> Path:
    key = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return _cache_dir() / (hashlib.md5(key.encode("utf-8")).hexdigest() + ".json")


def _read_cache(path: Path) -> Optional[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or "saved_at" not in payload:
        return None
    return payload


def _fetch_json(url: str, params: dict) -> dict:
    """GET JSON with a small on-disk cache and graceful stale fallback."""
    path = _cache_path(url, params)
    cached = _read_cache(path)
    if cached and time.time() - cached["saved_at"] < CACHE_TTL:
        return cached["data"]
    try:
        response = requests.get(
            url,
            params=params,
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": f"CiteGuard-CN ({config.OPENALEX_MAILTO})"},
        )
        if response.status_code >= 400:
            raise DiscoverError(f"OpenAlex 返回 HTTP {response.status_code}，请稍后重试")
        data = response.json()
    except DiscoverError:
        raise
    except Exception as exc:  # noqa: BLE001 - network layer
        if cached:
            return cached["data"]
        raise DiscoverError(f"OpenAlex 请求失败：{exc}") from exc
    path.write_text(json.dumps({"saved_at": time.time(), "data": data}, ensure_ascii=False),
                    encoding="utf-8")
    return data


# ---------------------------------------------------------------------------
# Mapping / ranking
# ---------------------------------------------------------------------------

def _short_id(value: str) -> str:
    return (value or "").rstrip("/").rsplit("/", 1)[-1]


def _to_item(work: dict) -> dict:
    authors = [
        ((a.get("author") or {}).get("display_name") or "").strip()
        for a in (work.get("authorships") or [])
    ]
    source = ((work.get("primary_location") or {}).get("source") or {}) or {}
    oa = work.get("open_access") or {}
    best = work.get("best_oa_location") or {}
    return {
        "title": (work.get("title") or "").strip(),
        "authors": [a for a in authors if a],
        "year": work.get("publication_year"),
        "venue": (source.get("display_name") or "").strip(),
        "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
        "openalex_id": _short_id(work.get("id") or ""),
        "type": work.get("type") or "",
        "language": work.get("language") or "",
        "cited_by": int(work.get("cited_by_count") or 0),
        "is_oa": bool(oa.get("is_oa")),
        "oa_url": best.get("pdf_url") or best.get("landing_page_url") or "",
    }


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9\-]{2,}")


def _query_overlap(query: str, title: str) -> float:
    """Fraction of query tokens/bigrams that appear in the title (0..1)."""
    q, t = (query or "").lower(), (title or "").lower()
    tokens: list[str] = _WORD_RE.findall(q)
    cjk = _CJK_RE.findall(q)
    for i in range(len(cjk) - 1):
        tokens.append(cjk[i] + cjk[i + 1])
    if not tokens:
        return 0.0
    return sum(1 for token in tokens if token in t) / len(tokens)


def rank(items: Iterable[dict], query: str, now_year: Optional[int] = None) -> list[dict]:
    """Heuristic re-rank: keep OpenAlex relevance, add overlap/citation/recency/OA."""
    now_year = now_year or datetime.now().year
    scored = []
    for index, item in enumerate(items):
        relevance = 1.0 / (1.0 + index)
        overlap = _query_overlap(query, item.get("title") or "")
        citations = 0.35 * min(math.log10(1 + int(item.get("cited_by") or 0)), 3.0)
        year = item.get("year") or 0
        recency = 0.3 if year >= now_year - 3 else 0.15 if year >= now_year - 8 else 0.0
        oa_bonus = 0.1 if item.get("is_oa") else 0.0
        score = relevance + 2.0 * overlap + citations + recency + oa_bonus
        scored.append((score, -index, item))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    out = []
    for score, _, item in scored:
        enriched = dict(item)
        enriched["match_score"] = round(score, 3)
        out.append(enriched)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_papers(
    query: str,
    *,
    limit: int = 20,
    year_from: Optional[int] = None,
    oa_only: bool = False,
) -> dict:
    """Search OpenAlex for a topic and return a ranked candidate list."""
    query = re.sub(r"\s+", " ", (query or "")).strip()
    if len(query) < 2:
        raise ValueError("请输入至少两个字符的研究主题")
    limit = max(1, min(int(limit or 20), MAX_RESULTS))
    filters = []
    if year_from:
        filters.append(f"from_publication_date:{int(year_from)}-01-01")
    if oa_only:
        filters.append("is_oa:true")
    params: dict[str, Any] = {
        "search": query,
        "per-page": limit,
        "sort": "relevance_score:desc",
        "select": (
            "id,doi,title,publication_year,authorships,primary_location,type,language,"
            "cited_by_count,open_access,best_oa_location"
        ),
        "mailto": config.OPENALEX_MAILTO,
    }
    if filters:
        params["filter"] = ",".join(filters)
    data = _fetch_json(OPENALEX_WORKS, params)
    results = [_to_item(work) for work in (data.get("results") or []) if work.get("title")]
    ranked = rank(results, query, now_year=datetime.now().year)[:limit]
    return {
        "query": query,
        "provider": "OpenAlex",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "matched": int(((data.get("meta") or {}).get("count")) or len(results)),
        "results": ranked,
    }


def import_entries(items: Iterable[dict], library_path: Optional[Path] = None) -> dict:
    """Add discovered records to the local library (dedupe by normalized title)."""
    path = Path(library_path or config.LIBRARY_FILE)
    library = Library.load(path)
    before = len(library)
    entries: list[LibraryEntry] = []
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        entries.append(
            LibraryEntry(
                title=title,
                authors=[str(a) for a in (item.get("authors") or []) if str(a).strip()],
                venue=(item.get("venue") or "").strip(),
                year=item.get("year") if isinstance(item.get("year"), int) else None,
                doi=(item.get("doi") or "").strip(),
                url=(item.get("oa_url") or "").strip(),
                doc_type=_TYPE_MAP.get((item.get("type") or "").lower(), ""),
                source="openalex-discover",
            )
        )
    library.add(entries)
    added = len(library) - before
    if added:
        library.save(path)
    return {
        "added": added,
        "skipped": max(0, len(entries) - added),
        "count": len(library),
    }


def render_csv(result: dict) -> str:
    """CSV for the discovery list (UTF-8 with BOM added by the caller)."""
    rows = ["题名,作者,年份,来源,被引,DOI,开放获取,链接"]
    for item in result.get("results") or []:
        title = (item.get("title") or "").replace('"', '""')
        authors = "; ".join(item.get("authors") or []).replace('"', '""')
        venue = (item.get("venue") or "").replace('"', '""')
        rows.append(
            f'"{title}","{authors}",{item.get("year") or ""},"{venue}",'
            f'{item.get("cited_by") or 0},"{item.get("doi") or ""}",'
            f'{"是" if item.get("is_oa") else "否"},"{item.get("oa_url") or ""}"'
        )
    return "\n".join(rows) + "\n"
