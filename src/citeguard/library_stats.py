"""Dashboard statistics for the local reference library.

The library page already lists entries and missing fields; this module turns the
same records into a JSON-serialisable snapshot for charts:

    sources distribution, year distribution, venue ranking, duplicate groups,
    completeness (by source / language / tag), tag distribution, and the
    coverage of analysis reports by library records.

Design rules:

* Missing fields are *not* errors. ``year is None``, an empty ``venue`` or an
  entry without a DOI only lowers completeness; nothing raises.
* Tags are user-maintained labels, not an automatic semantic classification.
* Language is inferred from the *title* (CJK characters vs Latin letters); this
  is a display heuristic, not language identification.
* Nothing here performs network I/O or mutates the library.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .local_library import Library, LibraryEntry

SCHEMA_VERSION = 1

# A2 (library gaps) uses the same required-field set, so the two pages agree.
REQUIRED_FIELDS = ("doi", "year", "venue", "pages", "abstract")

LANGUAGE_NOTE = "语言由题名是否含 CJK 字符推断（zh/en/unknown），不使用语言识别模型"
TAG_NOTE = "标签由用户维护，不是自动语义分类"
MISSING_NOTE = "缺失字段只影响完整度统计，不代表条目有错误"

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _entry_value(entry: Any, name: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(name)
    return getattr(entry, name, None)


def _present(entry: Any, name: str) -> bool:
    value = _entry_value(entry, name)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def language_of(title: str) -> str:
    """Display heuristic: CJK -> zh, Latin -> en, otherwise unknown."""
    text = _text(title)
    if _CJK_RE.search(text):
        return "zh"
    if _LATIN_RE.search(text):
        return "en"
    return "unknown"


def _percent(part: int, total: int) -> float:
    return round(part * 100.0 / total, 1) if total else 0.0


def _rows(entries: Sequence[Any], key_fn) -> list[dict]:
    """Group entries by a key and report counts + completeness per group."""
    buckets: dict[str, list[Any]] = {}
    for entry in entries:
        key = key_fn(entry)
        buckets.setdefault(key, []).append(entry)
    rows = []
    for key in sorted(buckets, key=lambda k: (-len(buckets[k]), str(k))):
        group = buckets[key]
        rows.append(
            {
                "key": key,
                "total": len(group),
                "complete": sum(1 for entry in group if _is_complete(entry)),
                "missing_fields": _missing_counts(group),
            }
        )
    return rows


def _missing_counts(entries: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in REQUIRED_FIELDS:
        counts[name] = sum(1 for entry in entries if not _present(entry, name))
    return counts


def _is_complete(entry: Any) -> bool:
    return all(_present(entry, name) for name in REQUIRED_FIELDS)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def field_coverage(entries: Sequence[Any]) -> dict[str, dict]:
    fields = (
        "title", "authors", "venue", "year", "volume", "issue", "pages",
        "doi", "url", "abstract", "doc_type", "source", "tags",
    )
    total = len(entries)
    return {
        name: {"present": sum(1 for entry in entries if _present(entry, name)), "pct": _percent(sum(1 for entry in entries if _present(entry, name)), total)}
        for name in fields
    }


def source_distribution(entries: Sequence[Any]) -> dict:
    total = len(entries)
    buckets: dict[str, list[Any]] = {}
    for entry in entries:
        key = _text(_entry_value(entry, "source")) or "未标注"
        buckets.setdefault(key, []).append(entry)
    rows = []
    for key in sorted(buckets, key=lambda k: (-len(buckets[k]), str(k))):
        group = buckets[key]
        rows.append(
            {
                "source": key,
                "total": len(group),
                "pct": _percent(len(group), total),
                "complete": sum(1 for entry in group if _is_complete(entry)),
                "missing_fields": _missing_counts(group),
            }
        )
    return {"total": total, "rows": rows}


def year_distribution(entries: Sequence[Any]) -> dict:
    years: list[int] = []
    missing = 0
    counts: dict[str, int] = {}
    for entry in entries:
        raw = _entry_value(entry, "year")
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
            missing += 1
            continue
        years.append(raw)
        key = str(raw)
        counts[key] = counts.get(key, 0) + 1
    total = len(entries)
    median = round(float(statistics.median(years)), 1) if years else None
    by_year = [
        {"year": key, "count": counts[key], "pct": _percent(counts[key], total)}
        for key in sorted(counts, key=lambda y: int(y))
    ]
    return {
        "total": total,
        "with_year": len(years),
        "missing": missing,
        "min": min(years) if years else None,
        "max": max(years) if years else None,
        "median": median,
        "by_year": by_year,
    }


def venue_ranking(entries: Sequence[Any], *, top: int = 8) -> dict:
    buckets: dict[str, int] = {}
    missing = 0
    for entry in entries:
        venue = _text(_entry_value(entry, "venue"))
        if not venue:
            missing += 1
            continue
        buckets[venue] = buckets.get(venue, 0) + 1
    ranked = sorted(buckets.items(), key=lambda item: (-item[1], item[0]))
    total = len(entries)
    return {
        "unique": len(buckets),
        "missing": missing,
        "top": [
            {"venue": venue, "count": count, "pct": _percent(count, total)}
            for venue, count in ranked[: max(1, int(top))]
        ],
    }


def duplicate_summary(library: Library) -> dict:
    """Summarise ``Library.find_duplicates`` without exposing full entries."""
    try:
        groups = library.find_duplicates()
    except Exception:
        groups = []
    summary = []
    for group in groups:
        entries = group.get("entries") or []
        summary.append(
            {
                "reason": group.get("reason", ""),
                "ids": list(group.get("ids") or []),
                "count": len(entries),
                "titles": [_text(entry.get("title")) for entry in entries],
                "dois": [_text(entry.get("doi")) for entry in entries],
                "years": [entry.get("year") for entry in entries],
            }
        )
    return {
        "groups": summary,
        "group_count": len(summary),
        "entries_in_groups": sum(item["count"] for item in summary),
    }


def tag_distribution(entries: Sequence[Any]) -> dict:
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    tagged = 0
    for entry in entries:
        tags = _entry_value(entry, "tags") or []
        if isinstance(tags, str):
            tags = [tags]
        cleaned = [str(tag).strip() for tag in tags if str(tag).strip()]
        if cleaned:
            tagged += 1
        for tag in cleaned:
            key = tag.casefold()
            counts[key] = counts.get(key, 0) + 1
            display.setdefault(key, tag)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], display[item[0]]))
    total = len(entries)
    return {
        "unique": len(counts),
        "tagged": tagged,
        "untagged": total - tagged,
        "total": total,
        "rows": [
            {"tag": display[key], "count": count, "pct": _percent(count, total)}
            for key, count in ranked
        ],
        "note": TAG_NOTE,
    }


def _load_report(item: Any) -> Optional[dict]:
    """Accept a report dict or a path to a report.json; None when unreadable."""
    if isinstance(item, dict):
        return item
    if isinstance(item, (str, Path)):
        try:
            data = json.loads(Path(item).read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None
    return None


def _library_hit(reference: dict) -> bool:
    verify = reference.get("verify") or {}
    if not isinstance(verify, dict):
        return False
    if verify.get("doi_status") == "local":
        return True
    sources = verify.get("sources") or []
    if isinstance(sources, list) and "local" in sources:
        return True
    best = verify.get("best") or {}
    return isinstance(best, dict) and best.get("source") == "local"


def _report_rows(reports: Sequence[Any]) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    skipped: list[str] = []
    for item in reports:
        report = _load_report(item)
        label = item if isinstance(item, str) else (
            str(item.get("job_id") or item.get("input", {}).get("name", "")) if isinstance(item, dict) else ""
        )
        if report is None:
            skipped.append(str(label))
            continue
        references = report.get("references") or []
        if not isinstance(references, list):
            skipped.append(str(label))
            continue
        hits = sum(1 for ref in references if isinstance(ref, dict) and _library_hit(ref))
        generated_at = _text(report.get("generated_at"))
        job_id = _text(report.get("job_id"))
        rows.append(
            {
                "job_id": job_id,
                "generated_at": generated_at,
                "month": generated_at[:7] if len(generated_at) >= 7 else "",
                "references": len(references),
                "library_hits": hits,
                "pct": _percent(hits, len(references)),
            }
        )
    return rows, skipped


def _coverage_trend(rows: Sequence[dict]) -> dict:
    """Aggregate coverage per report month (reports are the time axis)."""
    buckets: dict[str, dict] = {}
    for row in rows:
        month = row.get("month") or "unknown"
        bucket = buckets.setdefault(month, {"month": month, "reports": 0, "references": 0, "library_hits": 0})
        bucket["reports"] += 1
        bucket["references"] += int(row.get("references") or 0)
        bucket["library_hits"] += int(row.get("library_hits") or 0)
    trend = []
    for month in sorted(buckets):
        bucket = buckets[month]
        trend.append(
            {
                "month": month,
                "reports": bucket["reports"],
                "references": bucket["references"],
                "library_hits": bucket["library_hits"],
                "pct": _percent(bucket["library_hits"], bucket["references"]),
            }
        )
    return {
        "trend": trend,
        "time_axis": "分析报告 generated_at（不是条目入馆时间）",
    }


def entries_by_created_month(entries: Sequence[Any]) -> dict:
    """Entries' own ``created_at`` months, when the storage format has one.

    ``LibraryEntry`` has no ``created_at`` field today; the section is therefore
    explicit about being unavailable instead of guessing from years.
    """
    buckets: dict[str, int] = {}
    with_month = 0
    for entry in entries:
        raw = _text(_entry_value(entry, "created_at"))
        if len(raw) >= 7:
            buckets[raw[:7]] = buckets.get(raw[:7], 0) + 1
            with_month += 1
    return {
        "entries_with_created_at": with_month,
        "months": [{"month": month, "count": buckets[month]} for month in sorted(buckets)],
        "note": "" if with_month else "条目没有 created_at 字段；本库不提供入馆趋势",
    }


def coverage_summary(reports: Optional[Sequence[Any]], entries: Sequence[Any]) -> dict:
    if reports is None:
        return {
            "reports_provided": False,
            "reports": 0,
            "skipped": [],
            "references": 0,
            "library_hits": 0,
            "pct": 0.0,
            "by_report": [],
            "trend": [],
            **_coverage_trend([]),
            "entries": entries_by_created_month(entries),
            "note": "未传入分析报告；覆盖率需要报告列表（references[].verify 中的 local 命中）",
        }
    rows, skipped = _report_rows(reports)
    references = sum(row["references"] for row in rows)
    hits = sum(row["library_hits"] for row in rows)
    return {
        "reports_provided": True,
        "reports": len(rows),
        "skipped": skipped,
        "references": references,
        "library_hits": hits,
        "pct": _percent(hits, references),
        "by_report": rows,
        **_coverage_trend(rows),
        "entries": entries_by_created_month(entries),
        "note": "覆盖率 = 参考文献中命中本地题录库（verify.doi_status=local 或 verify.sources 含 local）的条数 / 全部参考文献",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize(
    library: Library,
    reports: Optional[Sequence[Any]] = None,
    *,
    top_venues: int = 8,
    generated_at: Optional[str] = None,
) -> dict:
    """Return a JSON-serialisable dashboard snapshot for ``library``.

    ``reports`` is optional: a sequence of parsed report dicts or paths to
    ``report.json`` files. Unreadable reports are skipped, never raised.
    """
    entries = list(getattr(library, "entries", []) or [])
    total = len(entries)
    overall_missing = _missing_counts(entries)
    by_source = _rows(entries, lambda entry: _text(_entry_value(entry, "source")) or "未标注")
    by_language = _rows(entries, lambda entry: language_of(_text(_entry_value(entry, "title"))))
    by_tag = _rows(
        entries,
        lambda entry: " / ".join(sorted({str(tag).strip().casefold() for tag in (_entry_value(entry, "tags") or []) if str(tag).strip()}))
        or "untagged",
    )
    snapshot = {
        "schema": SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "library": {
            "total": total,
            "path": str(getattr(library, "_path", "") or ""),
            "with_doi": sum(1 for entry in entries if _present(entry, "doi")),
            "with_year": sum(1 for entry in entries if _present(entry, "year")),
            "with_venue": sum(1 for entry in entries if _present(entry, "venue")),
            "with_abstract": sum(1 for entry in entries if _present(entry, "abstract")),
        },
        "sources": source_distribution(entries),
        "years": year_distribution(entries),
        "venues": venue_ranking(entries, top=top_venues),
        "duplicates": duplicate_summary(library),
        "completeness": {
            "required_fields": list(REQUIRED_FIELDS),
            "rule": "完整 = doi/year/venue/pages/abstract 均非空；缺失字段不是错误",
            "overall": {
                "total": total,
                "complete": sum(1 for entry in entries if _is_complete(entry)),
                "pct": _percent(sum(1 for entry in entries if _is_complete(entry)), total),
                "missing_fields": overall_missing,
            },
            "fields": field_coverage(entries),
            "by_source": by_source,
            "by_language": by_language,
            "by_tag": by_tag,
        },
        "tags": tag_distribution(entries),
        "coverage": coverage_summary(reports, entries),
        "notes": [
            MISSING_NOTE,
            TAG_NOTE,
            LANGUAGE_NOTE,
        ],
    }
    return snapshot


def save_snapshot(snapshot: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _project_root() -> Path:
    # src/citeguard/library_stats.py -> repo root
    return Path(__file__).resolve().parents[2]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the A3 library dashboard snapshot")
    parser.add_argument("--library", default=str(_project_root() / "data" / "library" / "library.json"))
    parser.add_argument("--reports", nargs="*", default=None, help="report.json paths (default: none)")
    parser.add_argument(
        "--reports-glob",
        default="",
        help="when --reports is omitted: glob under the project root, e.g. data/jobs/*/report.json",
    )
    parser.add_argument(
        "--out",
        default=str(_project_root() / "data" / "experiments" / "opt_a3_library_dashboard_2026-11-27.json"),
    )
    parser.add_argument("--top-venues", type=int, default=8)
    args = parser.parse_args(list(argv) if argv is not None else None)

    library = Library.load(args.library)
    reports: Optional[list] = None
    if args.reports:
        reports = list(args.reports)
    elif args.reports_glob:
        reports = sorted(str(path) for path in _project_root().glob(args.reports_glob))
    snapshot = summarize(library, reports, top_venues=args.top_venues)
    save_snapshot(snapshot, args.out)
    print(
        "library={} complete={}/{} sources={} years={} duplicates={} coverage={}%".format(
            snapshot["library"]["total"],
            snapshot["completeness"]["overall"]["complete"],
            snapshot["library"]["total"],
            len(snapshot["sources"]["rows"]),
            len(snapshot["years"]["by_year"]),
            snapshot["duplicates"]["group_count"],
            snapshot["coverage"]["pct"],
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
