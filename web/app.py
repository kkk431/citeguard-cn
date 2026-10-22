"""CiteGuard-CN web application (FastAPI + Jinja2).

Run (from the citeguard/ directory):
    PYTHONPATH=src uvicorn web.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import shutil
import sys
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
from citeguard.pipeline import run_job  # noqa: E402

app = FastAPI(title="引证卫士 CiteGuard-CN", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))

UPLOAD_DIR = config.DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_SUFFIXES = {".pdf", ".txt", ".md"}


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
def analyze(file: UploadFile | None = File(default=None), text: str | None = Form(default=None)):
    if file is None and not text:
        raise HTTPException(status_code=400, detail="请上传文件或粘贴文本")
    filename = file.filename if file is not None else "pasted-text.txt"
    job = manager.create(filename=filename)
    if file is not None:
        suffix = Path(file.filename or "paper.pdf").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(status_code=400, detail="仅支持 PDF / TXT / MD")
        dst = UPLOAD_DIR / f"{job['id']}{suffix}"
        with dst.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        manager.submit(job["id"], run_job, file_path=str(dst))
    else:
        manager.submit(job["id"], run_job, text=text)
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
    return {"ok": True, "version": "0.2.0"}
