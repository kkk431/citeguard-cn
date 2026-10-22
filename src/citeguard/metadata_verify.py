"""Multi-source metadata verification: OpenAlex (CC0) -> Crossref -> arXiv.

Design goals:
- every candidate is traceable (source + URL);
- no API key required for OpenAlex/Crossref/arXiv;
- responses are cached under data/cache so evaluation runs are reproducible and cheap;
- failures degrade to ``Unknown`` instead of crashing.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from rapidfuzz import fuzz

from . import config
from .reference_parser import Reference

_ATOM = {"a": "http://www.w3.org/2005/Atom"}


@dataclass
class Candidate:
    source: str
    title: str
    doi: str = ""
    year: Optional[int] = None
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    abstract: str = ""
    url: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class VerifyResult:
    status: str  # Exact / Minor / Major / Unknown
    best: Optional[Candidate] = None
    title_sim: float = 0.0
    year_match: bool = False
    author_match: float = 0.0
    doi_status: str = "none"  # none / resolved / not_found / error
    mismatches: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Normalisation / similarity
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def norm_title(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = _PUNCT_RE.sub("", s)
    return s


def title_sim(a: str, b: str) -> float:
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    # token_set_ratio handles word reordering; ratio handles character-level Chinese.
    return max(fuzz.ratio(na, nb), fuzz.token_set_ratio(na, nb)) / 100.0


def _author_overlap(ref_authors: list[str], cand_authors: list[str]) -> float:
    if not ref_authors or not cand_authors:
        return 0.0
    ref = [norm_title(a) for a in ref_authors if norm_title(a)]
    cand = [norm_title(a) for a in cand_authors if norm_title(a)]
    if not ref or not cand:
        return 0.0
    hits = 0
    for r in ref:
        if any(r in c or c in r for c in cand if len(c) >= 2):
            hits += 1
    return hits / max(len(ref), 1)


def _year_match(ref_year: Optional[int], cand_year: Optional[int]) -> bool:
    # Exact match: a ±1 year difference is a real metadata drift (preprint vs
    # published version), and is reported as Minor rather than Exact.
    if ref_year is None or cand_year is None:
        return False
    return ref_year == cand_year


def _norm_field(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[\s\.,;:，；：、\(\)（）\[\]【】《》\-–—_/]+", "", s)
    return s


def _is_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


def _clean_abstract(raw: str, limit: int = 1800) -> str:
    """Strip JATS/XML tags from an abstract and cap its length."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _reconstruct_abstract(inverted: Optional[dict], limit: int = 1800) -> str:
    """OpenAlex stores abstracts as {word: [positions]}."""
    if not inverted:
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        if isinstance(positions, list):
            for p in positions:
                pairs.append((int(p), word))
    pairs.sort(key=lambda x: x[0])
    return _clean_abstract(" ".join(w for _, w in pairs), limit)


def _venue_match(ref_venue: str, cand_venue: str) -> bool:
    """True if venues match, or if either side is unknown (do not penalise)."""
    a, b = _norm_field(ref_venue), _norm_field(cand_venue)
    if not a or not b:
        return True
    return a in b or b in a or fuzz.ratio(a, b) / 100 >= 0.72


def _first_author_match(ref_authors: list[str], cand_authors: list[str]) -> bool:
    """Lenient author check.

    Chinese records often put an institution first ("四川大学华西第二医院") or
    include both the Chinese name and its pinyin ("黄程, Cheng Hong Huang").
    A strict first-author comparison therefore produces false mismatches. We
    accept if the first author matches, or if any of the first three reference
    authors overlaps with the first six source authors.
    """
    if not ref_authors or not cand_authors:
        return True
    ref = [norm_title(a) for a in ref_authors[:3] if norm_title(a)]
    cand = [norm_title(a) for a in cand_authors[:6] if norm_title(a)]
    if not ref or not cand:
        return True
    a, b = ref[0], cand[0]
    if a in b or b in a or fuzz.ratio(a, b) / 100 >= 0.55:
        return True
    for r in ref:
        if any(r in c or c in r for c in cand if len(c) >= 2):
            return True
    return False


def _volume_match(ref_v: str, cand_v: str) -> bool:
    a, b = _norm_field(ref_v), _norm_field(cand_v)
    if not a or not b:
        return True
    return a == b


def _pages_match(ref_p: str, cand_p: str) -> bool:
    a, b = _norm_field(ref_p), _norm_field(cand_p)
    if not a or not b:
        return True
    # compare first page only; page ranges often differ in end-page formatting
    fa = re.split(r"[-–—~]", a)[0]
    fb = re.split(r"[-–—~]", b)[0]
    if not fa or not fb:
        return True
    # tolerate electronic page prefixes such as "e39" vs "39"
    return fa == fb or fa in b or fb in a


def _author_order_mismatch(ref_authors: list[str], cand_authors: list[str]) -> bool:
    """Detect a re-ordered author list while tolerating institution/alias noise."""
    if not ref_authors or not cand_authors:
        return False
    a = norm_title(ref_authors[0])
    b = norm_title(cand_authors[0])
    if not a or not b:
        return False
    if a in b or b in a or fuzz.ratio(a, b) / 100 >= 0.55:
        return False
    rest = [norm_title(x) for x in cand_authors[1:6] if norm_title(x)]
    return any(a in c or c in a for c in rest)


def _field_mismatches(ref: Reference, cand: Candidate) -> list[str]:
    """Fields that differ between the reference and the matched record."""
    mism: list[str] = []
    if ref.year is not None and cand.year is not None and ref.year != cand.year:
        mism.append("year")
    if not _first_author_match(ref.authors, cand.authors):
        mism.append("authors")
    elif _author_order_mismatch(ref.authors, cand.authors):
        mism.append("authors_order")
    if not _venue_match(ref.venue, cand.venue):
        mism.append("venue")
    if not _volume_match(ref.volume, cand.volume):
        mism.append("volume")
    if not _pages_match(ref.pages, cand.pages):
        mism.append("pages")
    return mism


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return config.CACHE_DIR / f"{h}.json"


def _cached_json(url: str, params: Optional[dict] = None) -> Optional[Any]:
    key = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    cp = _cache_path(key)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        resp = requests.get(
            url,
            params=params,
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        time.sleep(config.API_SLEEP)
        return data
    except Exception:
        return None


def _cached_text(url: str, params: Optional[dict] = None) -> Optional[str]:
    key = "TEXT::" + url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    cp = _cache_path(key)
    if cp.exists():
        try:
            return cp.read_text(encoding="utf-8")
        except Exception:
            pass
    try:
        resp = requests.get(
            url,
            params=params,
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
        if resp.status_code != 200:
            return None
        text = resp.text
        cp.write_text(text, encoding="utf-8")
        time.sleep(config.API_SLEEP)
        return text
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------

def search_openalex(title: str, limit: int = 5) -> list[Candidate]:
    if not title or len(norm_title(title)) < 3:
        return []
    data = _cached_json(
        "https://api.openalex.org/works",
        {
            "search": title,
            "per-page": limit,
            "select": "id,doi,title,publication_year,authorships,primary_location,biblio,type,language,abstract_inverted_index",
            "mailto": config.OPENALEX_MAILTO,
        },
    )
    if not data:
        return []
    out: list[Candidate] = []
    for w in data.get("results", []) or []:
        try:
            authors = [
                (a.get("author") or {}).get("display_name", "")
                for a in (w.get("authorships") or [])
            ]
            src = ((w.get("primary_location") or {}).get("source") or {}) or {}
            biblio = w.get("biblio") or {}
            fp = biblio.get("first_page") or ""
            lp = biblio.get("last_page") or ""
            pages = f"{fp}-{lp}" if fp and lp else (fp or "")
            out.append(
                Candidate(
                    source="openalex",
                    title=w.get("title") or "",
                    doi=(w.get("doi") or "").replace("https://doi.org/", ""),
                    year=w.get("publication_year"),
                    authors=[a for a in authors if a],
                    venue=src.get("display_name", ""),
                    volume=str(biblio.get("volume") or ""),
                    issue=str(biblio.get("issue") or ""),
                    pages=str(pages),
                    abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
                    url=w.get("id", ""),
                )
            )
        except Exception:
            continue
    return out


def search_crossref(title: str, limit: int = 5) -> list[Candidate]:
    if not title or len(norm_title(title)) < 3:
        return []
    data = _cached_json(
        "https://api.crossref.org/works",
        {
            "query.bibliographic": title,
            "rows": limit,
            "select": "DOI,title,author,issued,container-title,type,volume,issue,page,abstract",
            "mailto": config.OPENALEX_MAILTO,
        },
    )
    if not data:
        return []
    out: list[Candidate] = []
    for it in (data.get("message", {}) or {}).get("items", []) or []:
        try:
            titles = it.get("title") or []
            authors = []
            for a in it.get("author") or []:
                name = " ".join(x for x in [a.get("given", ""), a.get("family", "")] if x).strip()
                if name:
                    authors.append(name)
            issued = (it.get("issued") or {}).get("date-parts") or [[None]]
            year = issued[0][0] if issued and issued[0] else None
            containers = it.get("container-title") or []
            out.append(
                Candidate(
                    source="crossref",
                    title=titles[0] if titles else "",
                    doi=it.get("DOI", ""),
                    year=year,
                    authors=authors,
                    venue=containers[0] if containers else "",
                    volume=str(it.get("volume") or ""),
                    issue=str(it.get("issue") or ""),
                    pages=str(it.get("page") or ""),
                    abstract=_clean_abstract(it.get("abstract", "")),
                    url=f"https://doi.org/{it.get('DOI', '')}" if it.get("DOI") else "",
                )
            )
        except Exception:
            continue
    return out


def search_arxiv(title: str, limit: int = 3) -> list[Candidate]:
    if not title or len(norm_title(title)) < 3:
        return []
    q = re.sub(r'["\\]', " ", title).strip()
    text = _cached_text(
        "http://export.arxiv.org/api/query",
        {"search_query": f'ti:"{q}"', "max_results": limit},
    )
    if not text:
        return []
    out: list[Candidate] = []
    try:
        root = ET.fromstring(text)
        for e in root.findall("a:entry", _ATOM):
            title_el = e.find("a:title", _ATOM)
            id_el = e.find("a:id", _ATOM)
            published = e.find("a:published", _ATOM)
            authors = [
                (a.find("a:name", _ATOM).text or "")
                for a in e.findall("a:author", _ATOM)
                if a.find("a:name", _ATOM) is not None
            ]
            year = None
            if published is not None and published.text:
                year = int(published.text[:4])
            out.append(
                Candidate(
                    source="arxiv",
                    title=(title_el.text or "").strip() if title_el is not None else "",
                    year=year,
                    authors=[a for a in authors if a],
                    url=(id_el.text or "").strip() if id_el is not None else "",
                )
            )
    except Exception:
        return []
    return out


def lookup_doi(doi: str) -> list[Candidate]:
    doi = (doi or "").strip()
    if not doi:
        return []
    out: list[Candidate] = []
    data = _cached_json(f"https://api.crossref.org/works/{doi}")
    if data:
        it = (data or {}).get("message", {}) or {}
        titles = it.get("title") or []
        authors = []
        for a in it.get("author") or []:
            name = " ".join(x for x in [a.get("given", ""), a.get("family", "")] if x).strip()
            if name:
                authors.append(name)
        issued = (it.get("issued") or {}).get("date-parts") or [[None]]
        containers = it.get("container-title") or []
        out.append(
            Candidate(
                source="crossref:doi",
                title=titles[0] if titles else "",
                doi=it.get("DOI", doi),
                year=issued[0][0] if issued and issued[0] else None,
                authors=authors,
                venue=containers[0] if containers else "",
                volume=str(it.get("volume") or ""),
                issue=str(it.get("issue") or ""),
                pages=str(it.get("page") or ""),
                abstract=_clean_abstract(it.get("abstract", "")),
                url=f"https://doi.org/{it.get('DOI', doi)}",
            )
        )
    data2 = _cached_json(f"https://api.openalex.org/works/https://doi.org/{doi}")
    if data2:
        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (data2.get("authorships") or [])
        ]
        src = ((data2.get("primary_location") or {}).get("source") or {}) or {}
        biblio = data2.get("biblio") or {}
        fp = biblio.get("first_page") or ""
        lp = biblio.get("last_page") or ""
        pages = f"{fp}-{lp}" if fp and lp else (fp or "")
        out.append(
            Candidate(
                source="openalex:doi",
                title=data2.get("title") or "",
                doi=(data2.get("doi") or "").replace("https://doi.org/", ""),
                year=data2.get("publication_year"),
                authors=[a for a in authors if a],
                venue=src.get("display_name", ""),
                volume=str(biblio.get("volume") or ""),
                issue=str(biblio.get("issue") or ""),
                pages=str(pages),
                abstract=_reconstruct_abstract(data2.get("abstract_inverted_index")),
                url=data2.get("id", ""),
            )
        )
    return out


def lookup_doi_status(doi: str) -> tuple[list[Candidate], str]:
    """Return (candidates, status), status in {resolved, not_found, error}.

    A missing DOI is a strong "fabricated reference" signal, so we distinguish
    a Crossref 404 from a network failure instead of collapsing both to [].
    """
    doi = (doi or "").strip()
    if not doi:
        return [], "not_found"
    cands = lookup_doi(doi)
    if cands:
        return cands, "resolved"
    cp = _cache_path("DOI_STATUS::" + doi)
    if cp.exists():
        try:
            return [], json.loads(cp.read_text(encoding="utf-8")).get("status", "not_found")
        except Exception:
            pass
    status = "error"
    try:
        resp = requests.get(
            f"https://api.crossref.org/works/{doi}",
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
        if resp.status_code == 404:
            status = "not_found"
        elif resp.status_code == 200:
            status = "resolved"
        else:
            status = "error"
    except Exception:
        status = "error"
    try:
        cp.write_text(json.dumps({"status": status}), encoding="utf-8")
    except Exception:
        pass
    time.sleep(config.API_SLEEP)
    return [], status


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _score_candidate(ref: Reference, cand: Candidate) -> tuple[float, bool, float]:
    ts = title_sim(ref.title, cand.title)
    ym = _year_match(ref.year, cand.year)
    am = _author_overlap(ref.authors, cand.authors)
    return ts, ym, am


def _pick_best(ref: Reference, candidates: list[Candidate]) -> Candidate:
    """Pick the best match, preferring a candidate that carries an abstract."""
    ranked = sorted(candidates, key=lambda c: title_sim(ref.title, c.title), reverse=True)
    top = ranked[0]
    top_sim = title_sim(ref.title, top.title)
    for c in ranked:
        if c.abstract and title_sim(ref.title, c.title) >= max(0.85, top_sim - 0.03):
            return c
    return top


def verify_reference(ref: Reference, use_arxiv: bool = True) -> VerifyResult:
    """Verify one reference.

    Decision rules (v1):
    - DOI resolves  -> compare year/authors/venue/volume/pages; mismatch => Minor,
      all consistent => Exact.
    - DOI 404       -> Major (fabricated DOI).
    - no DOI        -> title search; found + fields consistent => Exact,
      found + field drift => Minor, not found => Major.
    """
    notes: list[str] = []
    sources: list[str] = []

    # 1) DOI anchor.
    if ref.doi:
        doi_variants = [ref.doi]
        if ref.doi.endswith("_c"):
            doi_variants.append(ref.doi[:-2])
        if ref.doi.lower() != ref.doi:
            doi_variants.append(ref.doi.lower())

        doi_status = "not_found"
        doi_cands: list[Candidate] = []
        for d in dict.fromkeys(doi_variants):
            cands, status = lookup_doi_status(d)
            if status == "resolved":
                doi_cands = cands
                doi_status = "resolved"
                notes.append(f"DOI {d} resolved")
                break
            if status == "error":
                doi_status = "error"
                break
        if doi_status == "error":
            return VerifyResult(
                status="Unknown",
                doi_status="error",
                notes=notes + ["DOI lookup network error"],
                sources=["crossref:doi:error"],
            )
        if doi_status == "not_found":
            return VerifyResult(
                status="Major",
                doi_status="not_found",
                notes=notes + ["DOI 不存在（Crossref 404）"],
                sources=["crossref:doi:miss"],
            )

        best = _pick_best(ref, doi_cands)
        ts = title_sim(ref.title, best.title)
        ym = _year_match(ref.year, best.year)
        am = _author_overlap(ref.authors, best.authors)
        mism = _field_mismatches(ref, best)

        if ts < 0.50:
            if _is_cjk(ref.title) != _is_cjk(best.title):
                # Chinese citation vs English-only source record: language variant,
                # not a fabrication; keep it as Minor.
                mism.append("title_language")
            else:
                return VerifyResult(
                    status="Major",
                    best=best,
                    title_sim=round(ts, 4),
                    year_match=ym,
                    author_match=round(am, 4),
                    doi_status="resolved",
                    mismatches=["title"],
                    notes=notes + ["DOI resolved but title mismatch (title/DOI 错配)"],
                    sources=["crossref:doi", "openalex:doi"],
                )
        elif ts < 0.90:
            mism.append("title_partial")

        status = "Minor" if mism else "Exact"
        if mism:
            notes.append("DOI resolved; metadata mismatch: " + ",".join(mism))
        else:
            notes.append("DOI resolved; checked fields match")
        return VerifyResult(
            status=status,
            best=best,
            title_sim=round(ts, 4),
            year_match=ym,
            author_match=round(am, 4),
            doi_status="resolved",
            mismatches=mism,
            notes=notes,
            sources=["crossref:doi", "openalex:doi"],
        )

    # 2) No DOI: title search.
    candidates: list[Candidate] = []
    if ref.title and len(norm_title(ref.title)) >= 3:
        oa = search_openalex(ref.title)
        if oa:
            candidates.extend(oa)
            sources.append("openalex")
        cr = search_crossref(ref.title)
        if cr:
            candidates.extend(cr)
            sources.append("crossref")
        if use_arxiv and not oa and not cr:
            ax = search_arxiv(ref.title)
            if ax:
                candidates.extend(ax)
                sources.append("arxiv")

    if not candidates:
        return VerifyResult(
            status="Major",
            doi_status="none",
            notes=notes + ["title not found in open sources"],
            sources=sources,
        )

    scored: list[tuple[float, bool, float, Candidate]] = []
    for c in candidates:
        if not c.title:
            continue
        ts = title_sim(ref.title, c.title)
        ym = _year_match(ref.year, c.year)
        am = _author_overlap(ref.authors, c.authors)
        scored.append((ts, ym, am, c))
    if not scored:
        return VerifyResult(
            status="Major",
            doi_status="none",
            notes=notes + ["candidates without titles"],
            sources=sources,
        )

    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    ts, ym, am, best = scored[0]
    # Prefer an abstract-bearing candidate when the title similarities are close;
    # this keeps the claim-support step usable without changing the verdict.
    for ts2, ym2, am2, c in scored:
        if c.abstract and ts2 >= max(0.85, ts - 0.03):
            ts, ym, am, best = ts2, ym2, am2, c
            break

    if ts >= 0.90:
        mism = _field_mismatches(ref, best)
        status = "Minor" if mism else "Exact"
        notes.append("title matched" + (f"; mismatch: {','.join(mism)}" if mism else "; fields matched"))
    elif ts >= 0.78:
        status = "Minor"
        mism = ["title"]
        notes.append(f"partial title match ({ts:.2f})")
    else:
        status = "Major"
        mism = ["title"]
        notes.append(f"best title similarity only {ts:.2f}")

    return VerifyResult(
        status=status,
        best=best,
        title_sim=round(ts, 4),
        year_match=ym,
        author_match=round(am, 4),
        doi_status="none",
        mismatches=mism,
        notes=notes,
        sources=sources,
    )


def verify_many(
    refs: list[Reference],
    progress: bool = True,
    use_arxiv: bool = True,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> list[VerifyResult]:
    results: list[VerifyResult] = []
    for i, ref in enumerate(refs, 1):
        results.append(verify_reference(ref, use_arxiv=use_arxiv))
        if progress_cb is not None:
            try:
                progress_cb(i, len(refs))
            except Exception:
                pass
        if progress and (i % 10 == 0 or i == len(refs)):
            print(f"  verified {i}/{len(refs)}", flush=True)
    return results
