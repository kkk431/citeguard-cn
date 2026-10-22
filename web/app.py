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

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from citeguard import config  # noqa: E402
from citeguard.jobs import manager  # noqa: E402
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
    return templates.TemplateResponse(
        request, "index.html", {"recent": manager.recent(6), "active": "home"}
    )


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
    if format not in {"html", "md", "json"}:
        raise HTTPException(status_code=400, detail="format must be html/md/json")
    p = config.DATA_DIR / "jobs" / job_id / f"report.{format}"
    if not p.exists():
        raise HTTPException(status_code=404, detail="export not ready")
    media = {"html": "text/html; charset=utf-8", "md": "text/markdown; charset=utf-8", "json": "application/json"}
    return FileResponse(p, media_type=media[format], filename=f"citeguard-{job_id}.{format}")


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
