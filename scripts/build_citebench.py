"""Build CiteBench-CN: 250 Chinese references rendered from OpenAlex records (CC0).

Label definitions follow the v1 verifier wording (labels are fixed by construction):

* ``Exact`` (100): GB/T 7714-style reference rendered from a real OpenAlex work;
  title, year, authors, source, volume/issue/pages and DOI all match the record.
* ``Minor`` (75): the paper really exists, but exactly one field drifts:
    - year                              (15)
    - author order                      (15)
    - source / journal name             (15)
    - volume / issue                    (15)
    - pages                             (15)
  (DOI letter-case changes are NOT used: DOIs are case-insensitive, so a case
  change is semantically Exact and must not be labelled Minor.  A DOI that is
  changed so much that it 404s is a Major sample, not a Minor one.)
* ``Major`` (75): the title cannot be found in open databases, or the DOI is a
  clearly unrelated DOI that resolves to nothing (404):
    - fabricated (non-existent) title   (38)
    - DOI that points to no record      (37; prefix 10.9999 has no DOI service)

30% of the 250 references (75) carry **no DOI field at all** (title+authors+
year+source only), so that the ``- title search`` ablation has a real control:
30 Exact, 22 Minor, 23 Major.

The raw OpenAlex payload is cached at ``data/citebench_cn/openalex_zh_works.json``
and DOI existence checks at ``data/citebench_cn/doi_handle_checks.json``, so the
build is repeatable offline with a fixed ``--seed``. Every rendered reference is
re-parsed with ``citeguard.reference_parser.parse_reference`` and checked against
the fields that were rendered; a mismatch triggers a base-record retry.

Usage:
    PYTHONPATH=src python3 scripts/build_citebench.py [--seed 20261022] [--refresh]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.reference_parser import parse_reference  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):  # Windows consoles are often GBK.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_DIR = ROOT / "data" / "citebench_cn"
DATA_DIR.mkdir(parents=True, exist_ok=True)

JSONL_PATH = DATA_DIR / "citebench_cn.jsonl"
META_PATH = DATA_DIR / "citebench_cn.meta.json"
POOL_CACHE = DATA_DIR / "openalex_zh_works.json"
DOI_CHECK_CACHE = DATA_DIR / "doi_handle_checks.json"
LEGACY_FAKE_DOI_CACHE = DATA_DIR / "fabricated_doi_checks.json"

OPENALEX_URL = "https://api.openalex.org/works"
OPENALEX_FILTER = "language:zh,has_doi:true"
OPENALEX_SELECT = (
    "id,doi,title,publication_year,authorships,primary_location,biblio,type,language"
)
MAILTO = os.environ.get("CITEGUARD_MAILTO", "citeguard@example.org")
USER_AGENT = os.environ.get(
    "CITEGUARD_USER_AGENT",
    "CiteGuard-CN/0.1 (CiteBench-CN builder; research prototype)",
)

N_EXACT = 100
N_MINOR = 75
N_MAJOR = 75
N_TOTAL = N_EXACT + N_MINOR + N_MAJOR

POOL_TARGET = 340  # eligible base records to fetch (250 needed + buffer)
MAX_PAGES = 16
PER_PAGE = 200

# Exactly 75 references (30%) have no DOI field at all.
NO_DOI_EXACT = 30
# (kind, total, how many of them without DOI) -- Minor totals 75, no-DOI part 22.
MINOR_PLAN = (
    ("year", 15, 5),
    ("author_order", 15, 5),
    ("venue", 15, 4),
    ("volume_issue", 15, 4),
    ("pages", 15, 4),
)
# (kind, total, how many of them without DOI) -- Major totals 75, no-DOI part 23.
MAJOR_PLAN = (
    ("fake_title", 38, 23),
    ("fake_doi", 37, 0),
)
FAKE_VENUE_COUNT = sum(count for kind, count, _ in MINOR_PLAN if kind == "venue")

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CJK_START_RE = re.compile(r"^[\u4e00-\u9fff]")
DIGIT_RE = re.compile(r"\d")

# Venue aggregators are indexes, not journals: useless as a "来源" in a reference.
VENUE_BLACKLIST = (
    "doaj", "pubmed", "semantic scholar", "crossref", "researchgate",
    "openalex", "directory of open access", "web of science", "scopus",
    "cnki", "wanfang",
)

# ---------------------------------------------------------------------------
# Fabrication vocabularies (deterministic given the seed)
# ---------------------------------------------------------------------------

FAKE_TITLE_TOPICS = [
    "数字经济", "乡村振兴", "碳中和", "老年健康", "教育公平", "产业链韧性",
    "城市更新", "人工智能治理", "公共卫生应急", "绿色金融", "文化记忆",
    "基层治理", "能源转型", "数字孪生", "知识图谱", "海洋生态", "耕地保护",
    "区域协同", "平台经济", "老龄化社会",
]
FAKE_TITLE_METHODS = [
    "研究进展", "实证研究", "机制与路径", "评价指标体系", "时空演化特征",
    "影响因素分析", "政策工具比较", "案例考察", "测度与检验", "协同治理框架",
    "风险识别方法", "绩效评估模型",
]
FAKE_TITLE_SCOPES = [
    "", "——基于省级面板数据的", "——以长三角为例", "：一个分析框架",
    "的再审视", "的跨区域比较", "：理论建构与经验证据",
]
FAKE_TITLE_QUALIFIERS = ["新型", "多层次", "全链条", "数字化", "协同式", "动态"]

FAKE_VENUE_HEADS = ["中国", "现代", "当代", "国际", "亚太", "华东", "西部", "南方", "北方", "新型"]
FAKE_VENUE_FIELDS = [
    "区域经济", "数字治理", "绿色能源", "教育科学", "公共卫生", "材料工程",
    "信息管理", "农业生态", "文化传播", "计量经济", "城市发展", "海洋科学",
]
FAKE_VENUE_TAILS = ["研究", "学报", "评论", "前沿", "论坛", "学刊"]

FAKE_DOI_PREFIX = "10.9999"  # no DOI service is registered for this prefix (checked at build)


# ---------------------------------------------------------------------------
# OpenAlex pool
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_work(raw: dict) -> dict:
    source = ((raw.get("primary_location") or {}).get("source") or {}) or {}
    biblio = raw.get("biblio") or {}
    authors: list[str] = []
    for authorship in raw.get("authorships") or []:
        name = ((authorship.get("author") or {}).get("display_name") or "").strip()
        name = unicodedata.normalize("NFKC", name).strip()
        if name:
            authors.append(name)
    doi = (raw.get("doi") or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    return {
        "id": (raw.get("id") or "").strip(),
        "doi": doi,
        "title": unicodedata.normalize("NFKC", (raw.get("title") or "")).strip(),
        "year": raw.get("publication_year"),
        "authors": authors,
        "venue": unicodedata.normalize("NFKC", source.get("display_name") or "").strip(),
        "volume": str(biblio.get("volume") or "").strip(),
        "issue": str(biblio.get("issue") or "").strip(),
        "first_page": str(biblio.get("first_page") or "").strip(),
        "last_page": str(biblio.get("last_page") or "").strip(),
        "type": (raw.get("type") or "").strip(),
    }


def is_eligible(work: dict) -> bool:
    """A base record must render cleanly into a GB/T 7714 journal-article string."""
    title = work.get("title") or ""
    if not title or len(title) < 6 or len(title) > 80:
        return False
    if not CJK_START_RE.match(title) or not CJK_RE.search(title):
        return False
    if re.search(r"[\[\]\.．。\r\n\t\ufffd]", title):
        return False
    if work.get("type") != "article":
        return False
    doi = work.get("doi") or ""
    if not re.match(r"^10\.\d{4,9}/\S+$", doi):
        return False
    if not re.search(r"[A-Za-z]", doi):  # needed for DOI-case / DOI-suffix drift
        return False
    year = work.get("year")
    if not isinstance(year, int) or not (1950 <= year <= 2026):
        return False
    authors = work.get("authors") or []
    if len(authors) < 2:
        return False
    for name in authors:
        if len(name) > 60 or re.search(r"[,\uFF0C;；。\r\n\t]", name):
            return False
    venue = work.get("venue") or ""
    if not venue or len(venue) > 40 or not CJK_RE.search(venue):
        return False
    if re.search(r"[,\uFF0C;；。\.．\r\n\t]", venue):
        return False
    if DIGIT_RE.search(venue):  # a 4-digit year inside a venue name would be read as the year
        return False
    low = venue.lower()
    if any(key in low for key in VENUE_BLACKLIST):
        return False
    volume, issue = work.get("volume") or "", work.get("issue") or ""
    if not (volume.isdigit() and issue.isdigit()):
        return False
    first_page, last_page = work.get("first_page") or "", work.get("last_page") or ""
    if not (first_page.isdigit() and last_page.isdigit()):
        return False
    if int(last_page) < int(first_page) or int(last_page) - int(first_page) > 200:
        return False
    return True


def eligible_works(works: list[dict]) -> list[dict]:
    """Eligible works, de-duplicated by DOI and normalised title, sorted by OpenAlex id."""
    out: list[dict] = []
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    for work in works:
        if not is_eligible(work):
            continue
        doi_key = (work.get("doi") or "").lower()
        title_key = re.sub(r"[^\w\u4e00-\u9fff]+", "", (work.get("title") or "").lower())
        if not doi_key or not title_key or doi_key in seen_doi or title_key in seen_title:
            continue
        seen_doi.add(doi_key)
        seen_title.add(title_key)
        out.append(work)
    out.sort(key=lambda w: w.get("id") or "")
    return out


def _fetch_page(page: int, per_page: int = PER_PAGE, timeout: float = 60.0) -> Optional[dict]:
    params = {
        "filter": OPENALEX_FILTER,
        "per-page": per_page,
        "page": page,
        "select": OPENALEX_SELECT,
        "mailto": MAILTO,
    }
    last_err = ""
    for attempt in range(3):
        try:
            resp = requests.get(
                OPENALEX_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout
            )
            if resp.status_code == 200:
                return resp.json()
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:  # pragma: no cover - network dependent
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(1.5 * (attempt + 1))
    print(f"  [warn] OpenAlex page {page} failed: {last_err}")
    return None


def _save_pool(works: list[dict], pages_fetched: int) -> None:
    POOL_CACHE.write_text(
        json.dumps(
            {
                "meta": {
                    "provider": "OpenAlex",
                    "license": "CC0 1.0",
                    "api": OPENALEX_URL,
                    "filter": OPENALEX_FILTER,
                    "select": OPENALEX_SELECT,
                    "mailto": MAILTO,
                    "pages_fetched": pages_fetched,
                    "fetched_at": _utc_now(),
                },
                "works": works,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def load_or_fetch_pool(target: int = POOL_TARGET, refresh: bool = False) -> tuple[list[dict], dict]:
    """Load the cached OpenAlex pool, fetching more pages until enough eligible works."""
    cached: dict[str, Any] = {}
    if POOL_CACHE.exists() and not refresh:
        try:
            cached = json.loads(POOL_CACHE.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[warn] could not read {POOL_CACHE.name}: {exc}; refetching")
            cached = {}
    works: list[dict] = list(cached.get("works") or []) if isinstance(cached, dict) else []
    seen_ids = {w.get("id") for w in works if w.get("id")}
    pages_fetched = int((cached.get("meta") or {}).get("pages_fetched") or 0) if works else 0
    page = pages_fetched + 1
    eligible = eligible_works(works)
    print(f"[pool] cached works={len(works)} eligible={len(eligible)} next_page={page}")

    while len(eligible) < target and page <= MAX_PAGES:
        payload = _fetch_page(page)
        if not payload:
            break
        added = 0
        for raw in payload.get("results") or []:
            work = _normalize_work(raw)
            wid = work.get("id")
            if wid and wid not in seen_ids:
                seen_ids.add(wid)
                works.append(work)
                added += 1
        pages_fetched = page
        eligible = eligible_works(works)
        print(f"[pool] page {page}: +{added} works, total={len(works)}, eligible={len(eligible)}")
        _save_pool(works, pages_fetched)
        page += 1
    return works, {"pages_fetched": pages_fetched, "works": len(works), "eligible": len(eligible)}


# ---------------------------------------------------------------------------
# DOI existence checks via the authoritative DOI handle API
# ---------------------------------------------------------------------------

def _load_doi_checks() -> dict:
    if DOI_CHECK_CACHE.exists():
        try:
            return json.loads(DOI_CHECK_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_doi_checks(cache: dict) -> None:
    tmp = DOI_CHECK_CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DOI_CHECK_CACHE)


def check_doi_exists(doi: str) -> Optional[bool]:
    """Return True/False from the DOI handle API; None if it could not be checked."""
    cache = _load_doi_checks()
    if doi in cache and "exists" in cache[doi]:
        return cache[doi]["exists"]
    exists: Optional[bool] = None
    detail = ""
    for attempt in range(2):
        try:
            resp = requests.get(
                f"https://doi.org/api/handles/{doi}", headers={"User-Agent": USER_AGENT}, timeout=25
            )
            if resp.status_code == 404:
                exists = False
                detail = "handle API 404 (responseCode 100)"
                break
            if resp.status_code == 200:
                code = (resp.json() or {}).get("responseCode")
                exists = code == 1
                detail = f"handle API 200 (responseCode {code})"
                break
            detail = f"HTTP {resp.status_code}: {resp.text[:150]}"
        except Exception as exc:  # pragma: no cover - network dependent
            detail = f"{type(exc).__name__}: {exc}"
        time.sleep(1.0)
    if exists is None:
        print(f"[warn] could not check DOI existence for {doi}: {detail}")
        return None
    cache[doi] = {"exists": exists, "detail": detail, "checked_at": _utc_now()}
    _save_doi_checks(cache)
    time.sleep(0.1)
    return exists


def validate_fabricated_dois(rng: random.Random, n: int) -> tuple[list[str], dict]:
    """Generate DOIs that the handle API confirms are 404; regenerate on collision."""
    dois: list[str] = []
    used: set[str] = set()
    attempts = 0
    while len(dois) < n:
        attempts += 1
        if attempts > n * 50:
            raise RuntimeError("could not generate enough non-existent DOIs")
        doi = f"{FAKE_DOI_PREFIX}/cbcn.{rng.randint(2015, 2026)}.{rng.randint(10000, 99999)}"
        if doi.lower() in used:
            continue
        if check_doi_exists(doi) is True:
            print(f"[warn] fabricated DOI unexpectedly resolves, regenerating: {doi}")
            continue
        used.add(doi.lower())
        dois.append(doi)
    verdicts = {doi: check_doi_exists(doi) for doi in dois}
    return dois, {
        "checked": sum(1 for v in verdicts.values() if v is not None),
        "all_missing": all(v is False for v in verdicts.values())
        if all(v is not None for v in verdicts.values())
        else None,
        "verdicts": verdicts,
    }


# ---------------------------------------------------------------------------
# Rendering / construction
# ---------------------------------------------------------------------------

def pages_of(work: dict) -> str:
    first_page, last_page = work.get("first_page") or "", work.get("last_page") or ""
    if not first_page:
        return ""
    return f"{first_page}-{last_page}" if last_page and last_page != first_page else first_page


def author_string(authors: list[str]) -> str:
    """GB/T 7714 style: up to three authors, then ', 等'."""
    shown = authors[:3]
    text = ", ".join(shown)
    if len(authors) > 3:
        text += ", 等"
    return text


def render_reference(
    authors: list[str],
    title: str,
    venue: str,
    year: int,
    volume: str,
    issue: str,
    pages: str,
    doi: str,
) -> str:
    """Render a GB/T 7714-style journal reference string (DOI omitted when empty)."""
    ref = f"{author_string(authors)}. {title}[J]. {venue}, {year}"
    if volume and issue:
        ref += f", {volume}({issue})"
    elif volume:
        ref += f", {volume}"
    if pages:
        ref += f": {pages}"
    ref += "."
    if doi:
        ref += f" DOI: {doi}."
    return ref


def make_fake_title(rng: random.Random) -> str:
    title = (
        f"{rng.choice(FAKE_TITLE_QUALIFIERS)}{rng.choice(FAKE_TITLE_TOPICS)}"
        f"{rng.choice(FAKE_TITLE_METHODS)}{rng.choice(FAKE_TITLE_SCOPES)}"
    )
    return unicodedata.normalize("NFKC", title)


def make_fake_venue(rng: random.Random) -> str:
    return f"{rng.choice(FAKE_VENUE_HEADS)}{rng.choice(FAKE_VENUE_FIELDS)}{rng.choice(FAKE_VENUE_TAILS)}"


def _norm_key(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", (text or "").lower())


def _sim_norm(text: str) -> str:
    """Normalise for similarity: NFKC + lower case, keep CJK / word characters only."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def char_similarity(a: str, b: str) -> float:
    """Deterministic normalised-Levenshtein similarity in [0, 1].

    Deliberately implemented in pure Python instead of rapidfuzz: the fake-title
    filter must give identical results on every environment (local Python 3.12 +
    rapidfuzz 3.14.6 vs server Python 3.10 + 3.14.5), otherwise the same seed can
    produce different datasets and break the "rebuild keeps the SHA-256" claim.
    """
    a, b = _sim_norm(a), _sim_norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            current[j] = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (0 if ca == cb else 1),
            )
        previous = current
    return 1.0 - previous[-1] / max(len(a), len(b))


def build_fake_titles(rng: random.Random, n: int, pool_titles: list[str]) -> list[str]:
    """Fabricated titles that are not similar to any real pool title (Major by construction)."""
    out: list[str] = []
    used: set[str] = set()
    attempts = 0
    while len(out) < n:
        attempts += 1
        if attempts > n * 500:
            raise RuntimeError("could not synthesise enough distinct fake titles")
        title = make_fake_title(rng)
        key = _norm_key(title)
        if not key or key in used:
            continue
        if max((char_similarity(title, real) for real in pool_titles), default=0.0) >= 0.78:
            continue  # a title near a real record would not be a clean Major
        used.add(key)
        out.append(title)
    return out


def build_fake_venues(rng: random.Random, n: int, real_venues: list[str]) -> list[str]:
    out: list[str] = []
    used = {_norm_key(v) for v in real_venues}
    attempts = 0
    while len(out) < n:
        attempts += 1
        if attempts > n * 500:
            raise RuntimeError("could not synthesise enough distinct fake journal names")
        venue = make_fake_venue(rng)
        key = _norm_key(venue)
        if not key or key in used:
            continue
        used.add(key)
        out.append(venue)
    return out


def build_minor(
    work: dict,
    kind: str,
    rng: random.Random,
    fake_value: str = "",
) -> dict:
    """Return the claimed fields plus a corruption tag for one Minor perturbation."""
    authors = list(work["authors"])
    year = work["year"]
    venue = work["venue"]
    volume, issue, pages, doi = work["volume"], work["issue"], pages_of(work), work["doi"]
    if kind == "year":
        delta = rng.choice([-3, -2, -1, 1, 2, 3])
        new_year = year + delta
        while not (1950 <= new_year <= 2026) or new_year == year:
            delta = rng.choice([-3, -2, -1, 1, 2, 3])
            new_year = year + delta
        year = new_year
        corruption = f"minor:year {work['year']}->{new_year}"
    elif kind == "author_order":
        if rng.random() < 0.5:
            authors[0], authors[1] = authors[1], authors[0]
        else:
            authors = authors[1:] + authors[:1]
        if author_string(authors[:3]) == author_string(work["authors"][:3]):
            authors[0], authors[1] = authors[1], authors[0]
        corruption = "minor:author_order"
    elif kind == "venue":
        venue = fake_value
        corruption = f"minor:venue {work['venue']}->{venue}"
    elif kind == "volume_issue":
        if rng.random() < 0.5:
            new_volume = str(int(volume) + rng.choice([-1, 1]))
            if int(new_volume) < 1:
                new_volume = str(int(volume) + 1)
            volume = new_volume
            corruption = f"minor:volume {work['volume']}->{new_volume}"
        else:
            new_issue = str(int(issue) + rng.choice([-1, 1]))
            if int(new_issue) < 1:
                new_issue = str(int(issue) + 1)
            issue = new_issue
            corruption = f"minor:issue {work['issue']}->{new_issue}"
    elif kind == "pages":
        first_page, last_page = int(work["first_page"]), int(work["last_page"])
        shift = rng.choice([-6, -4, -2, 2, 4, 6])
        new_first = max(1, first_page + shift)
        if new_first == first_page:
            new_first = first_page + 2
        new_last = max(new_first, last_page + shift)
        pages = f"{new_first}-{new_last}" if new_last != new_first else str(new_first)
        corruption = f"minor:pages {pages_of(work)}->{pages}"
    else:  # pragma: no cover
        raise ValueError(f"unknown minor kind: {kind}")
    return {
        "authors": authors,
        "title": work["title"],
        "venue": venue,
        "year": year,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": doi,
        "corruption": corruption,
    }


def build_major(work: dict, kind: str, fake_value: str) -> dict:
    """Return the claimed fields plus a corruption tag for one fabricated element."""
    claimed = {
        "authors": list(work["authors"]),
        "title": work["title"],
        "venue": work["venue"],
        "year": work["year"],
        "volume": work["volume"],
        "issue": work["issue"],
        "pages": pages_of(work),
        "doi": work["doi"],
    }
    if kind == "fake_title":
        claimed["title"] = fake_value
        claimed["corruption"] = "major:fake_title"
    elif kind == "fake_doi":
        claimed["doi"] = fake_value
        claimed["corruption"] = "major:fake_doi"
    else:  # pragma: no cover
        raise ValueError(f"unknown major kind: {kind}")
    return claimed


def _gold(work: dict) -> dict:
    """Gold metadata of the *real* OpenAlex record the reference was built from."""
    return {
        "title": work["title"],
        "doi": work["doi"],
        "year": work["year"],
        "authors": list(work["authors"]),
        "venue": work["venue"],
        "volume": work["volume"],
        "issue": work["issue"],
        "pages": pages_of(work),
    }


def _work_id(work: dict) -> str:
    return (work.get("id") or "").rstrip("/").rsplit("/", 1)[-1]


def _self_check(item_id: str, ref_string: str, claimed: dict) -> None:
    """Re-parse the rendered string and verify every rendered field round-trips."""
    parsed = parse_reference(ref_string)
    problems: list[str] = []
    if parsed.title != claimed["title"]:
        problems.append(f"title {parsed.title!r} != {claimed['title']!r}")
    if parsed.venue != claimed["venue"]:
        problems.append(f"venue {parsed.venue!r} != {claimed['venue']!r}")
    if parsed.year != claimed["year"]:
        problems.append(f"year {parsed.year!r} != {claimed['year']!r}")
    if parsed.volume != claimed["volume"]:
        problems.append(f"volume {parsed.volume!r} != {claimed['volume']!r}")
    if parsed.issue != claimed["issue"]:
        problems.append(f"issue {parsed.issue!r} != {claimed['issue']!r}")
    if parsed.pages != claimed["pages"]:
        problems.append(f"pages {parsed.pages!r} != {claimed['pages']!r}")
    if parsed.doi.lower() != claimed["doi"].lower():
        problems.append(f"doi {parsed.doi!r} != {claimed['doi']!r}")
    expected_authors = [a for a in claimed["authors"][:3] if a]
    actual_authors = [a for a in parsed.authors if a][:3]
    if actual_authors != expected_authors:
        problems.append(f"authors {actual_authors!r} != {expected_authors!r}")
    if problems:
        raise RuntimeError(f"{item_id}: parser round-trip failed: " + "; ".join(problems))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _plan(kind_counts: tuple, rng: random.Random) -> list[dict]:
    plan: list[dict] = []
    for kind, total, no_doi in kind_counts:
        plan.extend({"kind": kind, "no_doi": True} for _ in range(no_doi))
        plan.extend({"kind": kind, "no_doi": False} for _ in range(total - no_doi))
    rng.shuffle(plan)
    return plan


def main(argv: Optional[list[str]] = None) -> int:
    argp = argparse.ArgumentParser(description="Build the CiteBench-CN evaluation set.")
    argp.add_argument("--seed", type=int, default=20261022, help="random seed (default: 20261022)")
    argp.add_argument("--refresh", action="store_true", help="refetch the OpenAlex pool from scratch")
    args = argp.parse_args(argv)

    rng = random.Random(args.seed)
    works, pool_stats = load_or_fetch_pool(refresh=args.refresh)
    eligible = eligible_works(works)
    pool_stats["eligible"] = len(eligible)
    if len(eligible) < N_TOTAL:
        print(
            f"[fatal] only {len(eligible)} eligible works, {N_TOTAL} needed. "
            f"OpenAlex pool too small (network/API failure?)",
            file=sys.stderr,
        )
        return 2
    print(f"[pool] eligible base records: {len(eligible)}")

    # Deterministic base selection: eligible_works() sorted by id, then seeded shuffle.
    rng.shuffle(eligible)
    pool = list(eligible)  # popped from the end; deterministic order

    pool_titles = [w["title"] for w in eligible]
    real_venues = [w["venue"] for w in eligible]
    fake_titles = build_fake_titles(rng, MAJOR_PLAN[0][1], pool_titles)
    fake_venues = build_fake_venues(rng, FAKE_VENUE_COUNT, real_venues)

    print("[major] generating fabricated DOIs and verifying they are 404 via doi.org ...")
    fake_dois, fake_doi_check = validate_fabricated_dois(rng, MAJOR_PLAN[1][1])
    if fake_doi_check.get("all_missing") is False:
        bad = [d for d, v in (fake_doi_check.get("verdicts") or {}).items() if v]
        print(f"[fatal] fabricated DOI(s) resolve to a real record: {bad}", file=sys.stderr)
        return 3
    if fake_doi_check.get("all_missing") is None:
        print("[warn] fabricated DOIs not all verified against doi.org "
              "(prefix 10.9999 is unregistered by construction)")

    rows: list[dict] = []
    rejected = 0

    def next_base(what: str) -> dict:
        if not pool:
            raise RuntimeError(f"OpenAlex base pool exhausted while building {what}")
        return pool.pop()

    def add_row(work: dict, claimed: dict, label: str, tag: str) -> None:
        ref_string = render_reference(
            claimed["authors"],
            claimed["title"],
            claimed["venue"],
            claimed["year"],
            claimed["volume"],
            claimed["issue"],
            claimed["pages"],
            claimed["doi"],
        )
        _self_check(tag, ref_string, claimed)
        rows.append(
            {
                "id": "",
                "ref_string": ref_string,
                "label": label,
                "corruption": claimed["corruption"],
                "gold": _gold(work),
                "source": f"openalex:{_work_id(work)}",
            }
        )

    exact_plan = _plan((("exact", N_EXACT, NO_DOI_EXACT),), rng)
    minor_plan = _plan(MINOR_PLAN, rng)
    major_plan = _plan(MAJOR_PLAN, rng)
    no_doi_total = sum(1 for item in exact_plan + minor_plan + major_plan if item["no_doi"])
    if no_doi_total != 75:
        print(f"[fatal] no-DOI plan is {no_doi_total}, expected 75", file=sys.stderr)
        return 4

    # --- Exact -------------------------------------------------------------
    exact_index = 0
    while exact_index < len(exact_plan):
        item = exact_plan[exact_index]
        work = next_base("Exact")
        claimed = {
            "authors": list(work["authors"]),
            "title": work["title"],
            "venue": work["venue"],
            "year": work["year"],
            "volume": work["volume"],
            "issue": work["issue"],
            "pages": pages_of(work),
            "doi": work["doi"] if not item["no_doi"] else "",
            "corruption": "none" if not item["no_doi"] else "none (no DOI)",
        }
        try:
            add_row(work, claimed, "Exact", "exact")
        except RuntimeError as exc:
            rejected += 1
            print(f"[skip] {exc}")
            continue
        exact_index += 1

    # --- Minor -------------------------------------------------------------
    minor_index = 0
    fake_venue_index = 0
    while minor_index < len(minor_plan):
        item = minor_plan[minor_index]
        kind = item["kind"]
        work = next_base("Minor")
        fake_value = fake_venues[fake_venue_index] if kind == "venue" else ""
        try:
            claimed = build_minor(work, kind, rng, fake_value=fake_value)
            if item["no_doi"]:
                claimed["doi"] = ""
                claimed["corruption"] += " (no DOI)"
            add_row(work, claimed, "Minor", f"minor[{kind}]")
        except (RuntimeError, ValueError) as exc:
            rejected += 1
            print(f"[skip] {type(exc).__name__}: {exc}")
            continue
        if kind == "venue":
            fake_venue_index += 1
        minor_index += 1

    # --- Major -------------------------------------------------------------
    major_index = 0
    fake_title_index = 0
    fake_doi_index = 0
    while major_index < len(major_plan):
        item = major_plan[major_index]
        kind = item["kind"]
        if kind == "fake_title":
            fake_value = fake_titles[fake_title_index]
        else:
            fake_value = fake_dois[fake_doi_index]
            if item["no_doi"]:  # pragma: no cover - plan guarantees False
                raise RuntimeError("fake-DOI Major sample cannot be built without a DOI")
        work = next_base("Major")
        try:
            claimed = build_major(work, kind, fake_value)
            if item["no_doi"]:
                claimed["doi"] = ""
                claimed["corruption"] += " (no DOI)"
            add_row(work, claimed, "Major", f"major[{kind}]")
        except RuntimeError as exc:
            rejected += 1
            print(f"[skip] {exc}")
            continue
        if kind == "fake_title":
            fake_title_index += 1
        else:
            fake_doi_index += 1
        major_index += 1

    if len(rows) != N_TOTAL:
        print(f"[fatal] expected {N_TOTAL} rows, built {len(rows)}", file=sys.stderr)
        return 4
    print(f"[done] built {N_TOTAL} references "
          f"({rejected} base records rejected by the round-trip check)")

    # Shuffle so the dataset order does not leak the label, then assign ids.
    rng.shuffle(rows)
    for idx, row in enumerate(rows, 1):
        row["id"] = f"cbcn-{idx:04d}"

    JSONL_PATH.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",  # LF everywhere: identical bytes and SHA-256 on Windows and Linux
    )

    counts = {"Exact": 0, "Minor": 0, "Major": 0}
    no_doi_counts = {"Exact": 0, "Minor": 0, "Major": 0}
    minor_breakdown: dict[str, int] = {}
    major_breakdown: dict[str, int] = {}
    for row in rows:
        counts[row["label"]] += 1
        if "(no DOI)" in row["corruption"]:
            no_doi_counts[row["label"]] += 1
        if row["label"] == "Minor":
            body = row["corruption"].split(":", 1)[1].replace(" (no DOI)", "")
            kind = body.split(" ", 1)[0]
            minor_breakdown[kind] = minor_breakdown.get(kind, 0) + 1
        elif row["label"] == "Major":
            body = row["corruption"].split(":", 1)[1].replace(" (no DOI)", "")
            kind = body.split(" ", 1)[0]
            major_breakdown[kind] = major_breakdown.get(kind, 0) + 1

    meta = {
        "dataset": "CiteBench-CN",
        "version": 3,
        "built_at": _utc_now(),
        "seed": args.seed,
        "n": len(rows),
        "counts": counts,
        "no_doi": {**no_doi_counts, "total": no_doi_total},
        "minor_breakdown": minor_breakdown,
        "major_breakdown": major_breakdown,
        "label_definitions": {
            "Exact": "title, year, authors, source, volume/issue/pages and DOI all match the real record",
            "Minor": "the paper really exists, but one field drifts: year / author order / "
                     "source / volume-issue / pages",
            "Major": "the title cannot be found in open databases, or the DOI is an unrelated "
                     "DOI that resolves to no record (404)",
            "doi_case_note": "DOI letter-case changes are not used as Minor samples: DOIs are "
                             "case-insensitive, so a case change is semantically Exact.",
        },
        "source": {
            "provider": "OpenAlex",
            "license": "CC0 1.0",
            "api": OPENALEX_URL,
            "filter": OPENALEX_FILTER,
            "select": OPENALEX_SELECT,
            "mailto": MAILTO,
            "note": "Base records are real OpenAlex works (language=zh, has_doi). "
                    "Each reference is a synthetic GB/T 7714 rendering; labels are fixed by construction.",
        },
        "pool": {**pool_stats, "bases_used": N_TOTAL, "render_rejections": rejected},
        "fabricated_doi_check": {
            "prefix": FAKE_DOI_PREFIX,
            "checked": fake_doi_check.get("checked"),
            "all_missing": fake_doi_check.get("all_missing"),
            "verdicts": fake_doi_check.get("verdicts"),
        },
        "gold_note": "gold = metadata of the real OpenAlex record used as the base; "
                     "the fabricated/perturbed value is described in `corruption`.",
        "files": {"jsonl": JSONL_PATH.name},
        "build_cmd": "PYTHONPATH=src python3 scripts/build_citebench.py",
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    if LEGACY_FAKE_DOI_CACHE.exists():
        LEGACY_FAKE_DOI_CACHE.unlink()

    print(f"[done] wrote {len(rows)} rows -> {JSONL_PATH}")
    print(f"[done] label counts: {counts}, no-DOI: {no_doi_counts} (total {no_doi_total})")
    print(f"[done] minor breakdown: {minor_breakdown}")
    print(f"[done] major breakdown: {major_breakdown}")
    print(f"[done] fabricated DOI check: {fake_doi_check.get('checked')} checked, "
          f"all_missing={fake_doi_check.get('all_missing')}")
    print(f"[done] metadata -> {META_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
