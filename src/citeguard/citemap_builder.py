"""Build a CiteMap topic from a user-supplied query.

This is deliberately a *machine* layer: each paper contributes one finding
sentence from its abstract.  It is not a human extraction and the UI must keep
saying so.  The generated corpus and extraction use the existing
``evidence_map`` schema so the normal CiteMap page can render it.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import requests

from . import evidence_map

OPENALEX_WORKS = "https://api.openalex.org/works"
_UA = {"User-Agent": "CiteGuard-CN/1.7 CiteMap builder"}
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_RESULT_CUES = (
    "we find", "results show", "results suggest", "findings", "conclude",
    "associated with", "increased", "decreased", "improved", "reduced",
    "significant", "we show", "this study", "our results",
)
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "using",
    "based", "study", "studies", "paper", "papers", "research", "review",
    "effect", "effects", "analysis", "关于", "研究", "论文",
}


def _query_terms(query: str) -> list[str]:
    terms = [
        t for t in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", (query or "").lower())
        if t not in _STOPWORDS
    ]
    # De-duplicate while preserving order.
    seen: set[str] = set()
    return [t for t in terms if not (t in seen or seen.add(t))]



def _norm_topic_id(text: str) -> str:
    return "dyn_" + hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()[:8]


def _abstract(work: dict[str, Any]) -> str:
    index = work.get("abstract_inverted_index")
    if not isinstance(index, dict):
        return ""
    positions: dict[int, str] = {}
    for word, pos in index.items():
        if isinstance(pos, list):
            for p in pos:
                if isinstance(p, int):
                    positions[p] = word
    return " ".join(positions[p] for p in sorted(positions))


def _best_sentence(abstract: str) -> str:
    cleaned = " ".join(abstract.split())
    sentences = [s.strip() for s in _SENT_SPLIT.split(cleaned) if 60 <= len(s.strip()) <= 420]
    if not sentences:
        sentences = [cleaned[:420]] if cleaned else []
    if not sentences:
        return ""

    def score(sentence: str) -> int:
        lowered = sentence.lower()
        return sum(2 for cue in _RESULT_CUES if cue in lowered) + min(len(sentence) // 80, 2)

    return max(sentences, key=score)


def _work_to_paper(work: dict[str, Any], topic_id: str, idx: int) -> dict[str, Any] | None:
    title = (work.get("title") or "").strip()
    doi = (work.get("doi") or "").removeprefix("https://doi.org/").strip()
    year = work.get("publication_year")
    openalex_url = work.get("id") or ""
    openalex_id = openalex_url.rsplit("/", 1)[-1] if "/" in openalex_url else ""
    if not title or not doi or not isinstance(year, int) or not openalex_id.startswith("W"):
        return None

    authors: list[str] = []
    cn = False
    for authorship in (work.get("authorships") or [])[:10]:
        name = ((authorship or {}).get("author") or {}).get("display_name")
        if name:
            authors.append(name)
        for inst in (authorship or {}).get("institutions") or []:
            if (inst or {}).get("country_code") == "CN":
                cn = True
    if not authors:
        authors = ["Unknown"]

    loc = work.get("primary_location") or {}
    best = work.get("best_oa_location") or {}
    source = (loc.get("source") or {}) if isinstance(loc, dict) else {}
    venue = (source.get("display_name") or "").strip() or "Unknown venue"
    license_id = (
        (loc.get("license") or "").lower()
        or (best.get("license") or "").lower()
        or "unknown"
    )
    oa_url = (best.get("pdf_url") or best.get("landing_page_url") or "").strip()
    open_access = work.get("open_access") or {}
    is_oa = bool(open_access.get("is_oa")) and bool(oa_url)
    if is_oa and license_id in evidence_map.LICENSE_UNKNOWN_VALUES:
        is_oa = False
    fulltext = bool(is_oa and oa_url)
    oa_status = (open_access.get("oa_status") or "unknown").lower()

    return {
        "paper_id": f"dyn-{idx:03d}",
        "title": title[:1200],
        "authors": authors,
        "year": year,
        "venue": venue[:300],
        "doi": doi,
        "openalex_id": openalex_id.upper(),
        "url": f"https://doi.org/{doi}",
        "license": license_id if license_id else "unknown",
        "is_oa": is_oa,
        "fulltext_available": fulltext,
        "oa_url": oa_url if fulltext else "",
        "oa_status": oa_status if oa_status in evidence_map.OA_STATUSES else "unknown",
        "language": (work.get("language") or "en")[:20],
        "topic_id": topic_id,
        "cn_affiliated": cn,
        "cited_by": int(work.get("cited_by_count") or 0),
        "source": "openalex",
        "notes": "用户输入主题后自动检索；仅元数据与摘要，不下载全文",
    }


def search_works(query: str, limit: int = 15) -> list[dict[str, Any]]:
    params = {
        "search": query,
        "per-page": max(1, min(limit, 50)),
        "filter": "has_abstract:true,has_doi:true",
        "sort": "relevance_score:desc",
        "select": (
            "id,doi,title,publication_year,authorships,primary_location,"
            "best_oa_location,open_access,cited_by_count,language,"
            "abstract_inverted_index"
        ),
    }
    try:
        response = requests.get(OPENALEX_WORKS, params=params, timeout=30, headers=_UA)
        response.raise_for_status()
        return list((response.json() or {}).get("results") or [])
    except requests.RequestException as exc:
        raise RuntimeError(f"OpenAlex 检索失败：{exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _register_topic(data_dir: Path, entry: dict[str, Any]) -> None:
    index_path = data_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    topics = [t for t in index.get("topics", []) if t.get("topic_id") != entry["topic_id"]]
    topics.insert(0, entry)
    index["topics"] = topics
    index["generated_at"] = date.today().isoformat()
    _write_json(index_path, index)


def build_from_topic(
    topic: str,
    *,
    question: str = "",
    query: str = "",
    limit: int = 15,
    data_dir: str | Path | None = None,
    works_override: list[dict[str, Any]] | None = None,
    source_label: str = "",
) -> dict[str, Any]:
    """Search OpenAlex, extract machine findings, register a CiteMap topic."""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic 不能为空")
    limit = max(5, min(int(limit), 30))
    search_query = (query or topic).strip()
    works = list(works_override) if works_override is not None else search_works(search_query, limit=limit * 2)
    terms = _query_terms(search_query) if works_override is None else []
    abstract_map = {id(w): _abstract(w) for w in works}
    if terms:
        required = 2 if len(terms) >= 4 else 1
        ranked: list[tuple[int, int, dict[str, Any]]] = []
        for order, work in enumerate(works):
            hay = (str(work.get("title") or "") + " " + abstract_map.get(id(work), "")).lower()
            matched = sum(1 for term in terms if term in hay)
            if matched >= required:
                ranked.append((matched, -order, work))
        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        works = [row[2] for row in ranked]
    abstract_map = {id(w): _abstract(w) for w in works}

    papers: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    topic_id = _norm_topic_id(topic)

    for work in works:
        if len(papers) >= limit:
            break
        abstract = abstract_map.get(id(work), "")
        sentence = _best_sentence(abstract)
        paper = _work_to_paper(work, topic_id, len(papers) + 1)
        if paper is None or not sentence:
            continue
        papers.append(paper)
        claim_id = f"{topic_id}-c{len(claims) + 1:03d}"
        claim_text = sentence if len(sentence) <= 1200 else sentence[:1197] + "..."
        claims.append(
            {
                "claim_id": claim_id,
                "topic_id": topic_id,
                "text": claim_text,
                "population": "",
                "outcome": "",
                "direction": "",
                "notes": "机器生成：摘要中的结果句，未人审",
            }
        )
        evidence.append(
            {
                "evidence_id": f"{topic_id}-e{len(evidence) + 1:03d}",
                "claim_id": claim_id,
                "paper_id": paper["paper_id"],
                "stance": "support",
                "summary": "机器抽取：摘要结果句，仅证明论文报告过该发现，不做跨论文综合",
                "quote": sentence,
                "quote_lang": "en",
                "locator": "Abstract",
                "confidence": 0.35,
                "extracted_by": "machine:abstract-finding",
                "verified": False,
                "notes": "自动生成；人工未核对。不要把本层当作人工金标。",
            }
        )

    if len(papers) < 5:
        raise ValueError("可用摘要论文不足 5 篇，请换一个更宽泛的主题或稍后重试")

    data_root = Path(data_dir) if data_dir is not None else evidence_map.DEFAULT_DATA_DIR
    rel_dir = Path("dynamic") / topic_id
    topic_obj = {
        "topic_id": topic_id,
        "name_zh": topic,
        "name_en": topic,
        "question": (question or f"{topic} 的主要证据、争议与空白是什么？")[:600],
        "description": "用户输入主题后现场检索生成的机器证据地图；非人工抽取，未人审。",
    }
    corpus = {
        "schema_version": "1.0",
        "topic": topic_obj,
        "generated_at": date.today().isoformat(),
        "source": source_label or f"OpenAlex Works API：{search_query}（{date.today().isoformat()}）",
        "selection": "用户提供的 DOI 列表" if works_override is not None else "按相关性检索，取有摘要/有 DOI 的前若干篇；不下载全文",
        "notes": "机器生成，未人审；仅摘要级证据，不能当作系统综述或元分析。",
        "papers": papers,
    }
    extraction = {
        "schema_version": "1.0",
        "topic": topic_obj,
        "extractor": "machine:abstract-finding",
        "extracted_at": date.today().isoformat(),
        "protocol": "每篇摘要选一句结果句作为机器断言；引用为该句；未做跨论文核对。",
        "claims": claims,
        "evidence": evidence,
        "gaps": [],
    }

    # Validate before writing so a broken map never appears as a topic.
    evidence_map.CorpusManifest.from_dict(corpus)
    evidence_map.EvidenceMap.from_dict(extraction)

    _write_json(data_root / rel_dir / "corpus.json", corpus)
    _write_json(data_root / rel_dir / "extractions.json", extraction)
    entry = {
        "topic_id": topic_id,
        "name_zh": topic,
        "name_en": topic,
        "question": topic_obj["question"],
        "corpus": str((rel_dir / "corpus.json")).replace("\\", "/"),
        "extractions": str((rel_dir / "extractions.json")).replace("\\", "/"),
        "papers": len(papers),
        "claims": len(claims),
        "evidence": len(evidence),
        "gaps": 0,
        "machine": True,
    }
    _register_topic(data_root, entry)
    return {"topic_id": topic_id, "papers": len(papers), "claims": len(claims), "evidence": len(evidence)}


def _normalise_doi(value: str) -> str:
    doi = (value or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "DOI:"):
        if doi.lower().startswith(prefix.lower()):
            doi = doi[len(prefix):]
            break
    return doi.strip()


def lookup_dois(dois: list[str]) -> list[dict[str, Any]]:
    """Fetch OpenAlex works for a user-provided DOI list (max 20)."""
    import urllib.parse

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in dois[:20]:
        doi = _normalise_doi(raw)
        if not doi or doi.lower() in seen:
            continue
        seen.add(doi.lower())
        try:
            response = requests.get(
                f"{OPENALEX_WORKS}/doi:{urllib.parse.quote(doi, safe='')}",
                params={
                    "select": (
                        "id,doi,title,publication_year,authorships,primary_location,"
                        "best_oa_location,open_access,cited_by_count,language,"
                        "abstract_inverted_index"
                    )
                },
                timeout=20,
                headers=_UA,
            )
            if response.status_code != 200:
                continue
            work = response.json()
        except (requests.RequestException, ValueError):
            continue
        if isinstance(work, dict) and work.get("id"):
            out.append(work)
    return out


def build_from_dois(
    topic: str,
    dois: list[str],
    *,
    question: str = "",
    limit: int = 20,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a machine map from a user-supplied DOI list instead of a search."""
    cleaned = [_normalise_doi(d) for d in (dois or []) if _normalise_doi(d)]
    if len(cleaned) < 5:
        raise ValueError("至少需要 5 个 DOI；多余或不存在的 DOI 会被跳过")
    works = lookup_dois(cleaned)
    if len(works) < 5:
        raise ValueError("能取到摘要的 DOI 不足 5 篇，请检查 DOI 或稍后重试")
    return build_from_topic(
        topic,
        question=question,
        limit=min(max(5, len(works)), min(int(limit), 20)),
        data_dir=data_dir,
        works_override=works,
        source_label=f"用户提供 DOI 列表（{len(works)} 篇，OpenAlex 元数据/摘要）",
    )
