"""CiteGuard-CN web application (FastAPI + Jinja2).

Run (from the citeguard/ directory):
    PYTHONPATH=src uvicorn web.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import os
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import re
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent          # citeguard/web
ROOT = BASE.parent                               # citeguard
sys.path.insert(0, str(ROOT / "src"))

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from citeguard import aggregate as aggregate_mod  # noqa: E402
from citeguard import compare  # noqa: E402
from citeguard import config  # noqa: E402
from citeguard import discover  # noqa: E402
from citeguard import evidence_map  # noqa: E402
from citeguard import figure_check  # noqa: E402
from citeguard import fix as fix_mod  # noqa: E402
from citeguard import triage  # noqa: E402
from citeguard.abstract_enrich import MAX_ENRICH_PER_REQUEST, enrich_missing  # noqa: E402
from citeguard.jobs import manager  # noqa: E402
from citeguard.local_library import Library, LibraryEntry, LibraryError, parse_library_text  # noqa: E402
from citeguard.pdf_extract import (  # noqa: E402
    SUPPORTED_SUFFIXES,
    extract_page_text,
    extract_text,
    caption_kind_from_claim,
    figure_number_from_claim,
    find_figure_page,
    render_page_png,
)
from citeguard.pipeline import run_job  # noqa: E402
from citeguard.report import render_reference_list  # noqa: E402
from citeguard import support  # noqa: E402

UPLOAD_DIR = config.DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_SUFFIXES = set(SUPPORTED_SUFFIXES) | {".doc"}
MAX_UPLOAD_BYTES = config.MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_MAX_AGE_SECONDS = 24 * 3600


def _cleanup_uploads(max_age_seconds: int = UPLOAD_MAX_AGE_SECONDS) -> None:
    """Remove uploaded copies left behind by crashed/aborted jobs."""
    now = time.time()
    for path in UPLOAD_DIR.glob("*"):
        try:
            if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _cleanup_compare(max_age_seconds: int = UPLOAD_MAX_AGE_SECONDS) -> None:
    """Remove comparison results left over from old jobs."""
    now = time.time()
    try:
        paths = list(_compare_dir().glob("*.json"))
    except OSError:
        return
    for path in paths:
        try:
            if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _compare_dir() -> Path:
    folder = config.DATA_DIR / "compare"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup hygiene: old job records/reports and stale uploads.
    manager.cleanup()
    manager.mark_stale_as_interrupted()
    _cleanup_uploads()
    _cleanup_compare()
    yield


app = FastAPI(title="引证卫士 CiteGuard-CN", version="1.7.7", lifespan=lifespan)
app.state.offline = config.OFFLINE
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve the SVG icon at the legacy path so browsers stop logging 404."""
    from fastapi.responses import FileResponse

    return FileResponse(BASE / "static" / "img" / "favicon.svg", media_type="image/svg+xml")
templates = Jinja2Templates(directory=str(BASE / "templates"))


# --- Optional access token + per-IP rate limit (public demo hardening) ---
_rate_buckets: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _supplied_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    return (
        request.headers.get("x-access-token", "").strip()
        or bearer
        or request.query_params.get("token", "").strip()
        or request.cookies.get("cg_token", "").strip()
    )


def _rate_limited(request: Request) -> bool:
    limit = config.RATE_LIMIT_PER_MIN
    if limit <= 0 or request.method in {"GET", "HEAD", "OPTIONS"}:
        return False
    ip = _client_ip(request)
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets.setdefault(ip, [])
        cutoff = now - 60.0
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)
        if len(bucket) >= limit:
            return True
        bucket.append(now)
    return False


@app.middleware("http")
async def _guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static/") or path in {"/api/health", "/favicon.ico"}:
        return await call_next(request)
    expected = config.ACCESS_TOKEN
    supplied = _supplied_token(request)
    if expected and supplied != expected:
        return JSONResponse(
            {"error": "unauthorized", "message": "需要访问令牌（?token= 或 X-Access-Token）"},
            status_code=401,
        )
    if path.startswith("/api/") and _rate_limited(request):
        return JSONResponse(
            {"error": "rate_limited", "message": "请求过于频繁，请稍后再试"},
            status_code=429,
            headers={"Retry-After": "60"},
        )
    response = await call_next(request)
    if expected and request.query_params.get("token") == expected:
        response.set_cookie("cg_token", expected, httponly=True, samesite="lax", max_age=86400)
    return response


def _report_path(job_id: str) -> Path:
    return config.DATA_DIR / "jobs" / job_id / "report.json"


def _load_report(job_id: str) -> dict | None:
    p = _report_path(job_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _compare_reports(a: dict, b: dict) -> dict:
    """Compare two saved reports: headline deltas plus per-reference status changes.

    Reports are only comparable positionally when both came from the same
    manuscript.  We still show the positional diff because that is exactly the
    "I fixed four citations, did the rest regress?" question the history page is
    for, and label it as positional so nobody mistakes it for a title match.
    """
    sa = a.get("stats") or {}
    sb = b.get("stats") or {}
    keys = ["total", "Exact", "Minor", "Major", "Unverified", "avg_compliance", "risk_index"]
    stats = {}
    for k in keys:
        va = sa.get(k)
        vb = sb.get(k)
        if isinstance(va, (int, float)) or isinstance(vb, (int, float)):
            stats[k] = {"a": va, "b": vb, "delta": (vb or 0) - (va or 0)}
    ra = a.get("references") or []
    rb = b.get("references") or []
    changes = []
    for i in range(min(len(ra), len(rb))):
        va = (ra[i].get("verify") or {}).get("status")
        vb = (rb[i].get("verify") or {}).get("status")
        if va != vb:
            parsed = rb[i].get("parsed") or ra[i].get("parsed") or {}
            changes.append(
                {
                    "index": i + 1,
                    "title": (parsed.get("title") or parsed.get("raw") or "")[:120],
                    "from": va,
                    "to": vb,
                }
            )
    return {
        "a": {"file": a.get("input"), "generated_at": a.get("generated_at")},
        "b": {"file": b.get("input"), "generated_at": b.get("generated_at")},
        "stats": stats,
        "positional": True,
        "changed": len(changes),
        "changes": changes[:100],
        "total_delta": len(rb) - len(ra),
    }


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    """Marketing landing page; the functional workspace lives at /workspace."""
    return templates.TemplateResponse(request, "landing.html", {"active": "landing"})


@app.get("/workspace", response_class=HTMLResponse)
def index(request: Request):
    library = Library.load(config.LIBRARY_FILE)
    recent = manager.recent(6)
    for job in recent:
        job["has_report"] = _report_path(job["id"]).exists()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"recent": recent, "active": "home", "library_count": len(library),
         "vl_available": figure_check.available(), "compare_available": compare.available()},
    )


@app.get("/library", response_class=HTMLResponse)
def library_page(request: Request):
    library = Library.load(config.LIBRARY_FILE)
    sources: dict[str, int] = {}
    with_abstract = 0
    with_doi = 0
    with_url = 0
    years: list[int] = []
    year_counts: dict[int, int] = {}
    venues: dict[str, int] = {}
    for entry in library.entries:
        sources[entry.source] = sources.get(entry.source, 0) + 1
        if (entry.abstract or "").strip():
            with_abstract += 1
        if (entry.doi or "").strip():
            with_doi += 1
        if (entry.url or "").strip():
            with_url += 1
        if entry.year:
            years.append(entry.year)
            year_counts[entry.year] = year_counts.get(entry.year, 0) + 1
        if (entry.venue or "").strip():
            venues[entry.venue] = venues.get(entry.venue, 0) + 1
    total = max(len(library), 1)
    coverage = {
        "doi": with_doi,
        "url": with_url,
        "doi_pct": round(100 * with_doi / total, 1),
        "abstract_pct": round(100 * with_abstract / total, 1),
        "year_range": f"{min(years)}–{max(years)}" if years else "—",
        "years": len(years),
        "top_venues": sorted(venues.items(), key=lambda kv: -kv[1])[:6],
        "venues": len(venues),
    }
    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "active": "library",
            "count": len(library),
            "with_abstract": with_abstract,
            "sources": sorted(sources.items()),
            "coverage": coverage,
            "year_hist": [[year, year_counts[year]] for year in sorted(year_counts)],
            "sample": [entry.to_dict() for entry in library.entries[:20]],
            "path": str(config.LIBRARY_FILE),
        },
    )


@app.post("/api/library/import")
def library_import(file: UploadFile = File(...)):
    filename = file.filename or "library.ris"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".ris", ".bib", ".json", ".csl", ".txt", ".enw"}:
        raise HTTPException(status_code=400, detail="仅支持 RIS / BibTeX / EndNote / CSL-JSON / 纯文本题录")
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"文件超过 {config.MAX_UPLOAD_MB} MB 上限")
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = raw.decode("utf-8", errors="replace")
    entries = parse_library_text(text, filename)
    if not entries:
        raise HTTPException(status_code=400, detail="没有解析到任何题录，请检查导出格式")
    library = Library.load(config.LIBRARY_FILE)
    before = len(library)
    library.add(entries)
    library.save(config.LIBRARY_FILE)
    added = len(library) - before
    imported_no_abstract = sum(1 for e in entries if not (e.abstract or "").strip())
    return {
        "imported": len(entries),
        "added": added,
        "skipped": len(entries) - added,
        "before": before,
        "count": len(library),
        "with_abstract": sum(1 for e in library.entries if (e.abstract or "").strip()),
        "imported_no_abstract": imported_no_abstract,
        "format_guess": entries[0].source if entries else "",
    }


@app.post("/api/library/demo")
def library_demo():
    """Load the bundled offline demo library in one click.

    The demo pack contains 10 real, openly available references; a conference
    laptop with no network can still walk the whole "library match + field
    check" path after one click.
    """
    path = config.PROJECT_ROOT / "samples" / "offline_demo" / "library.ris"
    if not path.exists():
        raise HTTPException(status_code=404, detail="演示题录包不存在，请检查 samples/offline_demo/")
    entries = parse_library_text(path.read_text(encoding="utf-8-sig"), "library.ris")
    if not entries:
        raise HTTPException(status_code=400, detail="演示题录包解析失败")
    library = Library.load(config.LIBRARY_FILE)
    before = len(library)
    library.add(entries)
    library.save(config.LIBRARY_FILE)
    return {
        "imported": len(entries),
        "added": len(library) - before,
        "before": before,
        "count": len(library),
        "with_abstract": sum(1 for e in library.entries if (e.abstract or "").strip()),
    }


@app.post("/api/library/add")
def library_add(body: dict = Body(...)):
    """Append one manually-confirmed record (the Chinese-paper workflow).

    Chinese journals are usually absent from OpenAlex/Crossref, so the honest
    path is: human checks CNKI/万方/百度学术, then stores the confirmed metadata
    here once; later runs verify against the local library automatically.
    """
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="缺少题名")
    authors = body.get("authors") or []
    if isinstance(authors, str):
        authors = [a for a in re.split(r"[;；、]", authors) if a.strip()]
    year = body.get("year")
    try:
        year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        year = None
    entry = LibraryEntry(
        title=title,
        authors=[str(a).strip() for a in authors if str(a).strip()],
        venue=str(body.get("venue") or "").strip(),
        year=year,
        doi=str(body.get("doi") or "").strip(),
        url=str(body.get("url") or "").strip(),
        abstract=str(body.get("abstract") or "").strip(),
        source="manual",
    )
    library = Library.load(config.LIBRARY_FILE)
    before = len(library)
    library.add([entry])
    if len(library) == before:
        return {"added": 0, "count": before, "message": "题录库中已有同题名记录"}
    library.save(config.LIBRARY_FILE)
    return {"added": 1, "count": len(library), "title": entry.title}


@app.post("/api/library/bulk")
def library_bulk(body: dict = Body(...)):
    """Append many manually-confirmed records at once (one per line).

    The single-record endpoint is for the report's "加入题录库" button; this
    one is for the common Chinese-paper workflow where a user already has a
    plain reference list and wants to seed the library in one paste.
    """
    from citeguard.reference_parser import parse_reference

    text = str(body.get("text") or "")
    library = Library.load(config.LIBRARY_FILE)
    before = len(library)
    entries: list[LibraryEntry] = []
    skipped: list[str] = []
    for line in re.split(r"\r?\n", text):
        line = line.strip()
        if len(line) < 8:
            continue
        ref = parse_reference(line)
        title = (ref.title or "").strip()
        if not title and ref.doi:
            title = ref.doi
        if not title:
            skipped.append(line[:80])
            continue
        entries.append(
            LibraryEntry(
                title=title,
                authors=[a for a in (ref.authors or []) if a.strip()],
                venue=(ref.venue or "").strip(),
                year=ref.year,
                doi=(ref.doi or "").strip(),
                url=(ref.url or "").strip(),
                source="manual-bulk",
            )
        )
    if entries:
        library.add(entries)
        library.save(config.LIBRARY_FILE)
    return {
        "parsed": len(entries) + len(skipped),
        "added": len(library) - before,
        "skipped": len(skipped),
        "samples": skipped[:5],
        "count": len(library),
    }


@app.post("/api/library/clear")
def library_clear():
    Library().save(config.LIBRARY_FILE)
    return {"count": 0}


@app.get("/api/library/suggest")
def library_suggest(title: str = "", year: int | None = None):
    """Look up a title in OpenAlex/Crossref so the user can add it in one click."""
    title = (title or "").strip()
    if len(title) < 4:
        raise HTTPException(status_code=400, detail="请输入至少 4 个字的题名")
    from citeguard.metadata_verify import (
        Reference,
        _candidate_to_dict,
        _title_candidates,
        norm_title,
        title_sim,
    )

    ref = Reference(raw=title, title=title, year=year)
    try:
        cands = _title_candidates(ref)
    except Exception:
        cands = []
    lib = Library.load(config.LIBRARY_FILE)
    have = {norm_title(e.title) for e in lib.entries}
    have_dois = {(e.doi or "").strip().lower() for e in lib.entries if e.doi}
    seen: set[str] = set()
    out: list[dict] = []
    for cand in cands:
        sim = title_sim(title, cand.title or "")
        if sim < 0.5:
            continue
        key = norm_title(cand.title or "")
        doi = (cand.doi or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        item = _candidate_to_dict(cand)
        item["sim"] = round(sim, 3)
        item["cited_by"] = int((cand.raw or {}).get("cited_by_count") or 0)
        item["already"] = key in have or bool(doi and doi in have_dois)
        out.append(item)
    out.sort(key=lambda item: (round(item["sim"], 2), item["cited_by"]), reverse=True)
    return {"query": title, "count": len(out[:6]), "candidates": out[:6]}


@app.get("/api/report/{job_id}/replacement")
def report_replacement(job_id: str, index: int, q: str = ""):
    """Suggest candidate references for a claim the current citation cannot support.

    Candidates come from an OpenAlex full-text search on the citation context; they
    are leads to check, not a claim that any candidate actually supports the sentence.
    """
    from citeguard.format_gbt import format_from_candidate
    from citeguard.metadata_verify import Reference, norm_title, search_openalex

    report = _load_report(job_id)
    refs = report.get("references") or []
    if not (1 <= index <= len(refs)):
        raise HTTPException(status_code=404, detail="没有这一条参考文献")
    item = refs[index - 1]
    parsed = item.get("parsed") or {}
    if not (q or "").strip():
        cited = item.get("cited_in") or []
        if cited:
            q = cited[0].get("sentence") or ""
        elif item.get("support"):
            q = (item["support"] or {}).get("claim") or ""
        if not q:
            q = parsed.get("title") or ""
    q = (q or "").strip()
    if len(q) < 4:
        raise HTTPException(status_code=400, detail="需要引用句或题名才能检索候选")
    query = q[:300]
    try:
        cands = search_openalex(query, limit=10)
    except Exception:
        cands = []
    have = {norm_title((r.get("parsed") or {}).get("title") or "") for r in refs}
    out: list[dict] = []
    for cand in cands:
        key = norm_title(cand.title or "")
        if not key or key in have:
            continue
        ref = Reference(
            raw=cand.title or "",
            title=cand.title or "",
            authors=list(cand.authors or []),
            year=cand.year,
            venue=cand.venue or "",
            doi=cand.doi or "",
            doc_type="J",
        )
        out.append(
            {
                "title": cand.title,
                "year": cand.year,
                "venue": cand.venue,
                "doi": cand.doi,
                "source": cand.source,
                "entry": format_from_candidate(ref, cand),
            }
        )
        if len(out) >= 3:
            break
    return {
        "index": index,
        "query": query,
        "count": len(out),
        "candidates": out,
        "note": "检索线索，不代表该文献一定支持这句话；请打开摘要核对后再替换。",
    }


@app.get("/api/library")
def library_api(limit: int = 500, offset: int = 0):
    """List library entries for the management table (indexes are stable)."""
    library = Library.load(config.LIBRARY_FILE)
    total = len(library)
    limit = max(1, min(int(limit or 500), 2000))
    offset = max(0, int(offset or 0))
    window = library.entries[offset : offset + limit]
    entries = []
    for i, entry in enumerate(window, start=offset):
        item = entry.to_dict()
        item["index"] = i
        entries.append(item)
    return {
        "count": total,
        "with_abstract": sum(1 for e in library.entries if (e.abstract or "").strip()),
        "missing_abstract": sum(1 for e in library.entries if not (e.abstract or "").strip()),
        "offset": offset,
        "entries": entries,
        "truncated": offset + len(entries) < total,
    }


class LibraryTagsUpdate(BaseModel):
    mode: str = "replace"
    tags: list[str] = []


class LibraryDuplicateMerge(BaseModel):
    keep_id: int
    drop_ids: list[int] = []


@app.get("/api/library/duplicates")
def library_duplicates():
    """Group likely duplicates; never deletes anything by itself."""
    library = Library.load(config.LIBRARY_FILE)
    groups = []
    for group in library.find_duplicates():
        groups.append(
            {
                "ids": group["ids"],
                "reason": group["reason"],
                "entries": group["entries"],
            }
        )
    return {"count": len(groups), "groups": groups}


@app.post("/api/library/duplicates/merge")
def library_duplicates_merge(payload: LibraryDuplicateMerge):
    """Merge duplicates after the user confirms; source work is left in place."""
    library = Library.load(config.LIBRARY_FILE)
    try:
        merged = library.merge_duplicates(payload.keep_id, payload.drop_ids)
    except LibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    kept = library.entries[payload.keep_id] if 0 <= payload.keep_id < len(library) else None
    return {
        "merged": merged,
        "count": len(library),
        "kept": kept.to_dict() if kept else None,
    }


@app.post("/api/library/{index}/tags")
def library_tags(index: int, payload: LibraryTagsUpdate):
    """Replace/add/remove tags on one entry (0-based index, same as DELETE)."""
    library = Library.load(config.LIBRARY_FILE)
    if index < 0 or index >= len(library):
        raise HTTPException(status_code=404, detail="题录不存在（列表可能已刷新，请重试）")
    mode = (payload.mode or "replace").strip().lower()
    try:
        if mode == "replace":
            entry = library.set_tags(index, payload.tags)
        elif mode == "add":
            entry = library.add_tags(index, payload.tags)
        elif mode == "remove":
            entry = library.remove_tags(index, payload.tags)
        else:
            raise HTTPException(status_code=400, detail="mode 必须是 replace/add/remove")
    except LibraryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    library.save(config.LIBRARY_FILE)
    return {"index": index, "tags": entry.tags, "count": len(library)}


@app.delete("/api/library/{index}")
def library_delete(index: int):
    """Remove one record by its list index (the UI confirms before calling)."""
    library = Library.load(config.LIBRARY_FILE)
    if index < 0 or index >= len(library):
        raise HTTPException(status_code=404, detail="题录不存在（列表可能已刷新，请重试）")
    removed = library.entries.pop(index)
    library.save(config.LIBRARY_FILE)
    return {
        "removed": removed.title,
        "count": len(library),
        "with_abstract": sum(1 for e in library.entries if (e.abstract or "").strip()),
    }


@app.post("/api/library/enrich")
def library_enrich(limit: int = 10):
    """Opt-in: fill missing abstracts from OpenAlex / Crossref public metadata.

    Runs in the request thread but is capped (``MAX_ENRICH_PER_REQUEST``) and the
    UI calls it in small batches so one click cannot hang on a huge library.
    """
    library = Library.load(config.LIBRARY_FILE)
    if not library:
        raise HTTPException(status_code=400, detail="题录库为空，先导入题录")
    missing_before = sum(1 for e in library.entries if not (e.abstract or "").strip())
    if not missing_before:
        return {"tried": 0, "enriched": 0, "remaining": 0, "total_missing": 0, "details": []}
    limit = max(1, min(int(limit or 10), MAX_ENRICH_PER_REQUEST))
    result = enrich_missing(library, limit=limit)
    library.save(config.LIBRARY_FILE)
    result["with_abstract"] = sum(1 for e in library.entries if (e.abstract or "").strip())
    return result


@app.get("/api/library/export")
def library_export(format: str = "bibtex"):
    from citeguard.local_library import to_bibtex, to_ris

    library = Library.load(config.LIBRARY_FILE)
    if not library:
        raise HTTPException(status_code=404, detail="题录库为空")
    if format == "ris":
        content, media, ext = to_ris(library), "application/x-research-info-systems", "ris"
    elif format in {"bibtex", "bib"}:
        content, media, ext = to_bibtex(library), "application/x-bibtex", "bib"
    else:
        raise HTTPException(status_code=400, detail="format must be bibtex or ris")
    return Response(
        content=content.encode("utf-8"),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="citeguard-library.{ext}"'},
    )


def _save_upload(file: UploadFile, dst: Path) -> int:
    """Stream one upload to ``dst`` under the size cap; return bytes written."""
    written = 0
    with dst.open("wb") as fh:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件超过 {config.MAX_UPLOAD_MB} MB 上限，请压缩或拆分后再传",
                )
            fh.write(chunk)
    if written == 0:
        raise HTTPException(status_code=400, detail="上传的文件是空的")
    return written


@app.post("/api/analyze")
def analyze(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    support_max: int | None = Form(default=None),
    figures: bool = Form(default=False),
):
    if file is None and not text:
        raise HTTPException(status_code=400, detail="请上传文件或粘贴文本")
    suffix = ""
    if file is not None:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400, detail="仅支持 PDF / DOCX / TXT / MD（旧版 .doc 请先另存为 .docx）"
            )
    filename = file.filename if file is not None else "pasted-text.txt"
    job = manager.create(filename=filename)
    if file is not None:
        dst = UPLOAD_DIR / f"{job['id']}{suffix}"
        try:
            _save_upload(file, dst)
        except HTTPException:
            dst.unlink(missing_ok=True)
            manager.discard(job["id"])
            raise
        manager.submit(job["id"], run_job, file_path=str(dst), support_max=support_max, figures=figures)
    else:
        manager.submit(job["id"], run_job, text=text, support_max=support_max, figures=figures)
    return JSONResponse({"job_id": job["id"]}, status_code=202)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    """Server-Sent Events stream of a job's progress (one JSON object per event)."""
    if manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    async def event_gen():
        last = None
        while True:
            if await request.is_disconnected():
                break
            job = manager.get(job_id) or {}
            data = {
                "id": job_id,
                "status": str(job.get("status") or ""),
                "progress": int(job.get("progress") or 0),
                "stage": str(job.get("stage") or ""),
                "error": str(job.get("error") or ""),
            }
            if data != last:
                yield "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"
                last = data
            if data["status"] in {"done", "error", "cancelled"}:
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.post("/api/jobs/{job_id}/rerun")
def rerun_job(job_id: str):
    """Re-run an interrupted/failed job from its retained extracted text."""
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    out_dir = config.DATA_DIR / "jobs" / job_id
    src = out_dir / "input.txt"
    if not src.exists():
        raise HTTPException(
            status_code=409,
            detail="这次任务的原文已清理（成功任务不保留），请重新上传文件",
        )
    try:
        text = src.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=409, detail="保留的原文读取失败，请重新上传")
    if not text.strip():
        raise HTTPException(status_code=409, detail="保留的原文为空，请重新上传")
    opts: dict = {}
    try:
        opts = json.loads((out_dir / "options.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    new_job = manager.create(filename=job.get("filename") or "重新运行")
    manager.submit(
        new_job["id"],
        run_job,
        text=text,
        support_max=opts.get("support_max"),
        figures=bool(opts.get("figures")),
    )
    return JSONResponse(
        {"job_id": new_job["id"], "rerun_of": job_id}, status_code=202
    )


@app.get("/api/report/{job_id}")
def report_json(job_id: str):
    report = _load_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not ready")
    return report


@app.get("/api/aggregate")
def aggregate_reports(ids: str = ""):
    """Aggregate finished reports by job id (max 50, order preserved)."""
    wanted = [i.strip() for i in ids.split(",") if i.strip()]
    wanted = list(dict.fromkeys(wanted))[:50]
    if not wanted:
        raise HTTPException(status_code=400, detail="请提供至少一份报告（ids=a,b）")
    reports = []
    missing = []
    for job_id in wanted:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
            missing.append(job_id)
            continue
        report = _load_report(job_id)
        if report is None:
            missing.append(job_id)
            continue
        job = manager.get(job_id) or {}
        name = job.get("filename") or (report.get("input") or {}).get("name") or job_id
        reports.append((job_id, name, report))
    if not reports:
        raise HTTPException(status_code=404, detail="所选任务暂无已完成的报告")
    seen = {}
    unique = []
    duplicates = []
    for job_id, name, report in reports:
        if name in seen:
            duplicates.append(job_id)
            continue
        seen[name] = job_id
        unique.append((job_id, name, report))
    data = aggregate_mod.aggregate(unique)
    data["missing"] = missing
    data["duplicates"] = duplicates
    return data


@app.get("/api/aggregate.csv")
def aggregate_csv(ids: str = ""):
    """CSV of the cohort view (UTF-8 BOM for Excel)."""
    data = aggregate_reports(ids)
    body = aggregate_mod.to_csv(data)
    return Response(
        content="\ufeff" + body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="citeguard-aggregate.csv"'},
    )


@app.get("/api/report/{job_id}/diff")
def report_diff(job_id: str, against: str = ""):
    """与另一份报告做字段级复检 diff（修正前 vs 修正后）。"""
    new = _load_report(job_id)
    if new is None:
        raise HTTPException(status_code=404, detail="report not ready")
    if not against:
        raise HTTPException(status_code=400, detail="缺少 against 参数（旧任务号）")
    old = _load_report(against)
    if old is None:
        raise HTTPException(status_code=404, detail="旧报告不存在")
    from citeguard.diff import diff_reports

    result = diff_reports(old, new)
    resolved = [int(i["index"]) for i in result["items"] if i.get("kind") == "resolved"]
    result["auto_closed"] = triage.auto_mark_fixed(job_id, resolved)
    return result


class TriageUpdate(BaseModel):
    index: int
    state: str
    note: str = ""


@app.get("/api/report/{job_id}/triage")
def get_triage(job_id: str):
    if _load_report(job_id) is None:
        raise HTTPException(status_code=404, detail="report not ready")
    return triage.load(job_id)


@app.post("/api/report/{job_id}/triage")
def update_triage(job_id: str, body: TriageUpdate):
    if _load_report(job_id) is None:
        raise HTTPException(status_code=404, detail="report not ready")
    try:
        return triage.set_state(job_id, body.index, body.state, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 修复闭环（C1）：预览 -> 应用 -> 撤销，report.json 始终只读
# ---------------------------------------------------------------------------

_REPAIR_LOCKS: dict[str, threading.Lock] = {}
_REPAIR_LOCKS_GUARD = threading.Lock()


def _repair_lock(job_id: str) -> threading.Lock:
    with _REPAIR_LOCKS_GUARD:
        return _REPAIR_LOCKS.setdefault(job_id, threading.Lock())


def _repair_paths(job_id: str) -> tuple[Path, Path]:
    folder = config.DATA_DIR / "jobs" / job_id
    return folder / "report.fixed.json", folder / "repair.json"


def _read_json_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_active_report(job_id: str) -> dict | None:
    fixed_path, _ = _repair_paths(job_id)
    fixed = _read_json_file(fixed_path)
    return fixed or _load_report(job_id)


def _repair_error(code: str, message: str, status: int = 400):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def _parse_indexes(raw: str) -> list[int] | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    values: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            _repair_error("bad_request", "indexes 里含有空值，请用 1,3,5 形式")
        try:
            values.append(int(part))
        except ValueError:
            _repair_error("bad_request", f"条目序号不是整数：{part}")
    return values


def _report_fingerprint(report: dict) -> str:
    # build_patch([]) 只计算 fingerprint，不产生任何操作。
    return str(fix_mod.build_patch(report, []).get("report_fingerprint") or "")


def _undo_info(job_id: str) -> dict:
    """暴露最近一次修复的撤销窗口（TTL 30 分钟）。"""
    base = _load_report(job_id)
    _, store_path = _repair_paths(job_id)
    store = _read_json_file(store_path)
    info = {
        "available": False,
        "patch_id": "",
        "applied_at": "",
        "expires_at": "",
        "indexes": [],
        "reason": "",
    }
    if not store or base is None:
        return info
    patch = store.get("patch") if isinstance(store.get("patch"), dict) else None
    if not patch:
        return info
    expires_at = str(store.get("expires_at") or "")
    info.update(
        {
            "patch_id": str(patch.get("patch_id") or ""),
            "applied_at": str(store.get("applied_at") or ""),
            "expires_at": expires_at,
            "indexes": patch.get("indexes") or [],
        }
    )
    try:
        expires = datetime.fromisoformat(expires_at)
    except ValueError:
        info["reason"] = "撤销窗口记录损坏；可再次修复覆盖。"
        return info
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) >= expires:
        info["reason"] = "撤销窗口已结束（30 分钟）。可再次修复并在窗口内撤销。"
        return info
    if patch.get("report_fingerprint") != _report_fingerprint(base):
        info["reason"] = "原始报告已变化，不能再撤销这一次修复。"
        return info
    info["available"] = True
    return info


class RepairApply(BaseModel):
    indexes: Optional[list[int]] = None
    patch_id: Optional[str] = None


class RepairUndo(BaseModel):
    patch_id: Optional[str] = None
    indexes: Optional[list[int]] = None


@app.get("/api/report/{job_id}/repair/state")
def repair_get_state(job_id: str):
    if _load_report(job_id) is None:
        raise HTTPException(status_code=404, detail="report not ready")
    active = _load_active_report(job_id)
    return {**fix_mod.repair_state(active), "undo": _undo_info(job_id)}


@app.get("/api/report/{job_id}/repair/preview")
def repair_preview(job_id: str, indexes: str = ""):
    base = _load_report(job_id)
    if base is None:
        raise HTTPException(status_code=404, detail="report not ready")
    active = _load_active_report(job_id)
    selected = _parse_indexes(indexes)
    try:
        patch = fix_mod.build_patch(active, selected)
    except ValueError as exc:
        _repair_error("invalid_index", str(exc))
    patch["state"] = fix_mod.repair_state(active)
    patch["undo"] = _undo_info(job_id)
    return patch


@app.post("/api/report/{job_id}/repair/apply")
def repair_apply(job_id: str, body: RepairApply):
    if _load_report(job_id) is None:
        raise HTTPException(status_code=404, detail="report not ready")
    if body.indexes is not None and not body.indexes:
        _repair_error("bad_request", "indexes 不能是空列表；不传表示全部条目")
    with _repair_lock(job_id):
        active = _load_active_report(job_id)
        fixed_path, store_path = _repair_paths(job_id)
        store = _read_json_file(store_path)
        if body.patch_id and store:
            stored_patch = store.get("patch") or {}
            if stored_patch.get("patch_id") == body.patch_id:
                return {
                    "schema": fix_mod.REPAIR_SCHEMA,
                    "applied": 0,
                    "already_applied": True,
                    "state": fix_mod.repair_state(active),
                    "undo": _undo_info(job_id),
                    "message": "该修复已经应用，无需重复点击。",
                }
        try:
            patch = fix_mod.build_patch(active, body.indexes)
        except ValueError as exc:
            _repair_error("invalid_index", str(exc))
        if body.patch_id and patch.get("patch_id") != body.patch_id:
            _repair_error(
                "stale_patch",
                "修复预览已过期（报告或条目已变化），请重新预览。",
                409,
            )
        if not patch["ops"]:
            return {
                "schema": fix_mod.REPAIR_SCHEMA,
                "applied": 0,
                "already_applied": True,
                "state": fix_mod.repair_state(active),
                "undo": _undo_info(job_id),
                "message": "没有需要修复的条目。",
            }
        try:
            repaired = fix_mod.apply_patch(active, patch)
        except ValueError as exc:
            _repair_error("stale_patch", str(exc), 409)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=fix_mod.REPAIR_UNDO_TTL_SECONDS)
        record = {
            "schema": "citeguard.repair_store/1",
            "job_id": job_id,
            "applied_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "indexes": patch["indexes"],
            "patch": patch,
        }
        previous_fixed = fixed_path.read_text(encoding="utf-8") if fixed_path.exists() else None
        try:
            _write_json_atomic(fixed_path, repaired)
            _write_json_atomic(store_path, record)
        except OSError as exc:
            if previous_fixed is None:
                fixed_path.unlink(missing_ok=True)
            else:
                fixed_path.write_text(previous_fixed, encoding="utf-8")
            _repair_error("bad_request", f"写入修复视图失败：{exc}", 500)
        return {
            "schema": fix_mod.REPAIR_SCHEMA,
            "applied": len(patch["ops"]),
            "already_applied": False,
            "patch_id": patch["patch_id"],
            "indexes": [op["index"] for op in patch["ops"]],
            "state": fix_mod.repair_state(repaired),
            "undo": _undo_info(job_id),
            "message": f"已修复 {len(patch['ops'])} 条，30 分钟内可撤销。",
        }


@app.post("/api/report/{job_id}/repair/undo")
def repair_undo(job_id: str, body: RepairUndo):
    if _load_report(job_id) is None:
        raise HTTPException(status_code=404, detail="report not ready")
    with _repair_lock(job_id):
        active = _load_active_report(job_id)
        fixed_path, store_path = _repair_paths(job_id)
        store = _read_json_file(store_path)
        if not store or not isinstance(store.get("patch"), dict):
            return {
                "schema": fix_mod.REPAIR_STATE_SCHEMA,
                "undone": 0,
                "already_undone": True,
                "state": fix_mod.repair_state(active),
                "undo": _undo_info(job_id),
                "message": "没有可撤销的修复。",
            }
        patch = store["patch"]
        if body.patch_id and patch.get("patch_id") != body.patch_id:
            _repair_error("stale_patch", "要撤销的补丁不是最近一次修复。", 409)
        try:
            expires = datetime.fromisoformat(str(store.get("expires_at") or ""))
        except ValueError:
            _repair_error("undo_expired", "撤销窗口记录损坏，无法撤销。", 409)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= expires:
            _repair_error("undo_expired", "撤销窗口已结束（30 分钟），无法撤销。", 409)
        before_fixed = fix_mod.repair_state(active)["fixed"]
        try:
            restored = fix_mod.undo_patch(active, patch, body.indexes)
        except ValueError as exc:
            _repair_error("stale_patch", str(exc), 409)
        after_state = fix_mod.repair_state(restored)
        try:
            if after_state["fixed"] == 0:
                fixed_path.unlink(missing_ok=True)
                store_path.unlink(missing_ok=True)
            else:
                _write_json_atomic(fixed_path, restored)
        except OSError as exc:
            _repair_error("bad_request", f"写入撤销结果失败：{exc}", 500)
        return {
            "schema": fix_mod.REPAIR_STATE_SCHEMA,
            "undone": before_fixed - after_state["fixed"],
            "already_undone": False,
            "state": after_state,
            "undo": _undo_info(job_id),
            "message": "已撤销本次修复，条目已恢复原文。",
        }


def _page_dir(job_id: str) -> Path:
    return config.DATA_DIR / "jobs" / job_id / "pages"


@app.get("/api/report/{job_id}/page/{page}.png")
def report_page_png(job_id: str, page: int):
    p = _page_dir(job_id) / f"p{page}.png"
    if not p.exists():
        raise HTTPException(status_code=404, detail="该报告没有保存这一页的图像（旧任务、非 PDF，或该页没有正文引注）")
    return FileResponse(p, media_type="image/png")


@app.get("/api/report/{job_id}/page/{page}")
def report_page_text(job_id: str, page: int):
    folder = _page_dir(job_id)
    png = folder / f"p{page}.png"
    if not png.exists():
        raise HTTPException(status_code=404, detail="该报告没有保存这一页（旧任务、非 PDF，或该页没有正文引注）")
    txt = folder / f"p{page}.txt"
    text = ""
    if txt.exists():
        try:
            text = txt.read_text(encoding="utf-8")
        except Exception:
            text = ""
    return {
        "page": page,
        "text": text,
        "image": f"/api/report/{job_id}/page/{page}.png",
        "note": "页图在分析时渲染并保存在任务目录；原始上传件按隐私策略已删除。",
    }


@app.get("/api/report/{job_id}/export")
def export_report(job_id: str, format: str = "html"):
    if format == "csv":
        report = _load_report(job_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not ready")
        text = _report_to_csv(report)
        filename = f"citeguard-{job_id}.csv"
        return Response(
            content=("\ufeff" + text).encode("utf-8"),  # BOM so Excel reads Chinese
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if format == "refs":
        report = _load_report(job_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not ready")
        text = render_reference_list(report)
        if not text:
            raise HTTPException(status_code=404, detail="reference list not available")
        return Response(
            content=text.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="citeguard-{job_id}-references.txt"'
            },
        )
    if format in {"ris", "enw", "bibtex", "csl"}:
        report = _load_report(job_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not ready")
        from citeguard.exporters import (
            refs_from_parsed,
            refs_to_bibtex,
            refs_to_csl,
            refs_to_enw,
            refs_to_ris,
        )

        refs = refs_from_parsed(report.get("references") or [])
        if not refs:
            raise HTTPException(status_code=404, detail="reference list not available")
        if format == "ris":
            text, media, ext = refs_to_ris(refs), "application/x-research-info-systems", "ris"
        elif format == "enw":
            text, media, ext = refs_to_enw(refs), "application/x-endnote-refer", "enw"
        elif format == "bibtex":
            text, media, ext = refs_to_bibtex(refs), "application/x-bibtex", "bib"
        else:
            text, media, ext = refs_to_csl(refs), "application/vnd.citationstyles.csl+json", "csl.json"
        return Response(
            content=text.encode("utf-8"),
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="citeguard-{job_id}.{ext}"'},
        )
    if format not in {"html", "md", "json"}:
        raise HTTPException(
            status_code=400, detail="format must be html/md/json/csv/refs/ris/enw/bibtex/csl"
        )
    p = config.DATA_DIR / "jobs" / job_id / f"report.{format}"
    if not p.exists():
        raise HTTPException(status_code=404, detail="export not ready")
    media = {"html": "text/html; charset=utf-8", "md": "text/markdown; charset=utf-8", "json": "application/json"}
    return FileResponse(p, media_type=media[format], filename=f"citeguard-{job_id}.{format}")


@app.get("/api/report/{job_id}/fixed")
def report_fixed(job_id: str):
    """Preview re-typeset reference entries (deterministic, no online lookup)."""
    report = _load_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not ready")
    from citeguard.fix import fix_report

    return fix_report(report)


@app.get("/api/report/{job_id}/fixed.txt")
def report_fixed_txt(job_id: str):
    report = _load_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not ready")
    from citeguard.fix import as_text, fix_report

    text = as_text(fix_report(report))
    return Response(
        content=("\ufeff" + text).encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="citeguard-{job_id}-fixed.txt"'
        },
    )


@app.get("/api/report/{job_id}/annotated")
def api_report_annotated(job_id: str):
    """Copy of the uploaded PDF with problem references pinned to page margins."""
    from citeguard.annotate import annotate_pdf

    report = _load_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在或任务未完成")
    out = _report_path(job_id).parent / "report.annotated.pdf"
    if not out.exists():
        candidates = sorted(UPLOAD_DIR.glob(f"{job_id}*.pdf"))
        if not candidates:
            raise HTTPException(status_code=404, detail="这份报告的原始 PDF 已清理；重新上传同一篇即可生成批注版")
        stats = annotate_pdf(candidates[0], report, out)
    else:
        stats = report.get("annotated") or {"annotated": 0, "unmapped": 0}
    return FileResponse(
        out,
        media_type="application/pdf",
        filename=f"citeguard-{job_id}-annotated.pdf",
        headers={
            "X-Annotated": str(stats["annotated"]),
            "X-Unmapped": str(stats["unmapped"]),
            "X-Citations-Annotated": str(stats.get("citations_annotated", 0)),
            "X-Citations-Unmapped": str(stats.get("citations_unmapped", 0)),
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/reports/zip")
def reports_zip(ids: str = ""):
    """Bundle several finished reports into one archive for batch review."""
    wanted = [part.strip() for part in ids.split(",") if part.strip()]
    if not wanted:
        raise HTTPException(status_code=400, detail="请至少选择一份报告")
    if len(wanted) > 20:
        raise HTTPException(status_code=400, detail="一次最多打包 20 份报告")
    import io
    import zipfile

    entries: list[tuple[str, list[Path]]] = []
    seen: set[str] = set()
    for job_id in wanted:
        if job_id in seen:
            continue
        seen.add(job_id)
        job_dir = config.DATA_DIR / "jobs" / job_id
        files = sorted(p for p in job_dir.glob("report.*") if p.is_file())
        if files:
            entries.append((job_id, files))
    if not entries:
        raise HTTPException(status_code=404, detail="所选报告都还没有生成")
    manifest = {
        "version": app.version,
        "jobs": [job_id for job_id, _ in entries],
        "files": {job_id: [p.name for p in files] for job_id, files in entries},
    }
    ris_parts: list[str] = []
    enw_parts: list[str] = []
    for _, files in entries:
        for path in files:
            if path.name == "report.ris":
                ris_parts.append(path.read_text(encoding="utf-8-sig"))
            elif path.name == "report.enw":
                enw_parts.append(path.read_text(encoding="utf-8-sig"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for job_id, files in entries:
            for path in files:
                zf.write(path, arcname=f"{job_id}/{path.name}")
        if ris_parts:
            zf.writestr("all.ris", "\ufeff" + "".join(ris_parts))
        if enw_parts:
            zf.writestr("all.enw", "\ufeff" + "".join(enw_parts))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="citeguard-reports.zip"'},
    )


@app.get("/api/report/{job_id}/bundle")
def report_bundle(job_id: str):
    """Evidence bundle: every rendered report file plus a manifest, one zip."""
    report = _load_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not ready")
    import io
    import zipfile

    job_dir = config.DATA_DIR / "jobs" / job_id
    files = sorted(p for p in job_dir.glob("report.*") if p.is_file())
    if not files:
        raise HTTPException(status_code=404, detail="export not ready")
    manifest = {
        "job_id": job_id,
        "version": app.version,
        "generated_at": report.get("generated_at") or "",
        "files": [p.name for p in files],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.name)
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="citeguard-{job_id}-evidence.zip"'
        },
    )


def _report_to_csv(report: dict) -> str:
    """Flat one-row-per-reference export for teachers / spreadsheet workflows."""
    import csv
    import io

    status_label = {
        "Exact": "真实一致",
        "Minor": "元数据偏差",
        "Major": "疑似虚构或错配",
        "Unverified": "未找到匹配",
        "Unknown": "无法核验",
    }
    support_label = {
        "support": "支持",
        "partial": "部分支持",
        "contradict": "矛盾",
        "no_evidence": "无证据",
        "not_checked": "未检测",
    }
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "序号",
            "结论",
            "支持度",
            "题名",
            "作者",
            "年份",
            "来源",
            "卷",
            "期",
            "页码",
            "DOI",
            "合规分",
            "格式问题",
            "修改建议",
            "规范条目（按原文重排）",
            "引用句",
            "证据链接",
            "原始条目",
        ]
    )
    formatted_by_index = {
        str(it.get("index")): it.get("entry", "")
        for it in (report.get("formatted_reference_list") or [])
    }
    for item in report.get("references", []):
        p = item.get("parsed") or {}
        v = item.get("verify") or {}
        c = item.get("compliance") or {}
        sup = item.get("support") or {}
        best = v.get("best") or {}
        issues = c.get("issues") or []
        errors = [f"[{i.get('level')}] {i.get('message')}" for i in issues]
        suggestions = [i.get("suggestion", "") for i in issues if i.get("suggestion")]
        writer.writerow(
            [
                item.get("index", ""),
                status_label.get(v.get("status"), v.get("status", "")),
                support_label.get(sup.get("label"), sup.get("label", "")),
                p.get("title", ""),
                ", ".join(p.get("authors") or []),
                p.get("year", ""),
                p.get("venue", ""),
                p.get("volume", ""),
                p.get("issue", ""),
                p.get("pages", ""),
                p.get("doi", ""),
                c.get("score", ""),
                "；".join(errors),
                "；".join(suggestions),
                formatted_by_index.get(str(item.get("index", "")), ""),
                sup.get("claim", ""),
                best.get("url", "") or (f"https://doi.org/{best.get('doi')}" if best.get("doi") else ""),
                item.get("raw", ""),
            ]
        )
    return buf.getvalue()


def _group_jobs_by_file(jobs: list[dict]) -> list[dict]:
    """Collapse repeated analyses of the same file, keeping the newest run."""
    grouped: list[dict] = []
    seen: dict[str, dict] = {}
    for job in jobs:
        key = (job.get("filename") or job.get("name") or "").strip().lower()
        if key and key in seen:
            current = seen[key]
            current["runs"] += 1
            if not current.get("has_report") and job.get("has_report"):
                replacement = dict(job)
                replacement["runs"] = current["runs"]
                index = grouped.index(current)
                grouped[index] = replacement
                seen[key] = replacement
            continue
        item = dict(job)
        item["runs"] = 1
        if key:
            seen[key] = item
        grouped.append(item)
    return grouped


@app.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    jobs = manager.recent(60)
    for job in jobs:
        job["has_report"] = _report_path(job["id"]).exists()
        job["retryable"] = (config.DATA_DIR / "jobs" / job["id"] / "input.txt").exists()
    total_runs = len(jobs)
    show_all = request.query_params.get("all", "").lower() in {"1", "true", "yes"}
    if not show_all:
        jobs = _group_jobs_by_file(jobs)
    return templates.TemplateResponse(
        request,
        "history.html",
        {"jobs": jobs, "total_runs": total_runs, "show_all": show_all, "active": "history"},
    )


@app.get("/api/jobs")
def api_jobs(limit: int = 30):
    """最近任务列表（报告页的“对比历史”选择器用）。"""
    jobs = manager.recent(min(max(int(limit), 1), 60))
    out = []
    for job in jobs:
        out.append({
            "id": job.get("id"),
            "name": job.get("name") or job.get("input_name") or "",
            "created_at": job.get("created_at") or job.get("created") or "",
            "status": job.get("status") or "",
            "has_report": _report_path(job.get("id") or "").exists(),
        })
    return {"jobs": out}


@app.get("/api/history/trend")
def history_trend(days: int = 30):
    """Daily health trend from saved reports (no new work is queued)."""
    span = min(max(int(days), 7), 180)
    buckets: dict[str, dict] = {}
    for job in manager.recent(200):
        job_id = job.get("id") or ""
        report = _load_report(job_id)
        if not isinstance(report, dict):
            continue
        stamp = str(job.get("created_at") or job.get("created") or "")
        day = stamp[:10]
        if len(day) != 10:
            continue
        stats = report.get("stats") or {}
        health = report.get("health") or {}
        item = buckets.setdefault(day, {
            "date": day,
            "reports": 0,
            "scored": 0,
            "health_sum": 0.0,
            "major": 0,
            "exact": 0,
            "unverified": 0,
            "format_issues": 0,
        })
        item["reports"] += 1
        item["major"] += int(stats.get("Major") or 0)
        item["exact"] += int(stats.get("Exact") or 0)
        item["unverified"] += int(stats.get("Unverified") or 0) + int(stats.get("Unknown") or 0)
        item["format_issues"] += int(stats.get("format_issues") or 0)
        overall = health.get("overall")
        if isinstance(overall, (int, float)):
            item["scored"] += 1
            item["health_sum"] += float(overall)
    points = []
    for day in sorted(buckets):
        item = buckets[day]
        points.append({
            "date": day,
            "reports": item["reports"],
            "scored": item["scored"],
            "avg_health": round(item["health_sum"] / item["scored"], 1) if item["scored"] else None,
            "major": item["major"],
            "exact": item["exact"],
            "unverified": item["unverified"],
        })
    return {"days": span, "points": points[-span:], "source": "data/jobs/*/report.json"}


@app.get("/api/compare")
def api_compare(a: str, b: str):
    """Compare two completed reports by their positional reference order."""
    ra = _load_report(a)
    rb = _load_report(b)
    if ra is None or rb is None:
        raise HTTPException(status_code=404, detail="对比的两份报告必须都存在（先完成任务）")
    return _compare_reports(ra, rb)


@app.get("/report/{job_id}", response_class=HTMLResponse)
def report_page(request: Request, job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return templates.TemplateResponse(
        request, "report.html", {"job": job, "report": _load_active_report(job_id), "active": "report"}
    )


def _load_json(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _benchmark_context() -> dict:
    """Benchmark page: CiteBench-CN + ClaimSupport-CN + real-data experiments."""
    data_dir = config.DATA_DIR
    benchmark = _load_json(data_dir / "citebench_cn" / "results.json")
    benchmark_v2 = _load_json(data_dir / "citebench_cn" / "v2_results.json")
    support = _load_json(data_dir / "claimsupport_cn" / "results.json")
    exp = data_dir / "experiments"
    real: dict = {}
    parse = _load_json(exp / "parse_real.json")
    if parse and parse.get("summary"):
        real["parse"] = parse["summary"]
    verify = _load_json(exp / "verify_real.json")
    if verify and verify.get("summary"):
        summary = dict(verify["summary"])
        rows = verify.get("rows") or []
        groups = {"cjk": {"refs": 0, "definite": 0}, "latin": {"refs": 0, "definite": 0}}
        for row in rows:
            title = row.get("title") or ""
            key = "cjk" if re.search(r"[\u4e00-\u9fff]", title) else "latin"
            groups[key]["refs"] += 1
            if row.get("status") in ("Exact", "Minor"):
                groups[key]["definite"] += 1
        if groups["cjk"]["refs"] or groups["latin"]["refs"]:
            summary["by_language"] = groups
        real["verify"] = summary
    library = _load_json(exp / "library_real.json")
    if library and library.get("summary"):
        real["library"] = library["summary"]
    recall = _load_json(exp / "search_recall.json")
    if recall and recall.get("summary"):
        real["recall"] = recall["summary"]
    e4 = _load_json(exp / "e4_format.json")
    if e4 and e4.get("drift"):
        real["e4"] = {
            "strict": e4["drift"].get("strict_detected"),
            "n": e4["drift"].get("n"),
            "type_recognition": (e4.get("metrics") or {}).get("type_code_recognition", {}).get("rate"),
        }
    scifact = _load_json(exp / "scifact_support_results.json")
    if scifact and scifact.get("results"):
        scifact_results = scifact["results"]
        real["scifact"] = {
            "n": scifact.get("n_claims"),
            "oracle_f1": (scifact_results.get("oracle") or {}).get("macro_f1"),
            "abstract_f1": (scifact_results.get("abstract") or {}).get("macro_f1"),
        }
    external = _load_json(exp / "scifact_refchecker_deepseek.json")
    ext_metrics = external.get("metrics") if external else None
    if external and ext_metrics:
        real["external"] = {
            "n": external.get("n"),
            "macro_f1": ext_metrics.get("macro_f1"),
            "accuracy": ext_metrics.get("accuracy"),
        }
    ocr = _load_json(exp / "ocr_scan_real.json")
    if ocr and ocr.get("parsed_refs") is not None:
        real["ocr"] = {
            "parsed": ocr.get("parsed_refs"),
            "expected": ocr.get("expected_refs"),
            "pages": ocr.get("pages"),
        }
    consistency = _load_json(exp / "citation_consistency.json")
    if consistency and consistency.get("cases"):
        real["consistency"] = {
            "cases": consistency.get("cases"),
            "passed": consistency.get("passed"),
            "accuracy": consistency.get("accuracy"),
        }
    mutation = _load_json(exp / "real_mutation_eval.json")
    if mutation and mutation.get("summary"):
        m = mutation["summary"]
        mut = m.get("mutations") or {}
        base = m.get("baseline") or {}
        real["mutation"] = {
            "n": mut.get("n"),
            "detected": mut.get("detected"),
            "detection_rate": mut.get("detection_rate"),
            "exact_rate": mut.get("exact_rate"),
            "sample": m.get("sample_size"),
            "baseline_n": base.get("n"),
            "baseline_exact_rate": base.get("exact_rate"),
        }
    wanfang_state = _load_json(exp / "wanfang_batch.json")
    if wanfang_state and wanfang_state.get("processed"):
        vals = list(wanfang_state["processed"].values())
        ok = [v for v in vals if "error" not in v]
        strong = [v for v in ok if (v.get("title_sim") or 0) >= 0.92 and v.get("year_match")]
        cjk = (real.get("verify") or {}).get("by_language", {}).get("cjk") or {}
        base_definite = cjk.get("definite") or 0
        base_refs = cjk.get("refs") or 0
        projection = (base_definite + len(strong)) / base_refs if base_refs else None
        status = (real.get("verify") or {}).get("status") or {}
        overall_definite = int(status.get("Exact", 0)) + int(status.get("Minor", 0))
        overall_refs = int((real.get("verify") or {}).get("refs") or 0)
        real["wanfang"] = {
            "probed": len(ok),
            "candidates": wanfang_state.get("candidates_total") or len(vals),
            "strong": len(strong),
            "mid": sum(1 for v in ok if 0.8 <= (v.get("title_sim") or 0) < 0.92),
            "errors": len(vals) - len(ok),
            "base_definite": base_definite,
            "base_refs": base_refs,
            "projection": projection,
            "overall_definite": overall_definite,
            "overall_refs": overall_refs,
            "overall_projection": (overall_definite + len(strong)) / overall_refs if overall_refs else None,
        }

    local_models = []
    for name in (
        "support_local_qwen25_3b_gpu.json",
        "support_local_qwen25_3b_simple.json",
        "support_local_qwen25_7b_gpu.json",
        "support_local_qwen25_7b_simple.json",
    ):
        d = _load_json(exp / name)
        if not d or not d.get("n"):
            continue
        metrics = d.get("metrics") or {}
        f1 = d.get("macro_f1", metrics.get("macro_f1"))
        if f1 is None:
            continue
        local_models.append(
            {
                "model": d.get("model") or (d.get("judge") or {}).get("model") or name,
                "n": d.get("n"),
                "macro_f1": f1,
                "accuracy": d.get("accuracy", metrics.get("accuracy")),
                "prompt": "精简 prompt" if "simple" in name else "产品长 prompt",
                "source": name,
            }
        )
    qwen3 = _load_json(exp / "support_local_qwen3_gpu.json")
    for row in (qwen3 or {}).get("rows", []):
        local_models.append(
            {
                "model": row.get("model") or "Qwen3",
                "n": row.get("n"),
                "macro_f1": row.get("macro_f1"),
                "accuracy": row.get("accuracy"),
                "prompt": "%s · %s" % (row.get("prompt") or "", row.get("split") or ""),
                "source": row.get("source") or "support_local_qwen3_gpu.json",
            }
        )
    figure_models = []
    for name in ("figure_prompt_eval.json", "figure_prompt_eval_3b.json"):
        data = _load_json(exp / name)
        if data and data.get("summary"):
            figure_models.append(
                {
                    "model": data.get("model"),
                    "n": (data["summary"].get("v2") or {}).get("n"),
                    "runs": data["summary"],
                }
            )
    if figure_models:
        real["figure"] = {
            "model": figure_models[0]["model"],
            "n": figure_models[0]["n"],
            "runs": figure_models[0]["runs"],
            "models": figure_models,
        }
    chartcheck = []
    for name, label in (
        ("chartcheck_val200_7b_v1.json", "Qwen2.5-VL-7B"),
        ("chartcheck_val200_8b_v1.json", "Qwen3-VL-8B"),
        ("chartcheck_val200_v3.json", "Qwen3-VL-8B · 分步 v3"),
    ):
        data = _load_json(exp / name)
        if not data or not data.get("sample"):
            continue
        conf = data.get("confusion") or {}
        insuff = sum((conf.get(g) or {}).get("insufficient", 0) for g in conf)
        chartcheck.append(
            {
                "model": label,
                "n": data.get("sample"),
                "binary_accuracy": data.get("binary_accuracy"),
                "binary_macro_f1": data.get("binary_supported_macro_f1"),
                "accuracy": data.get("accuracy"),
                "macro_f1": data.get("macro_f1"),
                "insufficient_rate": (insuff / data["sample"]) if data.get("sample") else None,
                "latency_s": (data.get("latency_ms_mean") or 0) / 1000.0,
            }
        )
    if chartcheck:
        real["figure_external"] = {
            "dataset": "ChartCheck（Akhtar et al., ACL 2024 Findings；MIT；val 953 分层抽取）",
            "n": chartcheck[0]["n"],
            "models": chartcheck,
        }
    support_audit = None
    audit_path = config.DATA_DIR / "claimsupport_cn" / "llm_consensus.json"
    if audit_path.exists():
        try:
            audit_metrics = json.loads(audit_path.read_text(encoding="utf-8"))["metrics"]
            support_audit = {
                "n": audit_metrics.get("n"),
                "annotators": audit_metrics.get("annotators", []),
                "majority_agreement": audit_metrics.get("majority_vs_constructed", {}).get("agreement"),
                "majority_kappa": audit_metrics.get("majority_vs_constructed", {}).get("kappa"),
                "product_accuracy": (audit_metrics.get("product") or {}).get("accuracy_vs_majority"),
                "product_macro_f1": (audit_metrics.get("product") or {}).get("macro_f1_vs_majority"),
            }
        except Exception:
            support_audit = None
    holdout_path = config.DATA_DIR / "claimsupport_cn" / "llm_consensus-test.json"
    if support_audit and holdout_path.exists():
        try:
            hold = json.loads(holdout_path.read_text(encoding="utf-8"))["metrics"]
            support_audit["holdout"] = {
                "n": hold.get("n"),
                "majority_agreement": hold.get("majority_vs_constructed", {}).get("agreement"),
                "majority_kappa": hold.get("majority_vs_constructed", {}).get("kappa"),
                "product_accuracy": (hold.get("product") or {}).get("accuracy_vs_majority"),
                "product_macro_f1": (hold.get("product") or {}).get("macro_f1_vs_majority"),
            }
        except Exception:
            pass
    return {
        "benchmark": benchmark,
        "benchmark_v2": benchmark_v2,
        "support": support,
        "real": real,
        "local_models": local_models,
        "support_audit": support_audit,
        "status": _system_status(),
    }


def _system_status() -> list[dict]:
    """Runtime self-check for /benchmark. Never prints secrets."""
    import shutil

    from citeguard import ocr as ocr_module
    from citeguard import support as support_module

    items: list[dict] = []
    base, model, key = support_module.judge_endpoint()
    hosted = "deepseek" in (base or "").lower()
    if support_module.judge_available():
        items.append({
            "label": "判定模型",
            "value": ("托管 · " if hosted else "自托管 · ") + (model or "未命名"),
            "state": "ok",
            "hint": "支持度判定链路；密钥只检查是否配置",
        })
    else:
        items.append({
            "label": "判定模型",
            "value": "未配置",
            "state": "warn",
            "hint": "设置 DEEPSEEK_API_KEY 或 CITEGUARD_JUDGE_BASE_URL 后启用支持度判定",
        })
    if config.SUPPORT_AUDIT:
        try:
            style = support_module._audit_style()
        except Exception:
            style = config.SUPPORT_AUDIT_STYLE
        items.append({
            "label": "覆盖审计",
            "value": "开启 · " + style,
            "state": "ok",
            "hint": "自托管判官走 v2，托管 API 走 v1",
        })
    else:
        items.append({"label": "覆盖审计", "value": "关闭", "state": "warn", "hint": "CITEGUARD_SUPPORT_AUDIT=0"})
    items.append({
        "label": "判定并发",
        "value": "%d 路" % config.SUPPORT_WORKERS,
        "state": "ok",
        "hint": "CITEGUARD_SUPPORT_WORKERS（1–8）",
    })
    if config.ACCESS_TOKEN:
        items.append({
            "label": "访问控制",
            "value": "已开启",
            "state": "ok",
            "hint": "限流 %d 次/分钟 · 每次 POST 请求" % config.RATE_LIMIT_PER_MIN,
        })
    else:
        items.append({
            "label": "访问控制",
            "value": "未开启",
            "state": "warn",
            "hint": "公开演示建议设置 CITEGUARD_ACCESS_TOKEN",
        })
    items.append({
        "label": "OCR",
        "value": "可用" if ocr_module.ocr_available() else "未安装",
        "state": "ok" if ocr_module.ocr_available() else "warn",
        "hint": "扫描版 PDF 的可选依赖（rapidocr-onnxruntime）",
    })
    items.append({
        "label": "图表核验",
        "value": config.VL_MODEL if config.VL_ENDPOINT else "未配置",
        "state": "ok" if config.VL_ENDPOINT else "warn",
        "hint": "CITEGUARD_VL_ENDPOINT 指向自托管视觉模型",
    })
    try:
        library = Library.load(config.LIBRARY_FILE)
        with_abstract = sum(1 for e in library.entries if (getattr(e, "abstract", "") or "").strip())
        items.append({
            "label": "题录库",
            "value": "%d 条 · %d 条带摘要" % (len(library.entries), with_abstract),
            "state": "ok",
            "hint": "本地题录库用于核验回退与摘要支持度判定",
        })
    except Exception:
        items.append({"label": "题录库", "value": "不可用", "state": "warn", "hint": "读取失败"})
    try:
        free_gb = shutil.disk_usage(str(ROOT)).free / 1e9
        items.append({
            "label": "磁盘剩余",
            "value": "%.1f GB" % free_gb,
            "state": "ok" if free_gb > 5 else "bad",
            "hint": "低于 5 GB 时上传与报告可能失败",
        })
    except Exception:
        pass
    return items


@app.get("/benchmark", response_class=HTMLResponse)
def benchmark_page(request: Request):
    ctx = _benchmark_context()
    return templates.TemplateResponse(
        request, "benchmark.html", {**ctx, "active": "benchmark"}
    )


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    return templates.TemplateResponse(request, "about.html", {"active": "about"})


@app.get("/word/taskpane", response_class=HTMLResponse)
def word_taskpane(request: Request):
    """Task pane for the Word add-in preview (served same-origin by this app)."""
    return templates.TemplateResponse(
        request, "word_taskpane.html", {"active": "", "version": app.version}
    )


@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request):
    """Single-claim support check: the same judge the extension and SDK call."""
    return templates.TemplateResponse(
        request,
        "support.html",
        {"active": "support", "judge_ok": support.judge_available()},
    )


@app.get("/batch", response_class=HTMLResponse)
def batch_page(request: Request):
    """Batch claim-evidence check page (same API as the SDK)."""
    return templates.TemplateResponse(
        request,
        "batch.html",
        {"active": "batch", "judge_ok": support.judge_available()},
    )



@app.get("/api/citemap/topics")
def citemap_topics_api():
    """Topic summaries for CiteMap (validated from the corpus files)."""
    data_dir = config.DATA_DIR / "evidence_map"
    try:
        return {"schema_version": "1.0", "topics": evidence_map.list_topics(data_dir)}
    except evidence_map.EvidenceMapError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/api/citemap/{topic_id}")
def citemap_topic_api(topic_id: str):
    """One validated CiteMap payload; unknown topic returns 404 + known ids."""
    data_dir = config.DATA_DIR / "evidence_map"
    try:
        return evidence_map.topic_payload(topic_id, data_dir)
    except evidence_map.UnknownTopicError as exc:
        known = [t.get("topic_id") for t in evidence_map.list_topics(data_dir)]
        return JSONResponse(
            {"ok": False, "error": str(exc), "known_topics": known}, status_code=404
        )
    except evidence_map.EvidenceMapError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/citemap", response_class=HTMLResponse)
def citemap_page(request: Request, topic: str = ""):
    """CiteMap topic view: claims, stance evidence, method/sample and gaps."""
    data_dir = config.DATA_DIR / "evidence_map"
    try:
        topics = evidence_map.list_topics(data_dir)
        current = topic or (topics[0].get("topic_id") if topics else "")
        payload = evidence_map.topic_payload(current, data_dir) if current else None
    except evidence_map.UnknownTopicError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except evidence_map.EvidenceMapError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return templates.TemplateResponse(
        request,
        "citemap.html",
        {"active": "citemap", "topics": topics, "current_topic": current, "payload": payload},
    )

@app.get("/live", response_class=HTMLResponse)
def live_page(request: Request):
    """CiteGuard Live：选中句对检索候选的试用页。"""
    return templates.TemplateResponse(request, "live.html", {"active": "live"})


@app.get("/aggregate", response_class=HTMLResponse)
def aggregate_page(request: Request):
    """Cohort view for several finished reports (class / lab batch)."""
    raw = request.query_params.get("ids", "")
    ids = [i for i in dict.fromkeys(part.strip() for part in raw.split(",")) if i]
    return templates.TemplateResponse(
        request,
        "aggregate.html",
        {"active": "aggregate", "ids": ",".join(ids[:50])},
    )


@app.get("/figure", response_class=HTMLResponse)
def figure_page(request: Request):
    model = (config.VL_MODEL or "qwen3-vl-8b").strip()
    label = model
    for small, big in (("-8b", "-8B"), ("-7b", "-7B"), ("-3b", "-3B"), ("-2b", "-2B")):
        label = label.replace(small, big)
    label = (label.replace("qwen3-vl-", "Qwen3-VL-")
                  .replace("qwen2.5-vl-", "Qwen2.5-VL-")
                  .replace("-instruct", ""))
    return templates.TemplateResponse(
        request,
        "figure.html",
        {
            "active": "figure",
            "vl_available": figure_check.available(),
            "max_mb": config.VL_MAX_FIGURE_MB,
            "vl_model_label": label,
        },
    )


@app.post("/api/figure-check")
def figure_check_api(
    image: UploadFile | None = File(None),
    claim: str = Form(""),
    claims: str = Form(""),
    context: str = Form(""),
    paper: UploadFile | None = File(None),
    page: str = Form(""),
):
    if config.OFFLINE:
        return JSONResponse(
            {"ok": False, "code": "offline", "error": "离线模式：图表核验需要调用视觉模型，已跳过"},
            status_code=503,
        )
    if not figure_check.available():
        return JSONResponse(
            {"ok": False, "code": "not_configured", "error": "未配置图表核验服务（设置 CITEGUARD_VL_ENDPOINT）"},
            status_code=503,
        )
    claim_list = figure_check.split_claims(claims) if claims.strip() else []
    claim_for_number = claim_list[0] if claim_list else claim
    if image is None and paper is None:
        return JSONResponse(
            {
                "ok": False,
                "code": "no_input",
                "error": "请上传图表截图，或上传论文 PDF 让系统自动定位并渲染图/表所在页",
            },
            status_code=400,
        )
    payload = b""
    if image is not None:
        payload = image.file.read(config.VL_MAX_FIGURE_MB * 1024 * 1024 + 1)
        if len(payload) > config.VL_MAX_FIGURE_MB * 1024 * 1024:
            return JSONResponse(
                {"ok": False, "code": "image_too_large", "error": f"图片超过 {config.VL_MAX_FIGURE_MB} MB"},
                status_code=400,
            )
    page_no = 0
    auto_caption = ""
    rendered: list[tuple[int, bytes, str, list[str]]] = []
    if paper is not None and paper.filename:
        if Path(paper.filename).suffix.lower() != ".pdf":
            return JSONResponse(
                {"ok": False, "code": "paper_not_pdf", "error": "按页取正文只支持 PDF 论文"},
                status_code=400,
            )
        raw = paper.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
        if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
            return JSONResponse(
                {"ok": False, "code": "paper_too_large", "error": f"论文 PDF 超过 {config.MAX_UPLOAD_MB} MB"},
                status_code=400,
            )
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as fh:
                fh.write(raw)
                tmp = Path(fh.name)
            if page.strip():
                try:
                    page_no = int(page.strip())
                except ValueError:
                    return JSONResponse(
                        {"ok": False, "code": "bad_page", "error": "页码要填整数（从 1 开始）"},
                        status_code=400,
                    )
            if image is None:
                # No screenshot: locate the figure/table caption per claim, render
                # each distinct page, and judge the claims on that rendered page.
                targets = claim_list or [claim]
                groups: dict[int, list[str]] = {}
                captions: dict[int, str] = {}
                for c in targets:
                    number = figure_number_from_claim(c)
                    kind = caption_kind_from_claim(c)
                    found = find_figure_page(tmp, number, kind=kind, claim=c)
                    if not found:
                        label = ("表" if kind == "table" else "图") + (f" {number} 的图注" if number else "注")
                        return JSONResponse(
                            {
                                "ok": False,
                                "code": "page_not_found",
                                "error": f"未在前 40 页找到{label}，请手动填写页码或上传图表截图",
                            },
                            status_code=400,
                        )
                    groups.setdefault(found[0], []).append(c)
                    captions.setdefault(found[0], found[1])
                if len(groups) > 3:
                    return JSONResponse(
                        {"ok": False, "code": "too_many_pages", "error": "结论涉及超过 3 个图/表页，请拆分后分别核验"},
                        status_code=400,
                    )
                for pg, cs in groups.items():
                    try:
                        ctx = extract_page_text(tmp, pg)
                    except (ValueError, RuntimeError):
                        ctx = ""
                    rendered.append((pg, render_page_png(tmp, pg), ctx, cs))
                    if not auto_caption:
                        auto_caption = captions.get(pg, "")
            else:
                if not page_no:
                    number = figure_number_from_claim(claim_for_number)
                    kind = caption_kind_from_claim(claim_for_number)
                    found = find_figure_page(tmp, number, kind=kind, claim=claim_for_number)
                    if not found:
                        label = ("图" if kind == "figure" else "表" if kind == "table" else "图/表") + (
                            f" {number} 的图注" if number else "注"
                        )
                        return JSONResponse(
                            {
                                "ok": False,
                                "code": "page_not_found",
                                "error": f"未在前 40 页找到{label}，请手动填写页码或粘贴该页正文",
                            },
                            status_code=400,
                        )
                    page_no, auto_caption = found
                page_text = extract_page_text(tmp, page_no)
                body = (f"图注：{auto_caption}\n\n" if auto_caption else "") + page_text
                context = (body + "\n\n" + context).strip() if context.strip() else body
        except ValueError as exc:
            return JSONResponse(
                {"ok": False, "code": "page_text_unavailable", "error": str(exc)}, status_code=400
            )
        except RuntimeError as exc:
            return JSONResponse(
                {"ok": False, "code": "page_render_failed", "error": str(exc)}, status_code=400
            )
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    # A renderer may still hold the handle for a moment on
                    # Windows; cleanup must never turn a valid result into 500.
                    pass

    if rendered:
        items: list[dict] = []
        first = True
        pages_used: list[int] = []
        for pg, png, ctx, cs in rendered:
            result = figure_check.check_claims(png, "image/png", cs, ctx)
            pages_used.append(pg)
            if not result.get("ok"):
                return JSONResponse(result, status_code=400)
            for item in result.get("items") or []:
                item["page"] = pg
                items.append(item)
            if first:
                first = False
                out = result
        out["items"] = items
        out["context_source"] = "pdf_pages:" + ",".join(str(p) for p in pages_used)
        out["page_no"] = pages_used[0]
        out["page_rendered"] = True
        return JSONResponse(out)
    if claim_list:
        result = figure_check.check_claims(payload, image.content_type or "", claim_list, context)
        if page_no and result.get("ok"):
            result["context_source"] = f"pdf_auto:{page_no}" if auto_caption else f"pdf_page:{page_no}"
        return JSONResponse(result, status_code=200 if result.get("ok") else 400)
    result = figure_check.check_figure(payload, image.content_type or "", claim, context)
    if page_no and result.get("ok"):
        result["context_source"] = f"pdf_auto:{page_no}" if auto_caption else f"pdf_page:{page_no}"
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


def _load_compare(job_id: str) -> dict | None:
    path = _compare_dir() / f"{job_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _run_compare_job(job_id: str, items: list[tuple[str, str]]) -> None:
    texts: list[tuple[str, str]] = []
    for name, path in items:
        text = extract_text(path)
        texts.append((name, text))

    def progress(index: int, total: int, name: str) -> None:
        manager.update(
            job_id,
            progress=min(95, 10 + int(85 * index / max(total, 1))),
            stage=f"抽取第 {index}/{total} 篇：{name}",
        )

    result = compare.compare_texts(texts, on_progress=progress)
    result["job_id"] = job_id
    (_compare_dir() / f"{job_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@app.get("/compare", response_class=HTMLResponse)
def compare_page(request: Request):
    return templates.TemplateResponse(
        request,
        "compare.html",
        {
            "active": "compare",
            "judge_available": compare.available(),
            "min_papers": compare.MIN_PAPERS,
            "max_papers": compare.MAX_PAPERS,
            "fields": compare.FIELDS,
        },
    )


@app.post("/api/compare")
def compare_api(files: list[UploadFile] = File(...)):
    if not compare.available():
        return JSONResponse(
            {"ok": False, "code": "not_configured", "error": "未配置判官接口（CITEGUARD_JUDGE_BASE_URL / API_KEY）"},
            status_code=503,
        )
    if not compare.MIN_PAPERS <= len(files) <= compare.MAX_PAPERS:
        raise HTTPException(
            status_code=400,
            detail=f"一次需要 {compare.MIN_PAPERS}–{compare.MAX_PAPERS} 篇文献（当前 {len(files)} 篇）",
        )
    names: list[str] = []
    suffixes: list[str] = []
    for index, upload in enumerate(files, 1):
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"第 {index} 个文件格式不支持（仅 PDF / DOCX / TXT / MD）",
            )
        names.append(Path(upload.filename or f"文献{index}").stem[:60] or f"文献{index}")
        suffixes.append(suffix)
    job = manager.create(filename=" / ".join(names))
    items: list[tuple[str, str]] = []
    try:
        for index, (upload, name, suffix) in enumerate(zip(files, names, suffixes)):
            dst = UPLOAD_DIR / f"{job['id']}-{index}{suffix}"
            _save_upload(upload, dst)
            items.append((name, str(dst)))
    except HTTPException:
        for _name, path in items:
            Path(path).unlink(missing_ok=True)
        manager.discard(job["id"])
        raise
    manager.submit(job["id"], _run_compare_job, items)
    return JSONResponse({"job_id": job["id"]}, status_code=202)


@app.get("/api/compare/{job_id}")
def compare_result(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": job, "result": _load_compare(job_id)}


@app.get("/api/compare/{job_id}/export")
def compare_export(job_id: str, format: str = "md"):
    result = _load_compare(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="结果还没准备好")
    fmt = (format or "md").lower()
    if fmt == "csv":
        body = "\ufeff" + compare.render_csv(result)
        media = "text/csv; charset=utf-8"
        ext = "csv"
    elif fmt == "md":
        body = compare.render_markdown(result)
        media = "text/markdown; charset=utf-8"
        ext = "md"
    else:
        raise HTTPException(status_code=400, detail="format must be md or csv")
    return Response(
        content=body.encode("utf-8"),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="citeguard-compare-{job_id}.{ext}"'},
    )


class DiscoverRequest(BaseModel):
    query: str = ""
    limit: int = 20
    page: int = 1
    sort: str = "relevance"
    year_from: Optional[int] = None
    oa_only: bool = False
    expand: str = "auto"
    include_retracted: bool = False


class DiscoverImportRequest(BaseModel):
    items: list[dict] = []


@app.get("/discover", response_class=HTMLResponse)
def discover_page(request: Request):
    return templates.TemplateResponse(
        request,
        "discover.html",
        {"active": "discover", "max_results": discover.MAX_RESULTS},
    )


@app.post("/api/discover")
def discover_api(payload: DiscoverRequest):
    try:
        result = discover.search_papers(
            payload.query,
            limit=payload.limit,
            year_from=payload.year_from,
            oa_only=payload.oa_only,
            page=payload.page,
            sort=payload.sort,
            expand=payload.expand,
            include_retracted=payload.include_retracted,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except discover.DiscoverError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.get("/api/discover/export")
def discover_export(
    query: str = "",
    limit: int = 20,
    page: int = 1,
    sort: str = "relevance",
    year_from: Optional[int] = None,
    oa_only: bool = False,
    expand: str = "auto",
    include_retracted: bool = False,
):
    try:
        result = discover.search_papers(
            query, limit=limit, year_from=year_from, oa_only=oa_only,
            page=page, sort=sort, expand=expand, include_retracted=include_retracted,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except discover.DiscoverError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    body = "\ufeff" + discover.render_csv(result)
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="citeguard-discover.csv"'},
    )


@app.post("/api/discover/import")
def discover_import(payload: DiscoverImportRequest):
    if not payload.items:
        raise HTTPException(status_code=400, detail="没有选中任何文献")
    if len(payload.items) > discover.MAX_RESULTS:
        raise HTTPException(status_code=400, detail=f"一次最多导入 {discover.MAX_RESULTS} 条")
    stats = discover.import_entries(payload.items)
    return {"ok": True, **stats}


@app.get("/api/benchmark")
def benchmark_api():
    ctx = _benchmark_context()
    if not ctx["benchmark"]:
        return {"available": False}
    return {
        "available": True,
        **ctx["benchmark"],
        "support_benchmark": ctx["support"],
        "real_data": ctx["real"],
        "local_models": ctx["local_models"],
    }



_SUPPORT_CHECK_BODY = {
    "type": "object",
    "required": ["claim", "evidence"],
    "properties": {
        "claim": {"type": "string", "maxLength": 500},
        "evidence": {"type": "string"},
    },
}
_SUPPORT_BATCH_BODY = {
    "type": "object",
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "maxItems": 50,
            "items": {
                "type": "object",
                "required": ["claim", "evidence"],
                "properties": {
                    "claim": {"type": "string", "maxLength": 500},
                    "evidence": {"type": "string"},
                },
            },
        }
    },
}


@app.post(
    "/api/support/batch",
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": _SUPPORT_BATCH_BODY}}}},
)
async def support_batch(request: Request):
    """Batch version of /api/support/check for SDKs and scripts (max 50 items)."""
    if config.OFFLINE:
        return JSONResponse({"ok": False, "code": "offline", "error": "离线模式不调用判定模型"}, status_code=503)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items 必须是非空数组")
    if len(items) > 50:
        raise HTTPException(status_code=400, detail="一次最多 50 条")
    clean = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise HTTPException(status_code=400, detail=f"第 {i+1} 条格式错误")
        claim = str(it.get("claim") or "").strip()
        evidence = str(it.get("evidence") or "").strip()
        if not claim or not evidence:
            raise HTTPException(status_code=400, detail=f"第 {i+1} 条缺少 claim/evidence")
        if len(claim) > 500:
            raise HTTPException(status_code=400, detail=f"第 {i+1} 条 claim 超过 500 字")
        clean.append((claim, evidence[:8000]))

    from citeguard.numeric_check import check as numeric_check

    def one(pair):
        claim, evidence = pair
        result = support.judge_support(claim, evidence)
        if result is None:
            return {"ok": False, "code": "judge_unavailable"}
        return {
            "ok": True,
            "label": result.get("label"),
            "confidence": result.get("confidence"),
            "reason": result.get("reason"),
            "evidence": result.get("evidence"),
            "audit": result.get("audit"),
            "numeric": numeric_check(claim, evidence).as_dict(),
        }

    with ThreadPoolExecutor(max_workers=min(4, len(clean))) as pool:
        results = list(pool.map(one, clean))
    if any(not r.get("ok") for r in results):
        return JSONResponse({"ok": False, "code": "judge_unavailable", "items": results}, status_code=503)
    return {"ok": True, "count": len(results), "items": results}


_LIVE_CHECK_BODY = {
    "type": "object",
    "required": ["claim"],
    "properties": {
        "claim": {"type": "string", "minLength": 1, "maxLength": 500},
        "page_url": {"type": "string", "maxLength": 2048},
        "page_title": {"type": "string", "maxLength": 300},
    },
}


@app.post(
    "/api/live/check",
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": _LIVE_CHECK_BODY}}}},
)
async def live_check(request: Request):
    """CiteGuard Live：判断浏览器里选中句与检索到的候选摘要是否一致。"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    claim = str(payload.get("claim") or "").strip()
    page_url = str(payload.get("page_url") or "").strip()
    page_title = str(payload.get("page_title") or "").strip()
    if not claim:
        raise HTTPException(status_code=400, detail="claim 不能为空")
    if len(claim) > 500:
        raise HTTPException(status_code=400, detail="claim 最长 500 字")
    if len(page_url) > 2048:
        raise HTTPException(status_code=400, detail="page_url 最长 2048 字符")
    if len(page_title) > 300:
        raise HTTPException(status_code=400, detail="page_title 最长 300 字符")
    from citeguard import live_check as live_mod

    result = live_mod.check_claim(claim, page_url=page_url, page_title=page_title)
    return {"ok": True, **result}


@app.post(
    "/api/support/check",
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": _SUPPORT_CHECK_BODY}}}},
)
async def support_check(request: Request):
    """Lightweight per-claim support check for the browser extension / SDK.

    The demo UI's full pipeline verifies references first and enriches evidence;
    this endpoint is for "I have a claim and an abstract, is it supported?".
    """
    if config.OFFLINE:
        return JSONResponse({"ok": False, "code": "offline", "error": "离线模式不调用判定模型"}, status_code=503)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    claim = str(payload.get("claim") or "").strip()
    evidence = str(payload.get("evidence") or "").strip()
    if not claim or not evidence:
        raise HTTPException(status_code=400, detail="需要 claim 和 evidence 两个字段")
    if len(claim) > 500:
        raise HTTPException(status_code=400, detail="claim 最长 500 字")
    if len(evidence) > 8000:
        evidence = evidence[:8000]
    from citeguard.numeric_check import check as numeric_check
    from citeguard.claim_decompose import analyze_claim

    numeric = numeric_check(claim, evidence).as_dict()
    result = support.judge_support(claim, evidence)
    if result is None:
        return JSONResponse(
            {"ok": False, "code": "judge_unavailable", "error": "判定模型不可用，请检查 CITEGUARD_JUDGE_BASE_URL / API key"},
            status_code=503,
        )
    low = support.is_low_confidence(result)
    return {
        "ok": True,
        "label": result.get("label"),
        "low_confidence": low,
        "review_hint": (
            f"置信度 {float(result.get('confidence')):.2f} 低于阈值 {config.SUPPORT_ABSTAIN:.2f}，建议人工复核"
            if low else ""
        ),
        "confidence": result.get("confidence"),
        "reason": result.get("reason", ""),
        "evidence": result.get("evidence", ""),
        "audit": result.get("audit"),
        "numeric": numeric,
        "sub_claims": analyze_claim(claim),
        "prompt_version": support.PROMPT_VERSION,
    }


@app.post("/api/feedback")
async def post_feedback(request: Request):
    """判错反馈：本地 JSONL 队列，不上传。"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求体必须是对象")
    from citeguard.feedback import record_feedback, summarize_feedback

    try:
        item = record_feedback(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "item": item, "queue": summarize_feedback([item])}


@app.get("/settings/models", response_class=HTMLResponse)
def settings_models(request: Request):
    """Choose which support-judge model the product uses (hosted/local/adapter)."""
    return templates.TemplateResponse(request=request, name="settings_models.html", context={"active": "settings"})


@app.get("/api/models")
def api_models():
    from citeguard import model_registry, support

    data = model_registry.load_registry()
    base, model, _key = support.judge_endpoint()
    return {
        "models": data["models"],
        "active": data["active"],
        "current": {"base_url": base, "model": model, "label": (model_registry.active_model() or {}).get("label") if data["active"] else "环境变量"},
    }


def _probe_judge(entry: dict) -> dict:
    import time
    import urllib.request

    url = entry["base_url"].rstrip("/") + "/models"
    started = time.monotonic()
    headers = {"Accept": "application/json"}
    key = os.environ.get("CITEGUARD_JUDGE_API_KEY") or config.DEEPSEEK_API_KEY
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            resp.read(400)
        return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000), "url": url}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": url}


@app.post("/api/models/active")
async def api_models_active(request: Request):
    from citeguard import model_registry

    payload = await request.json()
    model_id = payload.get("id")
    force = bool(payload.get("force"))
    try:
        if model_id:
            entry = model_registry.get_model(model_id)
            if not entry:
                raise ValueError("模型不存在")
            probe = _probe_judge(entry)
            if not probe["ok"] and not force:
                return JSONResponse(
                    {"ok": False, "error": "连不上该模型服务，先启动它或点“测连接”确认", "probe": probe},
                    status_code=409,
                )
        data = model_registry.set_active(model_id or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, **data}


@app.post("/api/models/test")
async def api_models_test(request: Request):
    from citeguard import model_registry

    payload = await request.json()
    entry = model_registry.get_model(payload.get("id") or "")
    if not entry:
        raise HTTPException(status_code=404, detail="模型不存在")
    return JSONResponse(_probe_judge(entry), status_code=200)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "version": app.version,
        "offline": config.OFFLINE,
        "supported": sorted(ALLOWED_SUFFIXES),
    }
