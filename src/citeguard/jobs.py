"""In-process job manager for the CiteGuard web app.

Jobs are kept in memory and persisted to data/jobs/<id>.json so a restart does
not lose the index. Heavy work runs in a small thread pool; the front-end polls
/api/jobs/<id> for progress.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from . import config

JOBS_DIR = config.DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


class JobManager:
    def __init__(self, max_workers: int = 2) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def create(self, filename: str = "") -> dict:
        job_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat(timespec="seconds")
        job = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "排队中",
            "filename": filename,
            "error": "",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._jobs[job_id] = job
        self._persist(job)
        return job

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            p = JOBS_DIR / f"{job_id}.json"
            if p.exists():
                try:
                    job = json.loads(p.read_text(encoding="utf-8"))
                    with self._lock:
                        self._jobs[job_id] = job
                except Exception:
                    return None
        return job

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(fields)
            job["updated_at"] = datetime.now().isoformat(timespec="seconds")
            snapshot = dict(job)
        self._persist(snapshot)

    def discard(self, job_id: str) -> None:
        """Remove a job that never started (e.g. rejected upload)."""
        with self._lock:
            self._jobs.pop(job_id, None)
        try:
            (JOBS_DIR / f"{job_id}.json").unlink(missing_ok=True)
        except Exception:
            pass

    def submit(self, job_id: str, fn: Callable, *args, **kwargs) -> None:
        self._executor.submit(self._run, job_id, fn, args, kwargs)

    def _run(self, job_id: str, fn: Callable, args: tuple, kwargs: dict) -> None:
        self.update(job_id, status="running", progress=1, stage="开始")
        try:
            fn(job_id, *args, **kwargs)
            self.update(job_id, status="done", progress=100, stage="完成")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.update(job_id, status="error", stage="失败", error=f"{type(exc).__name__}: {exc}")
            traceback.print_exc()

    def _persist(self, job: dict) -> None:
        try:
            (JOBS_DIR / f"{job['id']}.json").write_text(
                json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def recent(self, limit: int = 6) -> list[dict]:
        jobs: list[dict] = []
        try:
            paths = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            return jobs
        for p in paths[:limit]:
            try:
                jobs.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return jobs

    def cleanup(self, keep_recent: int = 100, max_age_days: int = 7) -> dict:
        """Delete stale job records and their report directories.

        Reports contain citation text from uploaded papers, so old ones are
        removed instead of being kept forever.
        """
        removed = {"records": 0, "reports": 0}
        cutoff = time.time() - max_age_days * 86400
        try:
            records = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            return removed
        for i, path in enumerate(records):
            try:
                stale = i >= keep_recent or path.stat().st_mtime < cutoff
            except OSError:
                continue
            if not stale:
                continue
            job_id = path.stem
            with self._lock:
                self._jobs.pop(job_id, None)
            try:
                path.unlink()
                removed["records"] += 1
            except OSError:
                pass
            job_dir = JOBS_DIR / job_id
            if job_dir.is_dir():
                shutil.rmtree(job_dir, ignore_errors=True)
                removed["reports"] += 1
        return removed


manager = JobManager()
