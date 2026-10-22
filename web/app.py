"""CiteGuard-CN web application (FastAPI + Jinja2).

Run (from the citeguard/ directory):
    PYTHONPATH=src uvicorn web.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

BASE = Path(__file__).resolve().parent          # citeguard/web
ROOT = BASE.parent                               # citeguard
sys.path.insert(0, str(ROOT / "src"))

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from citeguard import config  # noqa: E402
from citeguard.jobs import manager  # noqa: E402
from citeguard.local_library import Library, parse_library_text  # noqa: E402
from citeguard.pdf_extract import SUPPORTED_SUFFIXES  # noqa: E402
from citeguard.pipeline import run_job  # noqa: E402

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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup hygiene: old job records/reports and stale uploads.
    manager.cleanup()
    _cleanup_uploads()
    yield


app = FastAPI(title="引证卫士 CiteGuard-CN", version="0.3.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))


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


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    library = Library.load(config.LIBRARY_FILE)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"recent": manager.recent(6), "active": "home", "library_count": len(library)},
    )


@app.get("/library", response_class=HTMLResponse)
def library_page(request: Request):
    library = Library.load(config.LIBRARY_FILE)
    sources: dict[str, int] = {}
    for entry in library.entries:
        sources[entry.source] = sources.get(entry.source, 0) + 1
    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "active": "library",
            "count": len(library),
            "sources": sorted(sources.items()),
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
    return {
        "imported": len(entries),
        "before": before,
        "count": len(library),
        "format_guess": entries[0].source if entries else "",
    }


@app.post("/api/library/clear")
def library_clear():
    Library().save(config.LIBRARY_FILE)
    return {"count": 0}


@app.get("/api/library")
def library_api():
    library = Library.load(config.LIBRARY_FILE)
    return {"count": len(library), "sample": [e.to_dict() for e in library.entries[:5]]}


@app.post("/api/analyze")
def analyze(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    support_max: int | None = Form(default=None),
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
        written = 0
        try:
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
        except HTTPException:
            dst.unlink(missing_ok=True)
            manager.discard(job["id"])
            raise
        manager.submit(job["id"], run_job, file_path=str(dst), support_max=support_max)
    else:
        manager.submit(job["id"], run_job, text=text, support_max=support_max)
    return JSONResponse({"job_id": job["id"]}, status_code=202)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/report/{job_id}")
def report_json(job_id: str):
    report = _load_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not ready")
    return report


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
    if format not in {"html", "md", "json"}:
        raise HTTPException(status_code=400, detail="format must be html/md/json/csv")
    p = config.DATA_DIR / "jobs" / job_id / f"report.{format}"
    if not p.exists():
        raise HTTPException(status_code=404, detail="export not ready")
    media = {"html": "text/html; charset=utf-8", "md": "text/markdown; charset=utf-8", "json": "application/json"}
    return FileResponse(p, media_type=media[format], filename=f"citeguard-{job_id}.{format}")


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
            "引用句",
            "证据链接",
            "原始条目",
        ]
    )
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
                sup.get("claim", ""),
                best.get("url", "") or (f"https://doi.org/{best.get('doi')}" if best.get("doi") else ""),
                item.get("raw", ""),
            ]
        )
    return buf.getvalue()


@app.get("/report/{job_id}", response_class=HTMLResponse)
def report_page(request: Request, job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return templates.TemplateResponse(
        request, "report.html", {"job": job, "report": _load_report(job_id), "active": "report"}
    )


@app.get("/benchmark", response_class=HTMLResponse)
def benchmark_page(request: Request):
    p = config.DATA_DIR / "citebench_cn" / "results.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return templates.TemplateResponse(
        request, "benchmark.html", {"benchmark": data, "active": "benchmark"}
    )


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    return templates.TemplateResponse(request, "about.html", {"active": "about"})


@app.get("/api/benchmark")
def benchmark_api():
    p = config.DATA_DIR / "citebench_cn" / "results.json"
    if not p.exists():
        return {"available": False}
    return {"available": True, **json.loads(p.read_text(encoding="utf-8"))}


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.3.0", "supported": sorted(ALLOWED_SUFFIXES)}
