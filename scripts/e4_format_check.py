"""E4: GB/T 7714-2025 format-check experiment on real Chinese references.

What it does
------------
1. Takes 100 real Chinese-language records with a DOI from OpenAlex
   (``language:zh,has_doi:true``, CC0), reusing the pool already fetched for
   CiteBench-CN and, on first run, fetching ``--pages`` fresh pages (page JSON is
   cached under ``data/experiments/cache_e4/`` so reruns cost 0 requests).
2. Renders each record as a GB/T 7714-style entry (``[J]`` / ``[C]`` / ``[M]``)
   and parses it back with ``citeguard.reference_parser``.
3. Runs ``citeguard.gbt7714.check_reference`` and reports
   - type-code recognition rate,
   - required-field completeness (rendered vs. parsed, per type),
   - defect distribution (level / field / message),
   - parser field-recovery rate.
4. Builds 30 controlled format drifts (6 categories x 5 base records) and news
   up the rule-layer detection rate, per case. Detection is *differential*: an
   issue counts only if it is not already present in the corresponding
   undrifted base entry (the base entries share a known baseline issue, see
   ``docs/experiments.md``).

Outputs
-------
``data/experiments/e4_format.json`` (all numbers + per-entry / per-case detail).

Usage
-----
    PYTHONPATH=src python3 scripts/e4_format_check.py            # cached rerun, 0 requests
    PYTHONPATH=src python3 scripts/e4_format_check.py --refresh  # refetch OpenAlex pages
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402

import citeguard.gbt7714 as gbt  # noqa: E402
from citeguard.reference_parser import normalize_text, parse_reference  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_DIR = ROOT / "data"
CB_DIR = DATA_DIR / "citebench_cn"
POOL_FILE = CB_DIR / "openalex_zh_works.json"
OUT_DIR = DATA_DIR / "experiments"
CACHE_DIR = OUT_DIR / "cache_e4"
OUT_FILE = OUT_DIR / "e4_format.json"

OPENALEX_URL = "https://api.openalex.org/works"
OPENALEX_FILTER = "language:zh,has_doi:true"
OPENALEX_SELECT = (
    "id,doi,title,publication_year,authorships,primary_location,biblio,type,language"
)
OPENALEX_MAILTO = "citeguard@example.org"
USER_AGENT = "CiteGuard-CN/0.1 (research prototype; format-check experiment)"

SEED = 20261022
N_ENTRIES = 100
# Target composition of the 100-entry corpus (filled from other types when scarce).
TARGET = {"J": 85, "C": 10, "M": 5}
TYPE_MAP = {
    "article": "J",
    "review": "J",
    "conference-paper": "C",
    "book": "M",
    "book-chapter": "M",
}
VENUE_BLACKLIST = (
    "doaj", "pubmed", "semantic scholar", "crossref", "researchgate",
    "openalex", "directory of open access", "web of science", "scopus",
    "cnki", "wanfang",
)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


CODE_FILES = (
    "src/citeguard/gbt7714.py",
    "src/citeguard/reference_parser.py",
    "src/citeguard/metadata_verify.py",
)


def code_snapshot() -> dict:
    """Record which source revision the numbers were produced on.

    The project is being edited concurrently by the team; the E4/E5 code paths
    (parser + rule engine + verifier) can change between runs, so the exact file
    hashes are part of the result.
    """
    out = {}
    for rel in CODE_FILES:
        path = ROOT / rel
        if path.exists():
            out[rel] = {
                "sha256_16": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
    return out


# ---------------------------------------------------------------------------
# Corpus acquisition
# ---------------------------------------------------------------------------

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
        "title": unicodedata.normalize("NFKC", raw.get("title") or "").strip(),
        "year": raw.get("publication_year"),
        "authors": authors,
        "venue": unicodedata.normalize("NFKC", source.get("display_name") or "").strip(),
        "volume": str(biblio.get("volume") or "").strip(),
        "issue": str(biblio.get("issue") or "").strip(),
        "first_page": str(biblio.get("first_page") or "").strip(),
        "last_page": str(biblio.get("last_page") or "").strip(),
        "type": (raw.get("type") or "").strip(),
    }


class RequestStats:
    """Counts real HTTP GETs so the report can show actual OpenAlex usage."""

    def __init__(self) -> None:
        self.attempts = 0
        self.ok = 0
        self.failed = 0
        self.errors: list[str] = []
        self.cache_hits = 0

    def to_dict(self) -> dict:
        return {
            "http_attempts": self.attempts,
            "http_ok": self.ok,
            "http_failed": self.failed,
            "cache_hits": self.cache_hits,
            "errors": self.errors[:10],
        }


def _fetch_page(page: int, per_page: int, stats: RequestStats, refresh: bool) -> Optional[dict]:
    """Fetch one OpenAlex page, caching the raw payload for idempotent reruns."""
    cp = CACHE_DIR / f"openalex_page{page}_per{per_page}.json"
    if cp.exists() and not refresh:
        try:
            stats.cache_hits += 1
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    params = {
        "filter": OPENALEX_FILTER,
        "per-page": per_page,
        "page": page,
        "select": OPENALEX_SELECT,
        "mailto": OPENALEX_MAILTO,
    }
    for attempt in range(3):
        stats.attempts += 1
        try:
            resp = requests.get(
                OPENALEX_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=45
            )
            if resp.status_code == 200:
                stats.ok += 1
                payload = resp.json()
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                time.sleep(0.12)
                return payload
            stats.failed += 1
            stats.errors.append(f"page {page}: HTTP {resp.status_code} {resp.text[:120]}")
        except Exception as exc:  # pragma: no cover - network dependent
            stats.failed += 1
            stats.errors.append(f"page {page}: {type(exc).__name__}: {exc}")
        time.sleep(1.5 * (attempt + 1))
    return None


def _work_is_usable(work: dict) -> bool:
    """Loose eligibility for a *format* experiment (biblio may be incomplete)."""
    title = work.get("title") or ""
    if not (4 <= len(title) <= 120):
        return False
    if not CJK_RE.search(title):
        return False
    if re.search(r"[\[\]\.．。\r\n\t\ufffd]", title):
        return False
    if not DOI_RE.match(work.get("doi") or ""):
        return False
    year = work.get("year")
    if not isinstance(year, int) or not (1950 <= year <= 2026):
        return False
    venue = work.get("venue") or ""
    if not venue or len(venue) > 60:
        return False
    low = venue.lower()
    if any(key in low for key in VENUE_BLACKLIST):
        return False
    authors = work.get("authors") or []
    if not authors:
        return False
    for name in authors[:8]:
        if len(name) > 60 or re.search(r"[,\uFF0C;；。\r\n\t]", name):
            return False
    return work.get("type") in TYPE_MAP


def _dedupe(works: list[dict]) -> list[dict]:
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    out: list[dict] = []
    for work in sorted(works, key=lambda w: w.get("id") or ""):
        doi_key = (work.get("doi") or "").lower()
        title_key = re.sub(r"[^\w\u4e00-\u9fff]+", "", (work.get("title") or "").lower())
        if not doi_key or not title_key or doi_key in seen_doi or title_key in seen_title:
            continue
        seen_doi.add(doi_key)
        seen_title.add(title_key)
        out.append(work)
    return out


def acquire_corpus(
    entries: int, pages: int, per_page: int, refresh: bool, seed: int
) -> tuple[list[dict], dict]:
    stats = RequestStats()
    fetched: list[dict] = []
    for page in range(1, pages + 1):
        payload = _fetch_page(page, per_page, stats, refresh)
        if not payload:
            continue
        for raw in payload.get("results") or []:
            fetched.append(_normalize_work(raw))

    pool_meta: dict[str, Any] = {}
    pool_works: list[dict] = []
    if POOL_FILE.exists():
        try:
            payload = json.loads(POOL_FILE.read_text(encoding="utf-8"))
            pool_meta = payload.get("meta") or {}
            pool_works = [dict(w) for w in (payload.get("works") or [])]
        except Exception as exc:
            stats.errors.append(f"pool read: {type(exc).__name__}: {exc}")

    combined = _dedupe(fetched + pool_works)
    usable = [w for w in combined if _work_is_usable(w)]
    all_by_type: dict[str, int] = {}
    for work in combined:
        code = TYPE_MAP.get(work.get("type") or "", work.get("type") or "other")
        all_by_type[code] = all_by_type.get(code, 0) + 1
    rng = random.Random(seed)
    rng.shuffle(usable)

    selected: list[dict] = []
    for type_code, target in TARGET.items():
        picked = [w for w in usable if TYPE_MAP[w["type"]] == type_code][:target]
        selected.extend(picked)
    # Fill any shortfall with journal articles not already selected.
    selected_ids = {w["id"] for w in selected}
    if len(selected) < entries:
        for work in usable:
            if len(selected) >= entries:
                break
            if TYPE_MAP[work["type"]] != "J" or work["id"] in selected_ids:
                continue
            selected.append(work)
            selected_ids.add(work["id"])
    selected = selected[:entries]
    per_type: dict[str, int] = {}
    for work in selected:
        code = TYPE_MAP[work["type"]]
        per_type[code] = per_type.get(code, 0) + 1
    available_by_type: dict[str, int] = {}
    for work in usable:
        code = TYPE_MAP[work["type"]]
        available_by_type[code] = available_by_type.get(code, 0) + 1

    provenance = {
        "provider": "OpenAlex",
        "license": "CC0 1.0",
        "api": OPENALEX_URL,
        "filter": OPENALEX_FILTER,
        "select": OPENALEX_SELECT,
        "mailto": OPENALEX_MAILTO,
        "local_pool_file": str(POOL_FILE.relative_to(ROOT)) if POOL_FILE.exists() else "",
        "local_pool_works": len(pool_works),
        "local_pool_pages": pool_meta.get("pages_fetched"),
        "local_pool_fetched_at": pool_meta.get("fetched_at"),
        "fresh_pages_requested": pages,
        "per_page": per_page,
        "fresh_works": len(fetched),
        "deduped_works": len(combined),
        "deduped_by_type": all_by_type,
        "usable_works": len(usable),
        "usable_by_type": available_by_type,
        "selected": len(selected),
        "selected_by_type": per_type,
        "seed": seed,
        "requests": stats.to_dict(),
        "generated_at": _utc_now(),
    }
    return selected, provenance


# ---------------------------------------------------------------------------
# Rendering (GB/T 7714 style) and parsing
# ---------------------------------------------------------------------------

def _pages(work: dict) -> str:
    first, last = work.get("first_page") or "", work.get("last_page") or ""
    if not first:
        return ""
    return f"{first}–{last}" if last and last != first else first


def _authors(work: dict, limit: int = 3, et_al: bool = True) -> str:
    names = list(work.get("authors") or [])
    shown = names[:limit]
    text = ", ".join(shown)
    if et_al and len(names) > limit:
        text += ", 等"
    return text


def render_entry(work: dict, type_code: str, *, pages_text: Optional[str] = None) -> str:
    """Render one record as a GB/T 7714-style entry of the requested type."""
    authors = _authors(work)
    title = work["title"]
    venue = work["venue"]
    year = work["year"]
    pages = _pages(work) if pages_text is None else pages_text

    if type_code in {"J", "C"}:
        ref = f"{authors}. {title}[{type_code}]. {venue}, {year}"
        if type_code == "J":
            volume, issue = work.get("volume") or "", work.get("issue") or ""
            if volume and issue:
                ref += f", {volume}({issue})"
            elif volume:
                ref += f", {volume}"
            elif issue:
                ref += f", ({issue})"
        if pages:
            ref += f": {pages}"
        ref += "."
    elif type_code == "M":
        # OpenAlex has no publication place for books; the source name is used as
        # the publisher, so 出版地 stays absent on purpose (data gap, not a rule bug).
        ref = f"{authors}. {title}[M]. {venue}, {year}."
    elif type_code == "D":
        ref = f"{authors}. {title}[D]. {venue}, {year}."
    else:  # pragma: no cover - defensive
        ref = f"{authors}. {title}[{type_code}]. {venue}, {year}."
    if work.get("doi"):
        ref += f" DOI: {work['doi']}."
    return ref


def _field_value(parsed, field_name: str) -> str:
    if field_name == "doi":
        return parsed.doi or parsed.url
    if field_name == "year":
        return str(parsed.year) if parsed.year else ""
    return str(getattr(parsed, field_name, "") or "")


def _norm_cmp(text: str) -> str:
    """Comparison key: whitespace/punctuation-insensitive and dash-insensitive.

    Pages are rendered with an en dash (``1–5``) but the parser stores a plain
    hyphen (``1-5``); that is a formatting difference, not a field-recovery loss.
    """
    t = normalize_text(text or "").lower()
    for dash in ("–", "—", "~", "～"):
        t = t.replace(dash, "-")
    return re.sub(r"[\s\.,;:，；：、]+", "", t)


def _supplied_fields(work: dict, type_code: str) -> dict[str, str]:
    """Fields the renderer actually put into the entry (ground truth for parsing)."""
    venue = work["venue"]
    supplied = {
        "title": work["title"],
        "venue": venue,
        "year": str(work["year"]),
        "volume": work.get("volume") or "",
        "issue": work.get("issue") or "",
        "pages": _pages(work),
        "doi": work.get("doi") or "",
    }
    if type_code == "M":
        # The [M] rendering has no biblio fields and uses the source name as publisher.
        supplied.update(
            {"venue": "", "publisher": venue, "place": "", "volume": "", "issue": "", "pages": ""}
        )
    if type_code == "D":
        supplied.update({"venue": "", "institution": venue, "place": ""})
    return supplied


def check_entry(work: dict, type_code: str, idx: int) -> dict:
    rendered = render_entry(work, type_code)
    parsed = parse_reference(rendered, index=idx)
    result = gbt.check_reference(parsed)
    supplied = _supplied_fields(work, type_code)
    required = gbt.REQUIRED.get(type_code, [])

    required_detail = {}
    for field_name in required:
        rendered_has = bool(supplied.get(field_name))
        parsed_has = bool(_field_value(parsed, field_name)) if rendered_has else False
        required_detail[field_name] = {
            "supplied_in_rendering": rendered_has,
            "recovered_by_parser": parsed_has,
        }

    recovery = {}
    for field_name, value in supplied.items():
        if not value:
            continue
        got = _field_value(parsed, field_name)
        recovery[field_name] = {
            "supplied": value,
            "parsed": got,
            "recovered": bool(got) and _norm_cmp(got) == _norm_cmp(value),
        }

    return {
        "index": idx,
        "source_id": work["id"],
        "doi": work["doi"],
        "openalex_type": work["type"],
        "type_code": type_code,
        "rendered": rendered,
        "parsed": {
            "doc_type": parsed.doc_type,
            "title": parsed.title,
            "authors": parsed.authors,
            "venue": parsed.venue,
            "year": parsed.year,
            "volume": parsed.volume,
            "issue": parsed.issue,
            "pages": parsed.pages,
            "doi": parsed.doi,
            "place": parsed.place,
            "publisher": parsed.publisher,
            "institution": parsed.institution,
        },
        "type_recognized": parsed.doc_type == type_code,
        "required": required_detail,
        "recovery": recovery,
        "score": result.score,
        "issues": [i.to_dict() for i in result.issues],
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _issue_key(issue: dict) -> tuple[str, str, str]:
    return (issue["level"], issue["field"], issue["message"])


def summarize_corpus(entries: list[dict]) -> dict:
    n = len(entries)
    by_type: dict[str, list[dict]] = {}
    for e in entries:
        by_type.setdefault(e["type_code"], []).append(e)

    type_recognized = sum(1 for e in entries if e["type_recognized"])
    type_misses = [
        {
            "index": e["index"],
            "expected": e["type_code"],
            "parsed": e["parsed"]["doc_type"],
            "rendered": e["rendered"],
        }
        for e in entries
        if not e["type_recognized"]
    ]

    required_stats = {}
    for type_code, items in sorted(by_type.items()):
        fields = gbt.REQUIRED.get(type_code, [])
        supplied = sum(
            1 for e in items for f in fields if e["required"].get(f, {}).get("supplied_in_rendering")
        )
        recovered = sum(
            1 for e in items for f in fields if e["required"].get(f, {}).get("recovered_by_parser")
        )
        entries_complete = sum(
            1
            for e in items
            if all(e["required"].get(f, {}).get("recovered_by_parser") for f in fields)
        )
        required_stats[type_code] = {
            "entries": len(items),
            "required_fields": fields,
            "field_slots": len(items) * len(fields),
            "supplied_in_rendering": supplied,
            "recovered_by_parser": recovered,
            "completeness_rate": round(recovered / (len(items) * len(fields)), 4)
            if items and fields
            else 0.0,
            "entries_complete": entries_complete,
            "entries_complete_rate": round(entries_complete / len(items), 4) if items else 0.0,
        }

    field_slots = sum(v["field_slots"] for v in required_stats.values())
    recovered_all = sum(v["recovered_by_parser"] for v in required_stats.values())
    supplied_all = sum(v["supplied_in_rendering"] for v in required_stats.values())

    issue_counter: dict[tuple[str, str, str], int] = {}
    level_counter = {"error": 0, "warning": 0, "info": 0}
    entries_with_error = 0
    entries_with_warning = 0
    entries_clean = 0
    for e in entries:
        if any(i["level"] == "error" for i in e["issues"]):
            entries_with_error += 1
        if any(i["level"] == "warning" for i in e["issues"]):
            entries_with_warning += 1
        if not e["issues"]:
            entries_clean += 1
        for issue in e["issues"]:
            level_counter[issue["level"]] = level_counter.get(issue["level"], 0) + 1
            key = _issue_key(issue)
            issue_counter[key] = issue_counter.get(key, 0) + 1

    distribution = [
        {"level": k[0], "field": k[1], "message": k[2], "count": v}
        for k, v in sorted(issue_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    by_field: dict[str, int] = {}
    for (level, field, _msg), count in issue_counter.items():
        by_field[field] = by_field.get(field, 0) + count

    # Sensitivity: the punctuation rule used to fire on *every* entry in v0.2
    # (it triggered when the character before "[J]" was NOT a period, i.e. the
    # standard-correct form). It was fixed to "题名与文献类型标识之间不应有“.”"
    # in v0.3 while this experiment was being run; the block below quantifies how
    # much of the defect count comes from that single rule.
    punctuation_msgs = {
        "题名与文献类型标识之间缺少“.”",  # v0.2 (buggy) message
        "题名与文献类型标识之间不应有“.”",  # v0.3 (fixed) message
    }
    errors_excl_punct = 0
    clean_excl_punct = 0
    for e in entries:
        remaining = [
            i for i in e["issues"] if not (i["field"] == "punctuation" and i["message"] in punctuation_msgs)
        ]
        errors_excl_punct += sum(1 for i in remaining if i["level"] == "error")
        if not remaining:
            clean_excl_punct += 1

    recovery_stats: dict[str, dict] = {}
    for e in entries:
        for field_name, rec in e["recovery"].items():
            slot = recovery_stats.setdefault(field_name, {"supplied": 0, "recovered": 0})
            slot["supplied"] += 1
            slot["recovered"] += 1 if rec["recovered"] else 0
    for field_name, slot in recovery_stats.items():
        slot["rate"] = round(slot["recovered"] / slot["supplied"], 4) if slot["supplied"] else 0.0

    scores = sorted(e["score"] for e in entries)
    return {
        "n": n,
        "by_type": {k: len(v) for k, v in sorted(by_type.items())},
        "type_code_recognition": {
            "recognized": type_recognized,
            "total": n,
            "rate": round(type_recognized / n, 4) if n else 0.0,
            "misses": type_misses,
        },
        "required_fields": {
            "overall": {
                "field_slots": field_slots,
                "supplied_in_rendering": supplied_all,
                "recovered_by_parser": recovered_all,
                "completeness_rate": round(recovered_all / field_slots, 4) if field_slots else 0.0,
                "rendering_completeness_rate": round(supplied_all / field_slots, 4)
                if field_slots
                else 0.0,
            },
            "by_type": required_stats,
        },
        "defects": {
            "issues_total": sum(level_counter.values()),
            "by_level": level_counter,
            "entries_with_error": entries_with_error,
            "entries_with_warning": entries_with_warning,
            "entries_clean": entries_clean,
            "clean_rate": round(entries_clean / n, 4) if n else 0.0,
            "error_rate": round(entries_with_error / n, 4) if n else 0.0,
            "distribution": distribution,
            "by_field": dict(sorted(by_field.items(), key=lambda kv: -kv[1])),
            "sensitivity_without_punctuation_rule": {
                "errors": errors_excl_punct,
                "entries_clean": clean_excl_punct,
                "clean_rate": round(clean_excl_punct / n, 4) if n else 0.0,
            },
        },
        "parser_field_recovery": recovery_stats,
        "compliance_score": {
            "avg": round(sum(scores) / n, 2) if n else 0.0,
            "median": scores[n // 2] if n else 0,
            "min": scores[0] if n else 0,
            "max": scores[-1] if n else 0,
        },
    }


# ---------------------------------------------------------------------------
# Controlled format drifts (30 cases)
# ---------------------------------------------------------------------------

DRIFT_CATEGORIES = (
    "missing_volume_issue",
    "hyphen_pages",
    "four_authors_no_et_al",
    "missing_doi",
    "volume_issue_swap",
    "thesis_type_code",
)

CATEGORY_LABELS = {
    "missing_volume_issue": "缺卷期",
    "hyphen_pages": "页码用连字符 1-5（规范为 1–5）",
    "four_authors_no_et_al": "4 名作者未用「等」",
    "missing_doi": "缺 DOI",
    "volume_issue_swap": "卷期混淆",
    "thesis_type_code": "学位论文类型码错（期刊条目标成 [D]）",
}

EXPECTED_RULE = {
    "missing_volume_issue": "volume/issue 缺失 → 提示补卷/期",
    "hyphen_pages": "页码连接号：标准原文的破折号规定未核实，规则层不改单条，只在全文混用时提示（见 check_reference_list）",
    "four_authors_no_et_al": "作者超过 3 人应写「等」（规则层已支持：作者数 >3 且无「等」→ error）",
    "missing_doi": "doi 缺失 → 提示补 DOI",
    "volume_issue_swap": "卷/期语义校验（需元数据，格式层无此规则）",
    "thesis_type_code": "类型码错误 → 应报 [D] 字段不符",
}


def _build_drifts(bases: list[dict]) -> list[dict]:
    cases: list[dict] = []
    for base_no, work in enumerate(bases, 1):
        volume = work.get("volume") or "1"
        issue = work.get("issue") or "1"
        pages = _pages(work) or "1–5"
        base_entry = render_entry(work, "J")

        variants = []
        # 1) missing volume + issue
        v = f"{_authors(work)}. {work['title']}[J]. {work['venue']}, {work['year']}"
        if pages:
            v += f": {pages}"
        v += f". DOI: {work['doi']}."
        variants.append(("missing_volume_issue", v, {"volume": "", "issue": ""}))

        # 2) ASCII hyphen instead of the required en dash in the page range
        hyphen_pages = pages.replace("–", "-")
        v = (
            f"{_authors(work)}. {work['title']}[J]. {work['venue']}, {work['year']}, "
            f"{volume}({issue}): {hyphen_pages}. DOI: {work['doi']}."
        )
        variants.append(("hyphen_pages", v, {"pages": hyphen_pages}))

        # 3) four authors listed in full, no "等"
        names = list(work.get("authors") or [])
        four = ", ".join(names[:4]) if len(names) >= 4 else ", ".join(names)
        v = (
            f"{four}. {work['title']}[J]. {work['venue']}, {work['year']}, "
            f"{volume}({issue}): {pages}. DOI: {work['doi']}."
        )
        variants.append(("four_authors_no_et_al", v, {"authors": four}))

        # 4) DOI removed
        v = (
            f"{_authors(work)}. {work['title']}[J]. {work['venue']}, {work['year']}, "
            f"{volume}({issue}): {pages}."
        )
        variants.append(("missing_doi", v, {"doi": ""}))

        # 5) volume and issue swapped
        v = (
            f"{_authors(work)}. {work['title']}[J]. {work['venue']}, {work['year']}, "
            f"{issue}({volume}): {pages}. DOI: {work['doi']}."
        )
        variants.append(("volume_issue_swap", v, {"volume": issue, "issue": volume}))

        # 6) journal entry mislabelled as a thesis ([D])
        v = (
            f"{_authors(work)}. {work['title']}[D]. {work['venue']}, {work['year']}, "
            f"{volume}({issue}): {pages}. DOI: {work['doi']}."
        )
        variants.append(("thesis_type_code", v, {"doc_type": "D"}))

        for category, rendered, _fields in variants:
            parsed = parse_reference(rendered)
            result = gbt.check_reference(parsed)
            cases.append(
                {
                    "id": f"drift-{len(cases) + 1:02d}",
                    "category": category,
                    "category_label": CATEGORY_LABELS[category],
                    "base_index": base_no,
                    "base_id": work["id"],
                    "base_doi": work["doi"],
                    "rendered": rendered,
                    "parsed": {
                        "doc_type": parsed.doc_type,
                        "authors": parsed.authors,
                        "title": parsed.title,
                        "venue": parsed.venue,
                        "year": parsed.year,
                        "volume": parsed.volume,
                        "issue": parsed.issue,
                        "pages": parsed.pages,
                        "doi": parsed.doi,
                        "place": parsed.place,
                        "publisher": parsed.publisher,
                        "institution": parsed.institution,
                    },
                    "score": result.score,
                    "issues": [i.to_dict() for i in result.issues],
                }
            )
            cases[-1]["_base_entry"] = base_entry
    return cases


def _detect(case: dict) -> dict:
    """Differential detection: ignore issues already present in the base entry."""
    base_parsed = parse_reference(case["_base_entry"])
    base_issues = {_issue_key(i.to_dict()) for i in gbt.check_reference(base_parsed).issues}
    new_issues = [
        i for i in case["issues"] if _issue_key(i) not in base_issues
    ]
    category = case["category"]
    strict = False
    indirect = False
    matched: list[dict] = []

    if category == "missing_volume_issue":
        for issue in new_issues:
            if issue["field"] in {"volume", "issue"}:
                strict = True
                matched.append(issue)
    elif category == "missing_doi":
        for issue in new_issues:
            if issue["field"] == "doi":
                strict = True
                matched.append(issue)
    elif category == "four_authors_no_et_al":
        # Rule added after the first run of this experiment: >3 authors without
        # 等/et al is an error now.
        for issue in new_issues:
            if issue["field"] == "authors" and issue["level"] == "error":
                strict = True
                matched.append(issue)
    elif category == "thesis_type_code":
        # The rule layer cannot say "wrong type code"; it can only report the
        # required [D] fields that are missing. Count that as indirect only.
        for issue in new_issues:
            if issue["level"] == "error" and issue["field"] in {"place", "institution", "doc_type"}:
                indirect = True
                matched.append(issue)
    # hyphen_pages / volume_issue_swap: no single-reference rule can fire;
    # keeping ``new_issues`` in the record makes the miss auditable.
    return {
        "detected_strict": strict,
        "detected_indirect": (not strict) and indirect,
        "detected_any": bool(new_issues),
        "matched_issues": matched,
        "new_issues": new_issues,
    }


def summarize_drifts(cases: list[dict]) -> dict:
    for case in cases:
        det = _detect(case)
        case["detection"] = {
            "detected_strict": det["detected_strict"],
            "detected_indirect": det["detected_indirect"],
            "verdict": "strict" if det["detected_strict"] else ("indirect" if det["detected_indirect"] else "miss"),
            "matched_issues": det["matched_issues"],
            "new_issues": det["new_issues"],
        }
        case.pop("_base_entry", None)
    by_cat: dict[str, dict] = {}
    for case in cases:
        slot = by_cat.setdefault(
            case["category"],
            {
                "category": case["category"],
                "label": case["category_label"],
                "expected": EXPECTED_RULE[case["category"]],
                "n": 0,
                "strict": 0,
                "indirect": 0,
                "miss": 0,
                "examples": [],
            },
        )
        slot["n"] += 1
        verdict = case["detection"]["verdict"]
        slot["strict"] += 1 if verdict == "strict" else 0
        slot["indirect"] += 1 if verdict == "indirect" else 0
        slot["miss"] += 1 if verdict == "miss" else 0
        if len(slot["examples"]) < 2:
            slot["examples"].append(
                {
                    "id": case["id"],
                    "verdict": verdict,
                    "matched": [i["message"] for i in case["detection"]["matched_issues"]],
                    "new_issue_count": len(case["detection"]["new_issues"]),
                }
            )
    n = len(cases)
    strict = sum(1 for c in cases if c["detection"]["verdict"] == "strict")
    indirect = sum(1 for c in cases if c["detection"]["verdict"] == "indirect")
    return {
        "n": n,
        "categories": len(by_cat),
        "strict_detected": strict,
        "strict_rate": round(strict / n, 4) if n else 0.0,
        "indirect_detected": indirect,
        "strict_plus_indirect": strict + indirect,
        "strict_plus_indirect_rate": round((strict + indirect) / n, 4) if n else 0.0,
        "missed": n - strict - indirect,
        "by_category": list(by_cat.values()),
        "note": (
            "detection is differential against the undrifted base entry; strict = the "
            "expected rule fired; indirect = an issue appeared but not for the intended reason"
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    argp = argparse.ArgumentParser(description="E4: GB/T 7714 format-check experiment.")
    argp.add_argument("--entries", type=int, default=N_ENTRIES, help="corpus size (80-120)")
    argp.add_argument("--pages", type=int, default=2, help="fresh OpenAlex pages to fetch (per-page 50)")
    argp.add_argument("--per-page", type=int, default=50)
    argp.add_argument("--seed", type=int, default=SEED)
    argp.add_argument("--refresh", action="store_true", help="ignore cached OpenAlex pages")
    argp.add_argument("--out", type=Path, default=OUT_FILE)
    args = argp.parse_args(argv)

    if not (80 <= args.entries <= 120):
        print("[warn] --entries outside the 80-120 range requested by the task; continuing")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] acquiring OpenAlex records (pages={args.pages}, pool={POOL_FILE.name}) ...")
    works, provenance = acquire_corpus(args.entries, args.pages, args.per_page, args.refresh, args.seed)
    print(
        f"  selected={len(works)} by_type={provenance['selected_by_type']} "
        f"http={provenance['requests']['http_attempts']} "
        f"failed={provenance['requests']['http_failed']} "
        f"cache_hits={provenance['requests']['cache_hits']}"
    )

    print("[2/4] rendering GB/T entries, parsing and checking ...")
    entries = [check_entry(w, TYPE_MAP[w["type"]], i + 1) for i, w in enumerate(works)]
    metrics = summarize_corpus(entries)
    print(
        f"  type_recognition={metrics['type_code_recognition']['rate']:.3f} "
        f"required_fields={metrics['required_fields']['overall']['completeness_rate']:.3f} "
        f"errors={metrics['defects']['by_level']['error']} "
        f"clean={metrics['defects']['entries_clean']}/{metrics['n']}"
    )

    print("[3/4] building 30 controlled drifts ...")
    bases = [
        w
        for w in works
        if TYPE_MAP[w["type"]] == "J"
        and len({a for a in (w.get("authors") or [])}) >= 4
        and (w.get("volume") and w.get("issue"))
        and w.get("first_page")
        and w.get("doi")
    ][:5]
    if len(bases) < 5:
        print(f"[warn] only {len(bases)} usable drift bases found")
    cases = _build_drifts(bases)
    drift = summarize_drifts(cases)
    print(
        f"  drift n={drift['n']} strict={drift['strict_detected']} "
        f"indirect={drift['indirect_detected']} miss={drift['missed']}"
    )

    corpus_sha = hashlib.sha256(
        "\n".join(e["rendered"] for e in entries).encode("utf-8")
    ).hexdigest()
    payload = {
        "experiment": "E4",
        "title": "GB/T 7714-2025 格式合规检查（真实中文文献）",
        "generated_at": _utc_now(),
        "seed": args.seed,
        "code_snapshot": code_snapshot(),
        "provenance": provenance,
        "corpus_sha256": corpus_sha,
        "metrics": metrics,
        "drift": drift,
        "entries": entries,
        "drift_cases": cases,
        "limitations": [
            "格式检查只覆盖著录字段是否齐备、类型码是否可识别；不检查断字符、作者省略、卷期语义是否真实。",
            "100 条样本以 OpenAlex language=zh,has_doi 的真实记录渲染而来，渲染器与解析器同属本项目，可能与真实投稿格式存在系统性差异。",
            "[M] 组缺少出版地：OpenAlex 不提供出版地，属数据缺口而非规则缺陷。",
            "检出率按“差异检出”计算：只统计相对未漂移基线条目新增的问题。",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[4/4] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
