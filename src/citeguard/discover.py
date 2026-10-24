"""Topic → literature discovery over OpenAlex (module E).

Given a topic (Chinese or English), query the OpenAlex works index and return a
ranked, readable candidate list that can be imported into the local reference
library.

Design notes:
- Chinese topics are *also* searched in English when an OpenAI-compatible judge
  is configured: the LLM only produces a translation/keyword list, never facts,
  and the expansion is shown in the UI. Without a judge the feature degrades to
  plain OpenAlex search (and says so).
- Ranking is a transparent heuristic over OpenAlex relevance + title overlap +
  citations + recency + open access. It is not a learned ranker.
- Records are deduped by DOI/title; retracted works are hidden unless asked for.
- Only public metadata is consumed; no full text is fetched or stored.
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
from .support import judge_available, judge_endpoint

OPENALEX_WORKS = "https://api.openalex.org/works"
MAX_RESULTS = 50
MAX_PAGE = 5
MAX_PER_PAGE = 100
ABSTRACT_CHARS = 240
CACHE_TTL = 7 * 24 * 3600  # discovery results change slowly; a week is plenty
EXPAND_VERSION = 2
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
_SORTS = ("relevance", "citations", "year")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9\-]{2,}")
_WS_RE = re.compile(r"\s+")


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


def _norm_title(title: str) -> str:
    return _WS_RE.sub("", (title or "").lower())


def _reconstruct_abstract(index: Any) -> str:
    """OpenAlex abstract_inverted_index -> a short plain-text snippet."""
    if not isinstance(index, dict) or not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, spots in index.items():
        if not isinstance(spots, list):
            continue
        for pos in spots:
            if isinstance(pos, int):
                positions.append((pos, word))
    positions.sort(key=lambda row: row[0])
    text = " ".join(word for _, word in positions)
    return _WS_RE.sub(" ", text).strip()


def _to_item(work: dict) -> dict:
    authors = [
        ((a.get("author") or {}).get("display_name") or "").strip()
        for a in (work.get("authorships") or [])
    ]
    source = ((work.get("primary_location") or {}).get("source") or {}) or {}
    oa = work.get("open_access") or {}
    best = work.get("best_oa_location") or {}
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
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
        "abstract": abstract[:ABSTRACT_CHARS],
        "retracted": bool(work.get("is_retracted")),
        "relevance_score": float(work.get("relevance_score") or 0.0),
    }


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


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


def _matched_terms(query: str, title: str, keywords: Iterable[str] = ()) -> list[str]:
    """Readable matched query words, for the UI's 「命中」 explanation."""
    text = (title or "").lower()
    hits: list[str] = []
    for word in _WORD_RE.findall((query or "").lower()) + list(keywords or []):
        word = (word or "").strip()
        if len(word) >= 2 and word.lower() in text and word.lower() not in [h.lower() for h in hits]:
            hits.append(word)
    cjk = _CJK_RE.findall(query or "")
    seen_grams: list[str] = []
    for i in range(len(cjk) - 1):
        gram = cjk[i] + cjk[i + 1]
        if gram in text and gram not in seen_grams:
            seen_grams.append(gram)
    hits.extend(seen_grams)
    # collapse Chinese bigrams into their source words when possible
    words = [w for w in re.split(r"[\s,，、;；/]+", query or "") if len(w) >= 2]
    result: list[str] = []
    for word in words:
        if word.lower() in text and word not in result:
            result.append(word)
    for hit in hits:
        if hit not in result and not any(hit in r for r in result):
            result.append(hit)
    return result[:4]


def rank(items: Iterable[dict], query: str, now_year: Optional[int] = None,
         keywords: Iterable[str] = (), alt_query: str = "") -> list[dict]:
    """Heuristic re-rank: OpenAlex relevance + overlap + citations + recency + OA.

    ``alt_query`` is the English expansion query; an item matching either query
    counts as a title hit, so English results are not punished just because the
    user typed Chinese.
    """
    now_year = now_year or datetime.now().year
    rows = list(items)
    explicit = any("relevance" in item for item in rows)
    max_relevance = max((float(it.get("relevance_score") or 0.0) for it in rows), default=0.0)
    scored = []
    for index, item in enumerate(rows):
        if explicit:
            relevance = max(0.0, float(item.get("relevance") or 0.0))
        elif max_relevance > 0 and item.get("relevance_score"):
            relevance = min(1.0, float(item["relevance_score"]) / max_relevance)
        else:
            relevance = 1.0 / (1.0 + index)
        title = item.get("title") or ""
        overlap = _query_overlap(query, title)
        if alt_query:
            overlap = max(overlap, _query_overlap(alt_query, title))
        kw_overlap = 0.0
        if keywords:
            kw_overlap = _query_overlap(" ".join(str(k) for k in keywords), title)
        citations = 0.35 * min(math.log10(1 + int(item.get("cited_by") or 0)), 3.0)
        year = item.get("year") or 0
        recency = 0.3 if year >= now_year - 3 else 0.15 if year >= now_year - 8 else 0.0
        oa_bonus = 0.1 if item.get("is_oa") else 0.0
        score = 1.0 * relevance + 2.0 * overlap + 0.9 * kw_overlap + citations + recency + oa_bonus
        if item.get("retracted"):
            score -= 1.0
        enriched = dict(item)
        enriched["match_score"] = round(score, 3)
        matched = _matched_terms(query, title, keywords)
        if not matched and alt_query:
            matched = _matched_terms(alt_query, title, keywords)
        enriched["matched_terms"] = matched
        if matched:
            enriched["reason"] = "命中：" + "、".join(matched)
            if alt_query and not _matched_terms(query, title):
                enriched["reason"] = "英文扩展命中：" + "、".join(matched)
        else:
            enriched["reason"] = ""
        scored.append((score, -index, enriched))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [row[2] for row in scored]


def _dedupe(items: Iterable[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    order: list[str] = []
    for item in items:
        key = (item.get("doi") or "").lower().strip() or _norm_title(item.get("title") or "")
        if not key:
            continue
        if key not in seen:
            seen[key] = dict(item)
            order.append(key)
            continue
        kept = seen[key]
        if len(item.get("abstract") or "") > len(kept.get("abstract") or ""):
            kept["abstract"] = item.get("abstract") or ""
        kept["cited_by"] = max(int(kept.get("cited_by") or 0), int(item.get("cited_by") or 0))
        kept["is_oa"] = bool(kept.get("is_oa") or item.get("is_oa"))
        if not kept.get("oa_url"):
            kept["oa_url"] = item.get("oa_url") or ""
        if not kept.get("doi"):
            kept["doi"] = item.get("doi") or ""
    return [seen[key] for key in order]


def _apply_sort(items: list[dict], sort: str) -> list[dict]:
    if sort == "citations":
        return sorted(items, key=lambda it: (int(it.get("cited_by") or 0), it.get("year") or 0),
                      reverse=True)
    if sort == "year":
        return sorted(items, key=lambda it: (it.get("year") or 0, int(it.get("cited_by") or 0)),
                      reverse=True)
    return items  # already relevance-ranked


# ---------------------------------------------------------------------------
# Query expansion (Chinese topic -> English query + keywords)
# ---------------------------------------------------------------------------

def _expand_cache_path(query: str, model: str) -> Path:
    digits = hashlib.md5(f"v{EXPAND_VERSION}|{model}|{query}".encode("utf-8")).hexdigest()
    path = _cache_dir() / "expand"
    path.mkdir(parents=True, exist_ok=True)
    return path / (digits + ".json")


def expand_query(query: str) -> Optional[dict]:
    """Translate a Chinese topic into English and extract keywords.

    Returns ``None`` when no judge is configured or the call fails; the caller
    then searches with the original query and reports the degradation.
    """
    if not judge_available():
        return None
    base, model, key = judge_endpoint()
    cache = _expand_cache_path(query, model)
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("en") and isinstance(cached.get("keywords"), list):
            return cached
    except Exception:
        pass
    prompt = (
        "把下面的中文研究主题转成适合在 OpenAlex/Google Scholar 检索的英文检索式，"
        "并给出 3–6 个中英文关键词（英文为主，可保留中文原词）。检索式用 1–3 组核心词，总长不超过 120 字符，不要堆砌同义词。只输出 JSON："
        '{"en": "英文检索式", "keywords": ["关键词1", "关键词2"]}。'
        "不要解释，不要编造具体文献。"
    )
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是严谨的学术检索助手。"},
            {"role": "user", "content": prompt + "\n\n主题：" + query},
        ],
        "temperature": 0,
        "max_tokens": 220,
    }
    try:
        response = requests.post(base.rstrip("/") + "/chat/completions",
                                 headers=headers, json=payload,
                                 timeout=max(20, config.HTTP_TIMEOUT))
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.S)
        data = json.loads(match.group(0)) if match else {}
    except Exception:
        return None
    en = str(data.get("en") or "").strip().strip('"')
    keywords = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()]
    if not en or len(en) > 320:
        return None
    result = {"en": en, "keywords": keywords[:6], "model": model}
    try:
        cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _work_params(query: str, per_page: int, year_from: Optional[int],
                 oa_only: bool) -> dict:
    filters = []
    if year_from:
        filters.append(f"from_publication_date:{int(year_from)}-01-01")
    if oa_only:
        filters.append("is_oa:true")
    params: dict[str, Any] = {
        "search": query,
        "per-page": per_page,
        "sort": "relevance_score:desc",
        "select": (
            "id,doi,title,publication_year,authorships,primary_location,type,language,"
            "cited_by_count,open_access,best_oa_location,abstract_inverted_index,"
            "is_retracted,relevance_score"
        ),
        "mailto": config.OPENALEX_MAILTO,
    }
    if filters:
        params["filter"] = ",".join(filters)
    return params


def search_papers(
    query: str,
    *,
    limit: int = 20,
    year_from: Optional[int] = None,
    oa_only: bool = False,
    page: int = 1,
    sort: str = "relevance",
    expand: str = "auto",
    include_retracted: bool = False,
) -> dict:
    """Search OpenAlex for a topic and return a ranked candidate list.

    ``expand``: ``"auto"`` (expand Chinese topics when a judge is configured),
    ``"on"`` (always try), ``"off"`` (never).
    """
    query = _WS_RE.sub(" ", (query or "")).strip()
    if len(query) < 2:
        raise ValueError("请输入至少两个字符的研究主题")
    limit = max(1, min(int(limit or 20), MAX_RESULTS))
    page = max(1, min(int(page or 1), MAX_PAGE))
    sort = sort if sort in _SORTS else "relevance"
    # Fetch a stable pool for every page so re-ranking cannot shift items between pages.
    per_page = MAX_PER_PAGE

    expansion = None
    if expand == "on" or (expand == "auto" and _has_cjk(query)):
        expansion = expand_query(query)
    queries = [query]
    if expansion and expansion.get("en") and expansion["en"].lower() != query.lower():
        queries.append(expansion["en"])

    items: list[dict] = []
    matched = 0
    for query_index, q in enumerate(queries):
        data = _fetch_json(OPENALEX_WORKS, _work_params(q, per_page, year_from, oa_only))
        works = [work for work in (data.get("results") or []) if work.get("title")]
        matched = max(matched, int(((data.get("meta") or {}).get("count")) or 0))
        raw = [_to_item(work) for work in works]
        query_max = max((float(item.get("relevance_score") or 0.0) for item in raw), default=0.0)
        for item in raw:
            item["relevance"] = (float(item.get("relevance_score") or 0.0) / query_max
                                 if query_max > 0 else 0.0)
            item["via"] = "base" if query_index == 0 else "expansion"
            items.append(item)

    retracted_filtered = 0
    if not include_retracted:
        before = len(items)
        items = [item for item in items if not item["retracted"]]
        retracted_filtered = before - len(items)
    items = _dedupe(items)
    keywords = expansion.get("keywords") if expansion else []
    alt_query = queries[1] if len(queries) > 1 else ""
    ranked = rank(items, query, now_year=datetime.now().year, keywords=keywords or [],
                  alt_query=alt_query)
    ranked = _apply_sort(ranked, sort)
    start = (page - 1) * limit
    visible = ranked[start:start + limit]

    return {
        "query": query,
        "expanded_query": expansion.get("en") if expansion else "",
        "expansion": expansion,
        "queries": queries,
        "provider": "OpenAlex",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "matched": matched,
        "page": page,
        "page_size": limit,
        "has_more": len(ranked) > start + limit or matched > page * limit,
        "retracted_filtered": retracted_filtered,
        "sort": sort,
        "expand": expand,
        "results": visible,
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
    rows = ["题名,作者,年份,来源,被引,语言,DOI,开放获取,链接"]
    for item in result.get("results") or []:
        title = (item.get("title") or "").replace('"', '""')
        authors = "; ".join(item.get("authors") or []).replace('"', '""')
        venue = (item.get("venue") or "").replace('"', '""')
        rows.append(
            f'"{title}","{authors}",{item.get("year") or ""},"{venue}",'
            f'{item.get("cited_by") or 0},"{item.get("language") or ""}",'
            f'"{item.get("doi") or ""}",'
            f'{"是" if item.get("is_oa") else "否"},"{item.get("oa_url") or ""}"'
        )
    return "\n".join(rows) + "\n"
