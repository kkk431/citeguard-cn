"""CiteGuard Live: check one selected sentence against open literature metadata.

The browser extension sends the sentence a reader highlighted on a web page.
Live does **not** read the page's full text and does not try to prove whether
the sentence is true.  It retrieves a handful of candidate papers from
OpenAlex / Crossref, looks at their abstracts, and returns one of four labels:

``support`` / ``partial`` / ``contradict`` / ``no_evidence``

When the page can be identified as a paper (DOI/arXiv URL, or a close tab-title
match), Live first uses that work's ``referenced_works`` as candidates (at most
40 references, abstract-only).  Otherwise it falls back to the keyword search.
Page enrichment is best effort and never raises.

Two important guarantees:

* an evidence object is returned only when its ``quote`` is an exact excerpt of
  the candidate abstract (after finding the sentence, no wording is invented);
* the module works without a configured judge model.  In that case a
  transparent lexical fallback labels the claim from term / number overlap.

The FastAPI route for this module is owned by ``web/app.py``; see
``docs/live.md`` for the HTTP contract.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Optional
from urllib.parse import quote, unquote, urlparse

from . import config, support
from .metadata_verify import (
    Candidate,
    _cached_json,
    _reconstruct_abstract,
    search_crossref,
    search_openalex,
    title_sim,
)

LIVE_LABELS = ("support", "partial", "contradict", "no_evidence")
MAX_CLAIM_CHARS = 500
MAX_CANDIDATES = 5
MAX_PAGE_TITLE_CHARS = 300
MAX_PAGE_URL_CHARS = 2048
MAX_ABSTRACT_CHARS = 2000
MAX_QUOTE_CHARS = 600
MAX_REFERENCED_WORKS = 40
REFERENCE_BATCH_SIZE = 50
PAGE_TITLE_MIN_SIM = 0.6

_OPENALEX_WORKS = "https://api.openalex.org/works"
_PAGE_WORK_SELECT = "id,doi,title,publication_year,referenced_works"
_REFERENCE_SELECT = (
    "id,doi,title,publication_year,authorships,primary_location,"
    "abstract_inverted_index"
)
_DOI_IN_URL_RE = re.compile(r"10\.\d{4,9}/[^\s?#<>\"']+", re.I)
_ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/|10\.48550/arxiv\.)"
    r"(?P<id>\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?",
    re.I,
)

_CITATION_RE = re.compile(r"\[\d+(?:\s*[-–—,，]\s*\d+)*\]")
_CJK_BLOCK_RE = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-']*")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%?")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*|(?<=[.])\s+(?=[A-Z0-9“\"(])")
_CLAUSE_SPLIT_RE = re.compile(r"[，,；;。!?？]|(?:\band\b)|(?:以及|并且|同时|而且|还|也)")

_EN_STOP = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "it", "its", "we", "our",
    "they", "their", "study", "paper", "article", "results", "result",
    "shows", "show", "found", "using", "based", "can", "may", "might",
    "will", "would", "should", "has", "have", "had", "than", "into",
}
_CN_STOP_BIGRAMS = {
    "的是", "我们", "他们", "本文", "研究", "表明", "以及", "并且", "但是",
    "然而", "因此", "从而", "对于", "关于", "一个", "一种", "这些", "那些",
    "可以", "能够", "进行", "使用", "采用", "基于",
}
_NEG_CUES = (
    "未发现", "没有发现", "无显著", "未显著", "没有显著", "不能", "未能",
    "无效", "不支持", "并未", "没有", "not significantly", "no significant",
    "did not", "does not", "failed to", "no evidence", "without",
)
_POS_CUES = (
    "提高", "提升", "增加", "促进", "改善", "有效", "正向", "显著", "support",
    "improve", "increase", "enhance", "effective", "positive", "benefit", "better",
)
_LABEL_PRIORITY = {"support": 4, "contradict": 3, "partial": 2, "no_evidence": 1, "not_checked": 0}


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _stem(word: str) -> str:
    """A deliberately small lexicon-free stemmer for English overlap scoring."""
    word = word.lower()
    if len(word) > 6:
        return word[:6]
    return word


def _terms(text: str) -> set[str]:
    """Content terms for lexical overlap: English stems + CJK character bigrams."""
    terms: set[str] = set()
    for match in _LATIN_WORD_RE.finditer(text or ""):
        word = match.group(0).lower().strip("'")
        if len(word) < 2 or word in _EN_STOP:
            continue
        terms.add(_stem(word))
    for block in _CJK_BLOCK_RE.findall(text or ""):
        if len(block) == 1:
            terms.add(block)
            continue
        for i in range(len(block) - 1):
            bigram = block[i : i + 2]
            if bigram not in _CN_STOP_BIGRAMS:
                terms.add(bigram)
    return terms


def _numbers(text: str) -> set[str]:
    out: set[str] = set()
    for match in _NUMBER_RE.finditer(text or ""):
        token = match.group(0).replace(",", "").replace(" ", "")
        if token:
            out.add(token)
    return out


def _coverage(claim_terms: set[str], text_terms: set[str]) -> float:
    if not claim_terms:
        return 0.0
    return len(claim_terms & text_terms) / float(len(claim_terms))


def _number_coverage(claim_numbers: set[str], text_numbers: set[str]) -> float:
    if not claim_numbers:
        return 0.0
    return len(claim_numbers & text_numbers) / float(len(claim_numbers))


def _polarity(text: str) -> int:
    lowered = (text or "").lower()
    if any(cue in lowered for cue in _NEG_CUES):
        return -1
    if any(cue in lowered for cue in _POS_CUES):
        return 1
    return 0


def _sentences(text: str) -> list[str]:
    """Split a candidate abstract without normalising its whitespace.

    Returns stripped slices that remain substrings of ``text``; this is what
    makes the evidence quote verifiable.
    """
    if not text or not text.strip():
        return []
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part and part.strip()]


def _claim_clauses(claim: str) -> list[str]:
    parts = _CLAUSE_SPLIT_RE.split(claim or "")
    return [part.strip() for part in parts if part and part.strip()]


def _build_query(claim: str, page_title: str = "") -> str:
    """Turn a selected sentence into a short literature query.

    The full sentence is not a good title query.  Keep CJK blocks and English
    content words, drop citation markers / punctuation / stopwords, and fall
    back to the page title when the selected sentence is mostly a pronoun.
    """
    text = _CITATION_RE.sub(" ", claim or "").strip()
    parts: list[str] = []
    for block in _CJK_BLOCK_RE.findall(text):
        block = block.strip()
        if block:
            parts.append(block[:60])
    for match in _LATIN_WORD_RE.finditer(text):
        word = match.group(0).strip("'")
        if len(word) >= 2 and word.lower() not in _EN_STOP:
            parts.append(word)
    query = " ".join(parts).strip()
    if len(query) < 3:
        query = text
    if len(query) < 3 and page_title:
        query = page_title
    return query[:160].strip()


def _norm_title(title: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", (title or "").lower())


def _candidate_url(candidate: Candidate) -> str:
    if candidate.url:
        return candidate.url
    if candidate.doi:
        return "https://doi.org/" + candidate.doi
    return ""


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    out: list[Candidate] = []
    for candidate in candidates:
        key = (
            (candidate.doi or "").strip().lower()
            or _norm_title(candidate.title)
            or (candidate.url or "").strip()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _candidate_score(claim_terms: set[str], claim_numbers: set[str], candidate: Candidate) -> float:
    text = (candidate.title or "") + " " + (candidate.abstract or "")
    text_terms = _terms(text)
    text_numbers = _numbers(text)
    return round(0.8 * _coverage(claim_terms, text_terms) + 0.2 * _number_coverage(claim_numbers, text_numbers), 4)


def _candidate_payload(candidate: Candidate, score: float, verdict: Optional[dict] = None) -> dict:
    item = {
        "title": candidate.title or "",
        "authors": list(candidate.authors or [])[:8],
        "year": candidate.year,
        "venue": candidate.venue or "",
        "doi": candidate.doi or "",
        "url": _candidate_url(candidate),
        "source": candidate.source or "",
        "abstract": (candidate.abstract or "")[:MAX_ABSTRACT_CHARS],
        "score": score,
    }
    if verdict:
        item["label"] = verdict.get("label", "no_evidence")
        item["confidence"] = round(float(verdict.get("confidence") or 0.0), 3)
    return item


def _search_candidates(query: str, page_title: str = "") -> tuple[list[Candidate], list[str]]:
    """Query both metadata adapters; never let a transport error escape."""
    found: list[Candidate] = []
    errors: list[str] = []
    for search in (search_openalex, search_crossref):
        try:
            found.extend(search(query, limit=MAX_CANDIDATES) or [])
        except Exception as exc:  # noqa: BLE001 - Live must degrade, not 500
            errors.append(f"{getattr(search, '__name__', 'search')}: {exc}")
    if not found and page_title and _norm_title(page_title) != _norm_title(query):
        try:
            found.extend(search_openalex(page_title, limit=MAX_CANDIDATES) or [])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"search_openalex(page_title): {exc}")
    return found, errors


def _ground_quote(quote: str, abstract: str) -> str:
    """Return an exact excerpt of ``abstract`` for a model/heuristic quote.

    A model may normalise punctuation or wrap a quote in Chinese quotation
    marks.  In those cases we find the sentence that contains the quote's
    wording and return that *exact* sentence; if nothing matches, return an
    empty string.  We never manufacture a sentence.
    """
    raw = str(quote or "").strip()
    if not raw:
        return ""
    variants = [raw, raw.strip('"“”\'`')]
    for variant in variants:
        if variant and variant in abstract:
            return variant[:MAX_QUOTE_CHARS]
    if support.evidence_grounded(raw, abstract, min_len=8):
        for sentence in _sentences(abstract):
            if support.evidence_grounded(raw, sentence, min_len=8):
                return sentence[:MAX_QUOTE_CHARS]
    return ""


def _normalise_judge(result: dict) -> dict:
    label = str(result.get("label") or "no_evidence").strip().lower()
    if label not in LIVE_LABELS:
        label = "no_evidence"
    try:
        confidence = float(result.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "label": label,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(result.get("reason") or "").strip(),
        "quote": str(result.get("evidence") or result.get("evidence_quote") or "").strip(),
    }


def _judge_verdicts(claim: str, candidates: list[Candidate]) -> dict[int, dict]:
    verdicts: dict[int, dict] = {}
    checked = 0
    for candidate in candidates:
        if not (candidate.abstract or "").strip():
            continue
        try:
            result = support.judge_support(claim, candidate.abstract, title=candidate.title, doi=candidate.doi)
        except Exception:  # noqa: BLE001 - model transport failure falls back
            result = None
        if result:
            verdicts[id(candidate)] = _normalise_judge(result)
        checked += 1
        if checked >= 3:
            break
    return verdicts


def _pick_judged(candidates: list[Candidate], verdicts: dict[int, dict]) -> tuple[Optional[Candidate], Optional[dict]]:
    best_candidate: Optional[Candidate] = None
    best_verdict: Optional[dict] = None
    for candidate in candidates:
        verdict = verdicts.get(id(candidate))
        if not verdict:
            continue
        key = (_LABEL_PRIORITY.get(verdict["label"], 0), verdict["confidence"])
        if best_verdict is None or key > (
            _LABEL_PRIORITY.get(best_verdict["label"], 0),
            best_verdict["confidence"],
        ):
            best_candidate, best_verdict = candidate, verdict
    return best_candidate, best_verdict


def _judged_result(
    claim: str,
    candidates: list[Candidate],
    scores: dict[int, float],
    verdicts: dict[int, dict],
) -> dict:
    best_candidate, best = _pick_judged(candidates, verdicts)
    if best_candidate is None or best is None:
        raise RuntimeError("no judge verdict")
    label = best["label"]
    confidence = best["confidence"]
    reason = best["reason"] or "判定模型未给出理由"
    if label == "no_evidence":
        return _make_result(
            "no_evidence",
            min(confidence, 0.4),
            reason,
            None,
            [_candidate_payload(c, scores[id(c)], verdicts.get(id(c))) for c in candidates],
        )

    quote = _ground_quote(best["quote"], best_candidate.abstract)
    evidence = None
    if quote:
        evidence = {
            "title": best_candidate.title or "",
            "url": _candidate_url(best_candidate),
            "quote": quote,
        }
    else:
        confidence = min(confidence, 0.55)
        if best["quote"]:
            reason += "；判定模型给出的证据句未能在摘要中逐字核对，已不附证据"
        else:
            reason += "；判定模型未给出可核对的证据句，已不附证据"
    return _make_result(
        label,
        confidence,
        reason,
        evidence,
        [_candidate_payload(c, scores[id(c)], verdicts.get(id(c))) for c in candidates],
    )


def _heuristic_hit(claim: str, candidates: list[Candidate]) -> Optional[dict]:
    claim_terms = _terms(claim)
    claim_numbers = _numbers(claim)
    claim_polarity = _polarity(claim)
    clauses = [clause for clause in _claim_clauses(claim) if _terms(clause)]
    best: Optional[dict] = None

    for candidate in candidates:
        abstract = (candidate.abstract or "").strip()
        if not abstract:
            continue
        for sentence in _sentences(abstract):
            if len(sentence) < 12:
                continue
            sentence_terms = _terms(sentence)
            coverage = _coverage(claim_terms, sentence_terms)
            number_coverage = _number_coverage(claim_numbers, _numbers(sentence))
            if not claim_terms and not claim_numbers:
                continue
            if claim_terms and coverage < 0.2 and number_coverage == 0:
                continue
            clause_coverages = [_coverage(_terms(clause), sentence_terms) for clause in clauses]
            min_clause = min(clause_coverages) if clause_coverages else 1.0
            polarity = _polarity(sentence)

            label: Optional[str] = None
            confidence = 0.0
            if polarity and claim_polarity and polarity != claim_polarity and coverage >= 0.35:
                label = "contradict"
                confidence = min(0.82, 0.5 + 0.2 * coverage)
            elif (
                claim_terms
                and coverage >= 0.45
                and (not claim_numbers or number_coverage >= 1.0)
                and min_clause >= 0.35
            ):
                if polarity == -1 and claim_polarity != -1:
                    label = "partial"
                    confidence = min(0.7, 0.35 + 0.25 * coverage + 0.1 * number_coverage)
                else:
                    label = "support"
                    confidence = min(0.92, 0.55 + 0.3 * coverage + 0.15 * number_coverage)
            elif (claim_terms and coverage >= 0.28) or (claim_numbers and number_coverage > 0):
                label = "partial"
                confidence = min(0.7, 0.35 + 0.25 * coverage + 0.1 * number_coverage)

            if not label:
                continue
            ranking = (_LABEL_PRIORITY[label], confidence)
            if best is None or ranking > (_LABEL_PRIORITY[best["label"]], best["confidence"]):
                best = {
                    "candidate": candidate,
                    "sentence": sentence[:MAX_QUOTE_CHARS],
                    "label": label,
                    "confidence": round(confidence, 3),
                    "coverage": coverage,
                    "number_coverage": number_coverage,
                }
    return best


def _heuristic_result(
    claim: str,
    candidates: list[Candidate],
    scores: dict[int, float],
) -> dict:
    hit = _heuristic_hit(claim, candidates)
    base_candidates = [_candidate_payload(c, scores[id(c)]) for c in candidates]
    if hit is None:
        return _make_result(
            "no_evidence",
            0.0,
            "未配置判定模型；本地规则未在候选摘要中找到与引用句关键词/数字足够重合的句子",
            None,
            base_candidates,
        )
    candidate = hit["candidate"]
    verdict = {"label": hit["label"], "confidence": hit["confidence"]}
    payloads = []
    for item, c in zip(base_candidates, candidates):
        if c is candidate:
            item = dict(item)
            item["label"] = verdict["label"]
            item["confidence"] = verdict["confidence"]
        payloads.append(item)
    coverage_pct = int(round(hit["coverage"] * 100))
    detail = f"未配置判定模型，使用本地规则兜底：候选摘要句关键词覆盖 {coverage_pct}%"
    if _numbers(claim):
        detail += f"，数字命中 {int(round(hit['number_coverage'] * 100))}%"
    if hit["label"] == "contradict":
        detail += "；该句的方向与引用句相反"
    evidence = {
        "title": candidate.title or "",
        "url": _candidate_url(candidate),
        "quote": hit["sentence"],
    }
    return _make_result(hit["label"], hit["confidence"], detail, evidence, payloads)


def _make_result(label: str, confidence: float, reason: str, evidence: Optional[dict], candidates: list[dict]) -> dict:
    label = label if label in LIVE_LABELS else "no_evidence"
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    if evidence is not None and not (evidence.get("quote") or "").strip():
        evidence = None
    return {
        "label": label,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "reason": str(reason or ""),
        "evidence": evidence,
        "candidates": list(candidates or [])[:MAX_CANDIDATES],
    }


def _page_suffix(page_url: str) -> str:
    host = urlparse(page_url or "").netloc
    return f"；页面：{host}" if host else ""


def _extract_page_doi(page_url: str) -> str:
    """Return the first DOI visible in a page URL, without trailing punctuation."""
    text = unquote(str(page_url or ""))
    match = _DOI_IN_URL_RE.search(text)
    if not match:
        return ""
    return match.group(0).rstrip(".,;:)]}'\"<>")


def _extract_arxiv_id(page_url: str) -> str:
    """Return an arXiv identifier from /abs/ or /pdf/ URLs (old and new style)."""
    match = _ARXIV_ID_RE.search(unquote(str(page_url or "")))
    return match.group("id") if match else ""


def _strip_doi_prefix(value: Any) -> str:
    doi = str(value or "").strip()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    return doi.rstrip(".,;:)]}'\"<>")


def _work_to_candidate(work: Any) -> Optional[Candidate]:
    """Convert one OpenAlex work dict to the shared ``Candidate`` shape."""
    if not isinstance(work, dict):
        return None
    try:
        authors = [
            (authorship.get("author") or {}).get("display_name", "")
            for authorship in (work.get("authorships") or [])
            if isinstance(authorship, dict)
        ]
        source = ((work.get("primary_location") or {}).get("source") or {})
        return Candidate(
            source="openalex",
            title=str(work.get("title") or ""),
            doi=_strip_doi_prefix(work.get("doi")),
            year=work.get("publication_year"),
            authors=[author for author in authors if author],
            venue=str((source or {}).get("display_name") or ""),
            abstract=_reconstruct_abstract(work.get("abstract_inverted_index")),
            url=str(work.get("id") or ""),
            raw={"from": "referenced_works"},
        )
    except Exception:  # noqa: BLE001 - a malformed row must not break Live
        return None


def _work_by_doi(doi: str) -> Optional[dict]:
    doi = _strip_doi_prefix(doi)
    if not doi:
        return None
    encoded = quote(f"https://doi.org/{doi}", safe=":/")
    try:
        data = _cached_json(
            f"{_OPENALEX_WORKS}/{encoded}",
            {"select": _PAGE_WORK_SELECT, "mailto": config.OPENALEX_MAILTO},
        )
    except Exception:  # noqa: BLE001 - page enrichment is best effort
        return None
    if isinstance(data, dict) and data.get("id"):
        return data
    return None


def _work_by_title(page_title: str) -> Optional[dict]:
    """Find the OpenAlex work whose title is closest to the browser tab title."""
    title = _clean_text(page_title)
    if len(title) < 3:
        return None
    try:
        data = _cached_json(
            _OPENALEX_WORKS,
            {
                "search": title,
                "per-page": 5,
                "select": _PAGE_WORK_SELECT,
                "mailto": config.OPENALEX_MAILTO,
            },
        )
    except Exception:  # noqa: BLE001 - page enrichment is best effort
        return None
    results = (data or {}).get("results", []) if isinstance(data, dict) else []
    best: Optional[dict] = None
    best_similarity = 0.0
    for work in results or []:
        if not isinstance(work, dict):
            continue
        similarity = title_sim(title, str(work.get("title") or ""))
        if similarity > best_similarity:
            best, best_similarity = work, similarity
    if best is not None and best_similarity >= PAGE_TITLE_MIN_SIM:
        return best
    return None


def _page_work(page_url: str, page_title: str = "") -> Optional[dict]:
    """Resolve the paper currently open in the browser, if possible.

    DOI/arXiv URLs take the fast path.  If that lookup fails (or the URL has no
    identifier), a title search is accepted only when the best hit is close to
    the tab title; a wrong "current paper" would make its references worse than
    an ordinary keyword search.
    """
    doi = _extract_page_doi(page_url)
    if doi:
        work = _work_by_doi(doi)
        if work:
            return work
    arxiv_id = _extract_arxiv_id(page_url)
    if arxiv_id:
        work = _work_by_doi(f"10.48550/arxiv.{arxiv_id.lower()}")
        if work:
            return work
    if page_title:
        return _work_by_title(page_title)
    return None


def _referenced_candidates(work: Any) -> list[Candidate]:
    """Turn up to 40 ``referenced_works`` of an OpenAlex work into candidates.

    References are fetched in batches of 50 and abstracts are reconstructed
    from OpenAlex's inverted index.  Any transport / parse error is silent:
    Live then falls back to its keyword search instead of failing the request.
    """
    if not isinstance(work, dict):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for raw in work.get("referenced_works") or []:
        match = re.search(r"(W\d{6,})", str(raw or ""))
        if not match:
            continue
        work_id = match.group(1)
        if work_id in seen:
            continue
        seen.add(work_id)
        ids.append(work_id)
        if len(ids) >= MAX_REFERENCED_WORKS:
            break
    if not ids:
        return []

    found: list[Candidate] = []
    for start in range(0, len(ids), REFERENCE_BATCH_SIZE):
        batch = ids[start : start + REFERENCE_BATCH_SIZE]
        try:
            data = _cached_json(
                _OPENALEX_WORKS,
                {
                    "filter": "openalex_id:" + "|".join(batch),
                    "per-page": REFERENCE_BATCH_SIZE,
                    "select": _REFERENCE_SELECT,
                    "mailto": config.OPENALEX_MAILTO,
                },
            )
        except Exception:  # noqa: BLE001 - references are an optional accelerator
            continue
        results = (data or {}).get("results", []) if isinstance(data, dict) else []
        by_id: dict[str, Candidate] = {}
        for row in results or []:
            candidate = _work_to_candidate(row)
            if candidate is None:
                continue
            match = re.search(r"(W\d{6,})", candidate.url or "")
            if match:
                by_id[match.group(1)] = candidate
        for work_id in batch:
            candidate = by_id.get(work_id)
            if candidate is not None:
                found.append(candidate)
    return found


def _merge_candidates(
    page_candidates: list[Candidate],
    keyword_candidates: list[Candidate],
) -> list[Candidate]:
    """Merge reference-list hits before keyword hits, de-duplicating by DOI/title."""
    return _dedupe(list(page_candidates or []) + list(keyword_candidates or []))


def check_claim(claim: str, page_url: str = "", page_title: str = "") -> dict:
    """Check one selected sentence against candidate abstracts.

    Parameters
    ----------
    claim:
        The sentence highlighted by the reader.  Leading/trailing whitespace is
        stripped; the first ``MAX_CLAIM_CHARS`` characters are used.
    page_url, page_title:
        Optional context from the browser tab.  A DOI/arXiv URL is resolved to
        an OpenAlex work and its reference list is tried first; the title is
        used as a fallback query when the selected sentence is too short and as
        a lookup key when the URL has no identifier.  The DOI/arXiv identifier
        (or title) is sent to OpenAlex; the page's URL/HTML itself is not
        fetched.  The URL host is included in no-result reasons.

    Returns
    -------
    dict
        ``{label, confidence, reason, evidence, candidates}``.  ``evidence`` is
        ``None`` unless a quote is an exact excerpt of a candidate abstract.
    """
    claim = _clean_text(claim)[:MAX_CLAIM_CHARS]
    page_url = str(page_url or "").strip()[:MAX_PAGE_URL_CHARS]
    page_title = _clean_text(page_title)[:MAX_PAGE_TITLE_CHARS]

    if not claim:
        return _make_result("no_evidence", 0.0, "引用句为空，未进行核验", None, [])

    if config.OFFLINE:
        return _make_result(
            "no_evidence",
            0.0,
            "离线模式：CiteGuard Live 不检索外部文献" + _page_suffix(page_url),
            None,
            [],
        )

    query = _build_query(claim, page_title)
    claim_terms = _terms(claim)
    claim_numbers = _numbers(claim)

    # If the browser tab is a paper page we can resolve, its reference list is a
    # much better candidate set than a keyword search over a Chinese sentence.
    # Page enrichment is best effort: no network error may escape here.
    try:
        page_work = _page_work(page_url, page_title)
    except Exception:  # noqa: BLE001 - optional enrichment must not fail Live
        page_work = None
    try:
        page_candidates = _referenced_candidates(page_work) if page_work else []
    except Exception:  # noqa: BLE001
        page_candidates = []
    page_candidates = _dedupe(page_candidates)
    page_ranked = sorted(
        page_candidates,
        key=lambda candidate: _candidate_score(claim_terms, claim_numbers, candidate),
        reverse=True,
    )
    page_usable = any((candidate.abstract or "").strip() for candidate in page_ranked)

    keyword_candidates: list[Candidate] = []
    errors: list[str] = []
    if not page_usable and query:
        keyword_candidates, errors = _search_candidates(query, page_title)

    if not page_ranked and not keyword_candidates:
        if not query:
            reason = "无法从引用句提取检索关键词" + _page_suffix(page_url)
        elif errors:
            reason = "检索失败：OpenAlex/Crossref 均不可用（网络、限流或服务异常）" + _page_suffix(page_url)
        else:
            reason = "未检索到候选文献（OpenAlex/Crossref 无结果，或网络不可用）" + _page_suffix(page_url)
        return _make_result("no_evidence", 0.0, reason, None, [])

    merged = _merge_candidates(page_ranked, keyword_candidates)
    if not page_usable:
        # A page reference without an abstract cannot support a judgement; keep
        # abstract-bearing keyword hits ahead of it while still preserving the
        # page-first order for equal evidence.
        merged.sort(
            key=lambda candidate: (
                bool((candidate.abstract or "").strip()),
                _candidate_score(claim_terms, claim_numbers, candidate),
            ),
            reverse=True,
        )
    ranked = merged[:MAX_CANDIDATES]
    scores = {id(candidate): _candidate_score(claim_terms, claim_numbers, candidate) for candidate in ranked}

    if not any((candidate.abstract or "").strip() for candidate in ranked):
        return _make_result(
            "no_evidence",
            0.0,
            "检索到候选文献，但摘要字段为空，无法做摘要级判断" + _page_suffix(page_url),
            None,
            [_candidate_payload(c, scores[id(c)]) for c in ranked],
        )

    try:
        judge_available = bool(support.judge_available())
    except Exception:  # noqa: BLE001
        judge_available = False
    if judge_available:
        verdicts = _judge_verdicts(claim, ranked)
        if verdicts:
            return _judged_result(claim, ranked, scores, verdicts)
        # A configured endpoint can still fail over the network.  Degrade
        # explicitly instead of returning an empty "support" by accident.
        result = _heuristic_result(claim, ranked, scores)
        result["reason"] = "判定模型调用失败，已降级为本地规则判断；" + result["reason"]
        return result

    return _heuristic_result(claim, ranked, scores)


def main(argv: Optional[list[str]] = None) -> int:
    # The JSON payload contains Chinese reasons.  Force UTF-8 on Windows
    # consoles/pipes as well, so stdout is a predictable JSON document.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="python -m citeguard.live_check",
        description="Check one selected sentence against OpenAlex / Crossref abstracts.",
    )
    parser.add_argument("--claim", required=True, help="要核查的引用句（最多 500 字）")
    parser.add_argument("--page-url", default="", help="可选：选中句所在页面 URL")
    parser.add_argument("--page-title", default="", help="可选：页面标题")
    args = parser.parse_args(argv)
    try:
        result = check_claim(args.claim, page_url=args.page_url, page_title=args.page_title)
    except Exception as exc:  # noqa: BLE001 - CLI should print a JSON error, not a traceback
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
