"""Multi-source metadata verification: OpenAlex (CC0) -> Crossref -> arXiv.

Design goals:
- every candidate is traceable (source + URL);
- no API key required for OpenAlex/Crossref/arXiv;
- responses are cached under data/cache so evaluation runs are reproducible and cheap;
- failures degrade to ``Unknown`` instead of crashing.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import ipaddress
import json
import logging
import os
import re
import socket
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import requests
from rapidfuzz import fuzz

from . import config
from .reference_parser import Reference

_LOGGER = logging.getLogger(__name__)

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
    retracted: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class VerifyResult:
    status: str  # Exact / Minor / Major / Unverified / Unknown
    best: Optional[Candidate] = None
    title_sim: float = 0.0
    year_match: bool = False
    author_match: float = 0.0
    doi_status: str = "none"
    # none / local / resolved / resolved_landing / exists_elsewhere /
    # not_found / error
    mismatches: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    retracted: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _apply_retraction(result: "VerifyResult") -> "VerifyResult":
    """Surface the OpenAlex retraction flag without changing metadata status.

    Retraction is orthogonal to "does this citation match its record": a
    retracted paper can still be cited accurately, but the user should know
    before relying on it. Keeping ``status`` unchanged avoids turning a
    legitimate citation into a false accusation.
    """
    if result.best is not None and getattr(result.best, "retracted", False):
        result.retracted = True
        if not any("撤稿" in n for n in result.notes):
            result.notes.append(
                "OpenAlex 标记该文献已被撤稿（retraction），引用前请核对原文与撤稿声明"
            )
    return result


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


def _surname(name: str) -> str:
    """Comparable family name, tolerant of "Surname, I. N." vs "Given Surname".

    Chinese citations list "Li, D." or "李东"; Crossref/OpenAlex return
    "Dongping Li". Comparing full strings would call every correct citation an
    author mismatch, so compare family names only.
    """
    n = unicodedata.normalize("NFKC", name or "").strip()
    if not n:
        return ""
    if _is_cjk(n):
        return norm_title(n)
    if re.search(r"[,，]", n):
        # "Smith, J. D." / "van der Waals, J." -> the part before the comma
        return norm_title(re.split(r"[,，]", n)[0])
    tokens = [t for t in re.split(r"[\s\-‐–—]+", n) if t]
    # "Given Family": drop trailing initial tokens and keep the last word.
    while len(tokens) > 1 and re.fullmatch(r"[A-Z]\.|[A-Z]", tokens[-1]):
        tokens.pop()
    return norm_title(tokens[-1]) if tokens else ""


def _same_surname(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    # tolerate name particles and transliteration differences
    return len(a) >= 2 and len(b) >= 2 and (a in b or b in a)


def _author_overlap(ref_authors: list[str], cand_authors: list[str]) -> float:
    if not ref_authors or not cand_authors:
        return 0.0
    ref = [_surname(a) for a in ref_authors if _surname(a)]
    cand = [_surname(a) for a in cand_authors if _surname(a)]
    if not ref or not cand:
        return 0.0
    hits = 0
    for r in ref:
        if any(_same_surname(r, c) for c in cand):
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


_VENUE_ALIASES = {
    # CS conferences: a reference usually prints the acronym, the index prints
    # the proceedings title; both must compare equal, not "Minor".
    "neurips": "neural information processing systems",
    "nips": "neural information processing systems",
    "icml": "international conference on machine learning",
    "iclr": "international conference on learning representations",
    "acl": "association for computational linguistics",
    "emnlp": "empirical methods in natural language processing",
    "naacl": "north american chapter of the association for computational linguistics",
    "eacl": "european chapter of the association for computational linguistics",
    "coling": "international conference on computational linguistics",
    "cvpr": "computer vision and pattern recognition",
    "iccv": "international conference on computer vision",
    "eccv": "european conference on computer vision",
    "aaai": "aaai conference on artificial intelligence",
    "ijcai": "international joint conference on artificial intelligence",
    "kdd": "knowledge discovery and data mining",
    "sigir": "research and development in information retrieval",
    "www": "world wide web",
    "mm": "acm multimedia",
    "osdi": "operating systems design and implementation",
    "sosp": "symposium on operating systems principles",
    "nsdi": "networked systems design and implementation",
    "sigcomm": "special interest group on data communication",
    "pldi": "programming language design and implementation",
    "popl": "principles of programming languages",
    "icse": "international conference on software engineering",
    "fse": "foundations of software engineering",
    "ase": "automated software engineering",
    "issta": "software testing and analysis",
    "icra": "international conference on robotics and automation",
    "iros": "intelligent robots and systems",
    "miccai": "medical image computing and computer assisted intervention",
    "tpami": "pattern analysis and machine intelligence",
    "jmlr": "journal of machine learning research",
    "tacl": "transactions of the association for computational linguistics",
    "tmlr": "transactions on machine learning research",
}


def _canonical_venue(value: str) -> str:
    s = _norm_field(value)
    if not s:
        return ""
    for short, full in _VENUE_ALIASES.items():
        s = re.sub(rf"\b{re.escape(short)}\b", full, s)
    # _norm_field removes spaces; keep both sides compact so containment works.
    return s.replace(" ", "")


def _venue_match(ref_venue: str, cand_venue: str) -> bool:
    """True if venues match, or if either side is unknown (do not penalise)."""
    a, b = _canonical_venue(ref_venue), _canonical_venue(cand_venue)
    if not a or not b:
        return True
    return a in b or b in a or fuzz.ratio(a, b) / 100 >= 0.72


def _first_author_match(ref_authors: list[str], cand_authors: list[str]) -> bool:
    """Lenient author check.

    Chinese records often put an institution first ("四川大学华西第二医院") or
    include both the Chinese name and its pinyin ("黄程, Cheng Hong Huang").
    A strict comparison therefore produces false mismatches. We accept if the
    first author matches, or if any of the first three reference authors
    overlaps with the first six source authors (family names compared).
    """
    if not ref_authors or not cand_authors:
        return True
    ref = [_surname(a) for a in ref_authors[:3] if _surname(a)]
    cand = [_surname(a) for a in cand_authors[:6] if _surname(a)]
    if not ref or not cand:
        return True
    if _same_surname(ref[0], cand[0]):
        return True
    return any(_same_surname(r, c) for r in ref for c in cand)


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
    ref = [_surname(a) for a in ref_authors[:3] if _surname(a)]
    cand = [_surname(a) for a in cand_authors[:6] if _surname(a)]
    if not ref or not cand:
        return False
    if _same_surname(ref[0], cand[0]):
        return False
    return any(_same_surname(ref[0], c) for c in cand[1:])


_INITIALS_ONLY_RE = re.compile(r"^(?:[A-Za-z]\.(?:\s*[A-Za-z]\.)*|[A-Za-z])$")
_ET_AL_TOKEN_RE = re.compile(r"^(?:et\s*al\.?|等|等人)$", re.I)


def _authors_unreliable(authors: list[str]) -> bool:
    """True when the cited author list is too fragmentary to compare.

    PDF/OCR extraction of APA-style lists sometimes leaves pieces like "D." or
    a lone "et al."; comparing those against a full record would invent author
    mismatches.
    """
    if not authors:
        return True
    real = [a for a in authors if not _ET_AL_TOKEN_RE.match((a or "").strip().strip(".,;，；"))]
    if not real:
        return True
    weak = 0
    for author in real:
        # Do not strip the trailing period: "W.K." is an initials fragment, and
        # truncating it to "W.K" would hide the fragment from the checks below.
        cleaned = (author or "").strip().strip(",，;；")
        if _INITIALS_ONLY_RE.match(cleaned):
            # A lone set of initials is never a complete author name once the
            # parser has merged "Surname, I. N." pairs — the list is fragmentary.
            return True
        if len(norm_title(cleaned)) < 2:
            weak += 1
    return weak * 2 >= len(real)


def _field_mismatches(ref: Reference, cand: Candidate) -> list[str]:
    """Fields that differ between the reference and the matched record.

    A field the citation does not really contain is never reported as a
    mismatch: that would be a parse limitation, not an error in the paper.
    """
    mism: list[str] = []
    if ref.year is not None and cand.year is not None and ref.year != cand.year:
        mism.append("year")
    if not _authors_unreliable(ref.authors):
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


# Count of failed source requests (rate limits / network / 5xx). Used to tell
# "we found nothing" apart from "the data source was unavailable".
_source_errors = 0
_source_errors_lock = threading.Lock()


def _note_source_failure() -> None:
    global _source_errors
    with _source_errors_lock:
        _source_errors += 1


def source_error_count() -> int:
    with _source_errors_lock:
        return _source_errors


def _request(url: str, params: Optional[dict] = None, tries: int = 3):
    """GET with retries on rate limits / transient server errors.

    Returns the final ``requests.Response`` or raises the last transport error.
    ``tries`` total attempts with linear backoff (0.8s, 1.6s, ...).
    """
    last_error: Optional[Exception] = None
    response = None
    for attempt in range(max(1, tries)):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=config.HTTP_TIMEOUT,
                headers={"User-Agent": config.USER_AGENT},
            )
        except Exception as exc:  # noqa: BLE001 - retry transport errors
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
            continue
        if response.status_code in {429, 500, 502, 503, 504} and attempt + 1 < tries:
            time.sleep(0.8 * (attempt + 1))
            continue
        return response
    if last_error is not None:
        raise last_error
    return response  # type: ignore[return-value]


def _cached_json(url: str, params: Optional[dict] = None) -> Optional[Any]:
    key = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    cp = _cache_path(key)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        resp = _request(url, params)
        if resp.status_code != 200:
            if resp.status_code in {429, 500, 502, 503, 504}:
                _note_source_failure()
            return None
        data = resp.json()
        cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        time.sleep(config.API_SLEEP)
        return data
    except Exception:
        _note_source_failure()
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
        resp = _request(url, params)
        if resp.status_code != 200:
            if resp.status_code in {429, 500, 502, 503, 504}:
                _note_source_failure()
            return None
        text = resp.text
        cp.write_text(text, encoding="utf-8")
        time.sleep(config.API_SLEEP)
        return text
    except Exception:
        _note_source_failure()
        return None


# ---------------------------------------------------------------------------
# Web citation (EB) link checking
# ---------------------------------------------------------------------------

_URL_CHECK_CACHE_VERSION = "v1"
_URL_CHECK_MAX_BYTES = 300_000
_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_TAG_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _url_host_is_public(url: str) -> tuple[bool, str]:
    """Refuse non-http(s) URLs and hosts that resolve to private addresses.

    Reference lists come from untrusted documents (and from an LLM judge), so the
    link checker must not become an SSRF gadget against localhost / intranet.
    """
    try:
        parsed = urlparse(url or "")
    except Exception:
        return False, "URL 无法解析"
    if parsed.scheme not in {"http", "https"}:
        return False, "仅支持 http/https 链接"
    host = (parsed.hostname or "").strip(".")
    if not host:
        return False, "链接缺少主机名"
    if parsed.port not in (None, 80, 443):
        return False, "非标准端口，已跳过"
    lower = host.lower()
    if lower in {"localhost", "127.0.0.1", "::1"} or lower.endswith((".local", ".internal", ".localhost")):
        return False, "内网地址，已跳过"
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False, "域名无法解析"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not ip.is_global:
            return False, "内网地址，已跳过"
    return True, ""


def _decode_html(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _page_title(html: str) -> str:
    """Extract a human-readable page title (``<title>`` then ``<h1>``)."""
    for pattern in (_TITLE_TAG_RE, _H1_TAG_RE):
        match = pattern.search(html or "")
        if not match:
            continue
        text = html_lib.unescape(_TAG_RE.sub(" ", match.group(1)))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            return text[:300]
    return ""


def check_web_url(url: str) -> dict:
    """Check whether a cited URL is reachable and read its page title.

    Returns a small JSON-serialisable dict; never raises. ``state`` is one of
    ``live`` / ``dead`` / ``error`` / ``blocked`` / ``off``. Only stable outcomes
    are cached — a transient network error is retried on the next run.
    """
    if not config.URL_CHECK_ENABLED:
        return {"state": "off", "reason": "链接检查已关闭"}
    key = f"URL_CHECK::{_URL_CHECK_CACHE_VERSION}::{url}"
    cached = _cache_path(key)
    if cached.exists():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            pass
    public, reason = _url_host_is_public(url)
    if not public:
        result = {"state": "blocked", "reason": reason}
        try:
            cached.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return result
    try:
        response = requests.get(
            url,
            timeout=min(config.HTTP_TIMEOUT, config.URL_CHECK_TIMEOUT),
            headers={"User-Agent": config.USER_AGENT},
            allow_redirects=True,
            stream=True,
        )
        content = b""
        for chunk in response.iter_content(64 * 1024):
            content += chunk
            if len(content) >= _URL_CHECK_MAX_BYTES:
                break
        content_type = (response.headers.get("Content-Type") or "").lower()
        title = _page_title(_decode_html(content)) if "html" in content_type or not content_type else ""
        result = {
            "state": "live" if (response.status_code or 0) < 400 else "dead",
            "status": response.status_code,
            "final_url": response.url,
            "title": title,
        }
    except Exception as exc:  # noqa: BLE001 - a dead link must not crash a report
        return {"state": "error", "reason": type(exc).__name__}
    try:
        cached.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return result


def _web_title_sim(ref_title: str, page_title: str) -> float:
    """Similarity between a cited title and an HTML ``<title>``.

    Page titles usually add a site name ("Bio-X: About Bio-X | Stanford"), so a
    containment match counts as high similarity instead of being diluted by the
    suffix.
    """
    sim = title_sim(ref_title, page_title)
    nr, np = norm_title(ref_title), norm_title(page_title)
    if nr and np and len(nr) >= 6 and (nr in np or np in nr):
        overlap = min(len(nr), len(np)) / max(len(nr), len(np))
        sim = max(sim, 0.75 + 0.25 * overlap)
    return min(1.0, sim)


def _verify_web_url(ref: Reference) -> Optional[VerifyResult]:
    """Verify an``[EB/OL]`` citation against its URL (or say why we could not)."""
    info = check_web_url(ref.url)
    state = info.get("state")
    if state in {"off", "blocked"}:
        return None  # no opinion: fall back to the usual title search
    if state == "error":
        return None  # transient: let the title search / manual links handle it
    status = info.get("status")
    if state == "dead":
        if status in {401, 403}:
            return VerifyResult(
                status="Unverified",
                doi_status="none",
                notes=[f"网页链接需要登录或拒绝访问（HTTP {status}），无法自动核验，请人工打开核对"],
                sources=["url:blocked"],
            )
        return VerifyResult(
            status="Unverified",
            doi_status="none",
            notes=[
                f"网页链接返回 HTTP {status}（可能链接腐化或已迁移），"
                "请核对最新地址或存档；链接失效不等同于伪造"
            ],
            sources=["url:dead"],
        )
    page_title = info.get("title") or ""
    sim = _web_title_sim(ref.title, page_title) if (page_title and ref.title) else 0.0
    if sim >= 0.8:
        return VerifyResult(
            status="Exact",
            doi_status="none",
            title_sim=round(sim, 4),
            notes=[f"网页链接可访问（HTTP {status}），页面标题与引文题名一致（相似度 {sim:.2f}）"],
            sources=["url:live"],
        )
    if page_title:
        return VerifyResult(
            status="Unverified",
            doi_status="none",
            title_sim=round(sim, 4),
            notes=[
                f"网页链接可访问（HTTP {status}），但页面标题「{page_title[:60]}」与引文题名不一致，"
                "请核对是否同一页面"
            ],
            sources=["url:mismatch"],
        )
    return VerifyResult(
        status="Unverified",
        doi_status="none",
        notes=[f"网页链接可访问（HTTP {status}），但返回内容不是可读网页（PDF/附件），请人工打开核对"],
        sources=["url:live"],
    )


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
            "select": "id,doi,title,publication_year,authorships,primary_location,biblio,type,language,abstract_inverted_index,is_retracted",
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
                    retracted=bool(w.get("is_retracted")),
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


_ARXIV_ID_RE = re.compile(
    r"(?:arxiv(?:\.org/(?:abs|pdf)/)?[:\s/]*|10\.48550/arxiv\.)(?P<id>\d{4}\.\d{4,5})(?:v\d+)?",
    re.I,
)


def _arxiv_id_of(ref: "Reference") -> str:
    """Pull an arXiv identifier out of DOI/URL/raw text, if present."""
    hay = " ".join(
        part
        for part in (ref.doi or "", ref.url or "", ref.raw or "", ref.title or "")
        if part
    )
    m = _ARXIV_ID_RE.search(hay)
    return m.group("id") if m else ""


def _arxiv_by_id(arxiv_id: str) -> list[Candidate]:
    """Resolve a reference through its arXiv id (a second anchor besides DOI)."""
    if not arxiv_id:
        return []
    text = _cached_text(
        "http://export.arxiv.org/api/query", {"id_list": arxiv_id, "max_results": 1}
    )
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except Exception:
        return []
    out: list[Candidate] = []
    for e in root.findall("a:entry", _ATOM):
        title_el = e.find("a:title", _ATOM)
        id_el = e.find("a:id", _ATOM)
        published = e.find("a:published", _ATOM)
        doi_el = e.find("a:doi", _ATOM)
        journal_el = e.find("a:journal_ref", _ATOM)
        authors = [
            (a.find("a:name", _ATOM).text or "")
            for a in e.findall("a:author", _ATOM)
            if a.find("a:name", _ATOM) is not None
        ]
        year = None
        if published is not None and published.text:
            try:
                year = int(published.text[:4])
            except ValueError:
                year = None
        out.append(
            Candidate(
                source="arxiv:id",
                title=(title_el.text or "").strip() if title_el is not None else "",
                doi=(doi_el.text or "").strip() if doi_el is not None else "",
                year=year,
                authors=[a for a in authors if a],
                venue=(journal_el.text or "").strip() if journal_el is not None else "",
                url=(id_el.text or "").strip() if id_el is not None else "",
            )
        )
    return out


_S2_LOCK = threading.Lock()
_S2_LAST_CALL = [0.0]
_S2_DOWN_UNTIL = [0.0]
_S2_FIELDS = "title,year,venue,authors,externalIds,abstract"


def search_semantic_scholar(title: str, limit: int = 3) -> list[Candidate]:
    """Semantic Scholar as a CS-heavy fallback when OpenAlex/Crossref miss.

    Unauthenticated access is shared and rate-limited; a single 429 puts the
    source to sleep for two minutes so one batch does not stall.
    """
    if os.environ.get("CITEGUARD_S2", "0").lower() in {"0", "false", "off", "no", ""}:
        return []
    if not title or len(norm_title(title)) < 3 or _CJK_RE.search(title):
        return []
    if time.time() < _S2_DOWN_UNTIL[0]:
        return []
    params = {"query": title, "limit": limit, "fields": _S2_FIELDS}
    with _S2_LOCK:
        wait = 1.1 - (time.time() - _S2_LAST_CALL[0])
        if wait > 0:
            time.sleep(wait)
        _S2_LAST_CALL[0] = time.time()
    try:
        resp = _request(
            "https://api.semanticscholar.org/graph/v1/paper/search", params, tries=2
        )
    except Exception:
        _S2_DOWN_UNTIL[0] = time.time() + 60
        return []
    if resp.status_code == 429:
        _S2_DOWN_UNTIL[0] = time.time() + 120
        _note_source_failure()
        return []
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    out: list[Candidate] = []
    for item in data.get("data") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        ext = item.get("externalIds") or {}
        authors = [
            a.get("name") or ""
            for a in item.get("authors") or []
            if isinstance(a, dict) and a.get("name")
        ]
        paper_id = item.get("paperId") or ""
        out.append(
            Candidate(
                source="semanticscholar",
                title=str(item.get("title") or "").strip(),
                doi=str(ext.get("DOI") or "").strip(),
                year=item.get("year") if isinstance(item.get("year"), int) else None,
                authors=authors,
                venue=str(item.get("venue") or "").strip(),
                abstract=_clean_abstract(str(item.get("abstract") or "")),
                url=f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else "",
            )
        )
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
                retracted=bool(data2.get("is_retracted")),
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
    # v3: DOI landing metadata (China DOI / DataCite) is cached together with
    # the status, so a cached "resolved_landing" does not lose its candidate.
    cp = _cache_path("DOI_STATUS::v3::" + doi)
    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            st = data.get("status", "not_found")
            saved = data.get("candidates") or []
            if st == "resolved_landing" and saved:
                return [Candidate(**c) for c in saved], st
            return [], st
        except Exception:
            pass
    status = "error"
    try:
        resp = _request(f"https://api.crossref.org/works/{doi}")
        if resp.status_code == 404:
            status = "not_found"
        elif resp.status_code == 200:
            status = "resolved"
        else:
            status = "error"
    except Exception:
        status = "error"
    if status == "not_found":
        # DOI 404 at Crossref only means "not registered with Crossref". DOIs are
        # also issued by other registration agencies (DataCite, CNKI, JaLC, ...),
        # so ask the global handle system before calling a DOI fabricated.
        handle = _doi_handle_status(doi)
        if handle == "exists":
            status = "exists_elsewhere"
            # Some registrars (CNKI / DataCite) expose metadata even though
            # Crossref does not: use it instead of giving up.
            landing = _doi_landing_candidate(doi)
            if landing is not None:
                try:
                    cp.write_text(
                        json.dumps(
                            {
                                "status": "resolved_landing",
                                "candidates": [_candidate_to_dict(landing)],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                return [landing], "resolved_landing"
        elif handle == "error":
            status = "error"
    if status != "error":
        # Transient failures must not be cached: a rate-limited lookup would
        # otherwise stay "error" forever and hide the real verdict.
        try:
            cp.write_text(json.dumps({"status": status}), encoding="utf-8")
        except Exception:
            pass
    time.sleep(config.API_SLEEP)
    return [], status


def _doi_handle_status(doi: str) -> str:
    """Check whether a DOI exists in any registration agency: exists/missing/error."""
    key = _cache_path("DOI_HANDLE::" + doi)
    if key.exists():
        try:
            return json.loads(key.read_text(encoding="utf-8")).get("status", "error")
        except Exception:
            pass
    status = "error"
    try:
        resp = _request(f"https://doi.org/api/handles/{doi}")
        if resp.status_code == 200:
            status = "exists"
        elif resp.status_code == 404:
            status = "missing"
    except Exception:
        status = "error"
    if status != "error":
        try:
            key.write_text(json.dumps({"status": status}), encoding="utf-8")
        except Exception:
            pass
    time.sleep(config.API_SLEEP)
    return status


def _candidate_to_dict(cand: "Candidate") -> dict:
    return {
        "title": cand.title,
        "doi": cand.doi,
        "year": cand.year,
        "authors": cand.authors,
        "venue": cand.venue,
        "volume": cand.volume,
        "issue": cand.issue,
        "pages": cand.pages,
        "abstract": cand.abstract,
        "url": cand.url,
        "source": cand.source,
    }


def _landing_hint(html: str) -> bool:
    return ("题名" in html and ("作者" in html or "DOI码" in html)) or "多重解析" in html


def _parse_doi_landing(html: str, doi: str) -> Optional[Candidate]:
    """Parse a China-DOI 'multiple resolution' page (metadata in table labels)."""
    if not html or not _landing_hint(html):
        return None

    def grab(label: str) -> str:
        m = re.search(rf"{label}\s*[:：]\s*</label>\s*([^<]*)", html)
        return (m.group(1) or "").strip() if m else ""

    title = grab("题名")
    if not title:
        return None
    authors = [a.strip() for a in re.split(r"[;；]", grab("作者")) if a.strip()]
    venue = grab("来源")
    year = None
    ym = re.search(r"((?:19|20)\d{2})", grab("出版年"))
    if ym:
        year = int(ym.group(1))
    return Candidate(
        source="doi:landing",
        title=title,
        doi=doi,
        authors=authors,
        venue=venue,
        year=year,
    )


def _doi_landing_candidate(doi: str) -> Optional[Candidate]:
    """Fetch DOI landing metadata for DOIs registered outside Crossref (e.g. CNKI)."""
    key = _cache_path("DOI_LANDING::" + doi)
    if key.exists():
        try:
            data = json.loads(key.read_text(encoding="utf-8"))
            if data.get("found") and data.get("title"):
                return Candidate(**{k: v for k, v in data.items() if k != "found"})
            if data.get("found") is False:
                return None
        except Exception:
            pass

    cand: Optional[Candidate] = None
    # 1) DataCite (datasets / some journals / repositories)
    try:
        data = _cached_json(f"https://api.datacite.org/dois/{doi}")
        attr = ((data or {}).get("data") or {}).get("attributes") or {}
        titles = attr.get("titles") or []
        title = (titles[0].get("title") if titles else "") or ""
        if title:
            authors: list[str] = []
            for creator in attr.get("creators") or []:
                name = " ".join(
                    x for x in (creator.get("givenName", ""), creator.get("familyName", "")) if x
                ).strip()
                authors.append(name or (creator.get("name") or ""))
            container = (attr.get("container") or {}).get("title") or ""
            cand = Candidate(
                source="doi:datacite",
                title=title,
                doi=doi,
                authors=[a for a in authors if a],
                venue=container,
                year=attr.get("publicationYear"),
                url=attr.get("url", ""),
            )
    except Exception:
        pass

    # 2) doi.org landing page metadata (China DOI 'multiple resolution' page)
    if cand is None:
        try:
            resp = _request(f"https://doi.org/{doi}")
            if resp.status_code == 200:
                cand = _parse_doi_landing(resp.text or "", doi)
        except Exception:
            cand = None

    try:
        payload = _candidate_to_dict(cand) if cand else {"found": False}
        if cand is not None:
            payload["found"] = True
        key.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return cand


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


def _title_candidates(
    ref: Reference, use_arxiv: bool = True, sources: Optional[list[str]] = None
) -> list[Candidate]:
    """Search OpenAlex/Crossref (then arXiv) by title."""
    candidates: list[Candidate] = []
    if not ref.title or len(norm_title(ref.title)) < 3:
        return candidates
    ax_id = _arxiv_id_of(ref)
    if ax_id:
        ax = _arxiv_by_id(ax_id)
        if ax:
            candidates.extend(ax)
            if sources is not None:
                sources.append("arxiv:id")
    oa = search_openalex(ref.title)
    if oa:
        candidates.extend(oa)
        if sources is not None:
            sources.append("openalex")
    cr = search_crossref(ref.title)
    if cr:
        candidates.extend(cr)
        if sources is not None:
            sources.append("crossref")
    if use_arxiv and not oa and not cr:
        ax = search_arxiv(ref.title)
        if ax:
            candidates.extend(ax)
            if sources is not None:
                sources.append("arxiv")
    # Semantic Scholar: CS proceedings metadata is far better than Crossref
    # for acronym-only references. Only spend a rate-limited call when the
    # free sources produced nothing close.
    if not _CJK_RE.search(ref.title or ""):
        best_so_far = max(
            (title_sim(ref.title, c.title) for c in candidates if c.title), default=0.0
        )
        if best_so_far < 0.92:
            s2 = search_semantic_scholar(ref.title)
            if s2:
                candidates.extend(s2)
                if sources is not None:
                    sources.append("semanticscholar")
    # 中文题录兜底：OpenAlex/Crossref 对中文期刊覆盖很低，配置万方 App Key 后补一层。
    # 免费额度每天 100 次，失败（未订阅/限流/额度用尽）只记日志，不把条目误标成 Unknown。
    if _CJK_RE.search(ref.title or ""):
        try:
            from . import wanfang
        except ImportError:  # pragma: no cover - 可选依赖
            wanfang = None  # type: ignore[assignment]
        if wanfang is not None and wanfang.available():
            try:
                records = wanfang.search(f"Title:{ref.title}", rows=3)
            except wanfang.WanfangError as exc:
                _LOGGER.warning("wanfang lookup skipped: %s", exc)
                records = []
            found = 0
            for record in records:
                fields = wanfang.record_to_candidate_fields(record)
                if not fields.get("title"):
                    continue
                authors = [
                    part.strip()
                    for part in str(fields.get("authors") or "").replace("，", ";").split(";")
                    if part.strip()
                ]
                candidates.append(
                    Candidate(
                        source="wanfang",
                        title=fields["title"],
                        doi=fields.get("doi") or "",
                        year=fields.get("year"),
                        authors=authors,
                        venue=fields.get("venue") or "",
                        volume=fields.get("volume") or "",
                        issue=fields.get("issue") or "",
                        pages=fields.get("pages") or "",
                        abstract=fields.get("abstract") or "",
                        url=fields.get("url") or "",
                    )
                )
                found += 1
            if found and sources is not None:
                sources.append("wanfang")
    return candidates


def _best_scored(
    ref: Reference, candidates: list[Candidate]
) -> Optional[tuple[float, bool, float, Candidate]]:
    """Return (title_sim, year_match, author_overlap, candidate) for the best match."""
    scored: list[tuple[float, bool, float, Candidate]] = []
    for c in candidates:
        if not c.title:
            continue
        ts = title_sim(ref.title, c.title)
        ym = _year_match(ref.year, c.year)
        am = _author_overlap(ref.authors, c.authors)
        scored.append((ts, ym, am, c))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    ts, ym, am, best = scored[0]
    for ts2, ym2, am2, c in scored:
        if c.abstract and ts2 >= max(0.85, ts - 0.03):
            return ts2, ym2, am2, c
    return ts, ym, am, best


def local_library_verdict(
    ref: Reference, library: Optional["Library"] = None  # noqa: F821 - lazy type
) -> Optional[VerifyResult]:
    """Verify against the user's own reference library only (no network).

    Returns ``None`` when the library has no usable record for this reference;
    callers then fall back to the online sources.
    """
    if library is None or not ref.title:
        return None
    local_hits = library.search(ref.title, ref.year)
    if not local_hits:
        return None
    sim, entry = local_hits[0]
    from .local_library import entry_to_candidate

    cand = entry_to_candidate(entry)
    if sim >= 0.90:
        mism = _field_mismatches(ref, cand)
        if sim < 0.95:
            # The library holds the exact record; a near-but-not-equal title
            # means the citation's title was altered.
            mism.append("title_partial")
        status = "Minor" if mism else "Exact"
        note = f"本地题录库命中（题名相似度 {sim:.2f}）" + (
            f"；字段差异：{','.join(mism)}" if mism else "；字段一致"
        )
        return VerifyResult(
            status=status,
            best=cand,
            title_sim=round(sim, 4),
            year_match=_year_match(ref.year, cand.year),
            author_match=round(_author_overlap(ref.authors, cand.authors), 4),
            doi_status="local",
            mismatches=mism,
            notes=[note],
            sources=["local"],
        )
    if sim >= 0.78:
        return VerifyResult(
            status="Minor",
            best=cand,
            title_sim=round(sim, 4),
            year_match=_year_match(ref.year, cand.year),
            author_match=round(_author_overlap(ref.authors, cand.authors), 4),
            doi_status="local",
            mismatches=["title"],
            notes=[f"本地题录库近似命中（题名相似度 {sim:.2f}）"],
            sources=["local"],
        )
    return None


def _verify_reference(
    ref: Reference,
    use_arxiv: bool = True,
    library: Optional["Library"] = None,  # noqa: F821 - imported lazily to avoid a cycle
) -> VerifyResult:
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

    # 0) User-supplied local library first: it is the user's own licensed
    # metadata, so it can verify Chinese references that open indexes miss.
    local = local_library_verdict(ref, library)
    if local is not None:
        return local

    # 0b) A "title" that is actually a URL/DOI means the PDF/OCR text was split
    # badly (some PDFs print references as bare links). Treat it as a parse
    # artifact instead of accusing the paper of a fabricated citation.
    if re.match(r"^(?:https?://|www\.|10\.\d{4,9}/)", (ref.title or "").strip(), re.I):
        return VerifyResult(
            status="Unverified",
            doi_status="none",
            notes=["题名解析为链接/DOI，疑似 PDF/OCR 噪声，请人工核对原始条目"],
            sources=["parser:noise-guard"],
        )

    # 0c) An empty title cannot be verified. It is a parsing artifact (page
    # furniture, a bare link line), never evidence that the citation is fake.
    if not (ref.title or "").strip():
        return VerifyResult(
            status="Unverified",
            doi_status="none",
            notes=["题名解析为空（疑似 PDF/OCR 噪声），请人工核对原始条目"],
            sources=["parser:noise-guard"],
        )

    # 0d) Web citations (`[EB/OL]`) cite a URL instead of a journal record.
    # Checking the link is direct evidence: a reachable page whose title matches
    # the cited title confirms it even when academic indexes do not cover it.
    # Link rot / login walls are reported for manual review, never as 虚构.
    if (ref.doc_type or "").upper() == "EB" and ref.url and not ref.doi:
        web_result = _verify_web_url(ref)
        if web_result is not None:
            return web_result

    # 1) DOI anchor.
    if ref.doi:
        doi_variants = [ref.doi]
        if ref.doi.endswith("_c"):
            doi_variants.append(ref.doi[:-2])
        if ref.doi.lower() != ref.doi:
            doi_variants.append(ref.doi.lower())

        doi_status = "not_found"
        doi_cands: list[Candidate] = []
        exists_elsewhere = False
        doi_source_note = "Crossref"
        for d in dict.fromkeys(doi_variants):
            cands, status = lookup_doi_status(d)
            if status == "resolved":
                doi_cands = cands
                doi_status = "resolved"
                notes.append(f"DOI {d} resolved")
                break
            if status == "resolved_landing":
                doi_cands = cands
                doi_status = "resolved_landing"
                doi_source_note = "中国 DOI 平台" if cands and cands[0].source == "doi:landing" else "DataCite"
                notes.append(f"DOI {d} resolved via {doi_source_note}")
                break
            if status == "exists_elsewhere":
                exists_elsewhere = True
                doi_status = "exists_elsewhere"
                notes.append(f"DOI {d} exists but is not registered with Crossref")
                continue
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
                notes=notes + ["DOI 不存在（Crossref 404，DOI 系统也无记录）"],
                sources=["crossref:doi:miss", "doi.org:handle:miss"],
            )
        if exists_elsewhere and not doi_cands:
            # Registered with another agency (CNKI, DataCite, ...): the DOI is
            # real, but there is no Crossref metadata to compare against.
            return VerifyResult(
                status="Unverified",
                doi_status="exists_elsewhere",
                notes=notes + ["DOI 由其他注册机构签发，无 Crossref 元数据可比对"],
                sources=["doi.org:handle"],
            )

        if not doi_cands:
            # DOI resolved but the metadata endpoints returned nothing parsable:
            # do not guess, degrade to Unknown instead of crashing downstream.
            return VerifyResult(
                status="Unknown",
                doi_status="resolved",
                notes=notes + ["DOI resolved but no metadata returned"],
                sources=["crossref:doi", "openalex:doi"],
            )

        best = _pick_best(ref, doi_cands)
        ts = title_sim(ref.title, best.title)
        ym = _year_match(ref.year, best.year)
        am = _author_overlap(ref.authors, best.authors)
        mism = _field_mismatches(ref, best)

        doi_sources = ["crossref:doi", "openalex:doi"]
        if doi_status == "resolved_landing":
            doi_sources = ["doi:datacite"] if best.source == "doi:datacite" else ["doi:landing"]
            notes.append(
                f"外部注册机构元数据有限（{doi_source_note}）：只比对题名/作者/年份，卷期页可能缺"
            )

        if ts < 0.50:
            if _is_cjk(ref.title) != _is_cjk(best.title):
                # Chinese citation vs English-only source record: language variant,
                # not a fabrication; keep it as Minor.
                mism.append("title_language")
            else:
                # The DOI may simply be wrong (copy/paste error) while the cited
                # paper is real: search by title before accusing the reference.
                rescue_cands = _title_candidates(ref, use_arxiv)
                rescue = _best_scored(ref, rescue_cands)
                if rescue is not None and rescue[0] >= 0.78:
                    r_ts, r_ym, r_am, r_best = rescue
                    return VerifyResult(
                        status="Minor" if r_ts < 0.90 else "Minor",
                        best=r_best,
                        title_sim=round(r_ts, 4),
                        year_match=r_ym,
                        author_match=round(r_am, 4),
                        doi_status="resolved",
                        mismatches=["doi"],
                        notes=notes
                        + [
                            f"DOI 指向另一篇文献，但题名检索命中（相似度 {r_ts:.2f}）：更可能是 DOI 抄错"
                        ],
                        sources=sources + ["openalex:title", "crossref:title"],
                    )
                return VerifyResult(
                    status="Major",
                    best=best,
                    title_sim=round(ts, 4),
                    year_match=ym,
                    author_match=round(am, 4),
                    doi_status=doi_status,
                    mismatches=["title"],
                    notes=notes + ["DOI resolved but title mismatch (title/DOI 错配)"],
                    sources=doi_sources,
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
            doi_status=doi_status,
            mismatches=mism,
            notes=notes,
            sources=doi_sources,
        )

    # 2) No DOI: title search.
    errors_before = source_error_count()
    candidates = _title_candidates(ref, use_arxiv, sources)
    best_scored = _best_scored(ref, candidates)
    if best_scored is None:
        if source_error_count() > errors_before:
            # Distinguish "not indexed" from "the index did not answer".
            return VerifyResult(
                status="Unknown",
                doi_status="none",
                notes=notes + ["数据源请求失败（限流/网络），本条无法核验"],
                sources=sources,
            )
        return VerifyResult(
            status="Unverified",
            doi_status="none",
            notes=notes + ["title search returned no usable candidate"],
            sources=sources,
        )
    ts, ym, am, best = best_scored

    if ts >= 0.90:
        mism = _field_mismatches(ref, best)
        status = "Minor" if mism else "Exact"
        notes.append("title matched" + (f"; mismatch: {','.join(mism)}" if mism else "; fields matched"))
        if "authors" in mism and ts >= 0.98 and am == 0.0:
            # Same title but a completely different author list: the record is
            # often a book review / "review of" article, not the work itself.
            notes.append(
                "题名一致但作者完全不同：匹配记录可能是书评/同名不同作品"
                "（也可能是引文作者有误），请核对作者"
            )
    elif ts >= 0.78:
        status = "Minor"
        mism = ["title"]
        notes.append(f"partial title match ({ts:.2f})")
    else:
        # A weak best match is *not* evidence of a fabricated citation: most
        # Chinese journal articles are simply not indexed. Report "unverified"
        # so the user checks by hand instead of seeing a false accusation.
        status = "Unverified"
        mism = []
        notes.append(
            f"no close title match in OpenAlex/Crossref/arXiv (best {ts:.2f}); "
            "the article may be unindexed or the reference may be wrong — check manually"
        )
        if _CJK_RE.search(ref.title or ""):
            notes.append(
                "中文文献：OpenAlex/Crossref 对中文期刊收录有限，工具无法自动核验；"
                "报告已附知网/百度学术检索链接，请人工核对"
            )

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


def verify_reference(
    ref: Reference,
    use_arxiv: bool = True,
    library: Optional["Library"] = None,  # noqa: F821 - imported lazily to avoid a cycle
) -> VerifyResult:
    """Verify one reference and annotate retraction status when known."""
    return _apply_retraction(_verify_reference(ref, use_arxiv=use_arxiv, library=library))


def verify_many(
    refs: list[Reference],
    progress: bool = True,
    use_arxiv: bool = True,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    workers: Optional[int] = None,
    library: Optional["Library"] = None,  # noqa: F821 - lazy import in verify_reference
) -> list[VerifyResult]:
    """Verify references concurrently, preserving input order.

    Network latency dominates, so a small thread pool gives a multi-fold speedup
    on long reference lists. The default is conservative (4) to stay inside the
    polite-pool guidance of OpenAlex/Crossref; override with
    ``CITEGUARD_VERIFY_WORKERS``.

    Identical references (same normalized title + year + DOI) are only looked up
    once; theses commonly cite the same paper several times.
    """
    total = len(refs)
    if total == 0:
        return []

    # Deduplicate the work while keeping the original order for results.
    unique_refs: list[Reference] = []
    slots: list[int] = []
    key_to_slot: dict[tuple, int] = {}
    for ref in refs:
        key = (norm_title(ref.title), ref.year or 0, (ref.doi or "").lower())
        slot = key_to_slot.get(key)
        if slot is None:
            slot = len(unique_refs)
            key_to_slot[key] = slot
            unique_refs.append(ref)
        slots.append(slot)

    if workers is None:
        workers = max(1, min(config.VERIFY_WORKERS, len(unique_refs)))
    unique_results: list[Optional[VerifyResult]] = [None] * len(unique_refs)
    lock = threading.Lock()
    done = 0

    def one(slot: int, ref: Reference) -> None:
        nonlocal done
        try:
            result = verify_reference(ref, use_arxiv=use_arxiv, library=library)
        except Exception:  # noqa: BLE001 - never let one bad entry kill the run
            result = VerifyResult(status="Unknown", notes=["verification crashed"])
        with lock:
            unique_results[slot] = result
            done += 1
            current = done
        if progress_cb is not None:
            try:
                progress_cb(min(current, total), total)
            except Exception:
                pass
        if progress and (current % 10 == 0 or current == len(unique_refs)):
            print(f"  verified {current}/{len(unique_refs)} unique", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda pair: one(*pair), enumerate(unique_refs)))
    resolved: list[VerifyResult] = [
        r if r is not None else VerifyResult(status="Unknown") for r in unique_results
    ]
    return [resolved[slot] for slot in slots]
