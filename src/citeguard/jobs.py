"""In-process job manager for the CiteGuard web app.

Jobs are kept in memory and persisted to data/jobs/<id>.json so a restart does
not lose the index. Heavy work runs in a small thread pool; the front-end polls
/api/jobs/<id> for progress.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
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

# B2: result cache + batch rerun that only fills the failures.
#
# The cache key is content-addressed: SHA-256 over the uploaded bytes, the
# analysis options and the *versions* of everything that can change a verdict
# (pipeline/analysis schema, judge prompt, audit style, judge model).  Two runs
# that differ only in, say, the support prompt therefore never share entries.
RESULT_CACHE_SCHEMA = 1


def _canonical(payload) -> str:
    # default=str keeps non-JSON option values (e.g. a Library object) from
    # breaking the key; two different objects still hash differently.
    return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def result_cache_key(
    file_sha256: str,
    options: dict | None = None,
    versions: dict | None = None,
    *,
    schema: int = RESULT_CACHE_SCHEMA,
) -> str:
    """Stable key for one analysis result: content + options + versions."""
    material = "\n".join(
        [
            f"schema={int(schema)}",
            f"file={file_sha256}",
            f"options={_canonical(options)}",
            f"versions={_canonical(versions)}",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def result_cache_enabled() -> bool:
    return os.environ.get("CITEGUARD_RESULT_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def default_result_cache_dir() -> Path:
    override = os.environ.get("CITEGUARD_RESULT_CACHE_DIR")
    return Path(override) if override else config.CACHE_DIR / "results"


def default_batch_dir() -> Path:
    override = os.environ.get("CITEGUARD_BATCH_DIR")
    return Path(override) if override else config.DATA_DIR / "batches"


class ResultCache:
    """Content-addressed on-disk cache for one *whole* analysis report.

    ``report`` keeps the parsed references, verification verdicts and support
    labels, so a rerun with the same bytes/options/versions skips both parsing
    and verification.  Entries are plain JSON and can be deleted at any time.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root) if root is not None else None
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._writes = 0

    @property
    def root(self) -> Path:
        return self._root if self._root is not None else default_result_cache_dir()

    def slot(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def load(self, key: str) -> Optional[dict]:
        path = self.slot(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            with self._lock:
                self._misses += 1
            return None
        if not isinstance(payload, dict) or payload.get("schema") != RESULT_CACHE_SCHEMA:
            with self._lock:
                self._misses += 1
            return None
        if payload.get("key") != key or not isinstance(payload.get("report"), dict):
            with self._lock:
                self._misses += 1
            return None
        with self._lock:
            self._hits += 1
        return payload

    def store(self, key: str, report: dict, meta: dict | None = None) -> Optional[Path]:
        if not result_cache_enabled():
            return None
        slot = self.slot(key)
        payload = {
            "schema": RESULT_CACHE_SCHEMA,
            "key": key,
            "cached_at": datetime.now().isoformat(timespec="seconds"),
            "meta": meta or {},
            "report": report,
        }
        try:
            slot.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(slot.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False)
                os.replace(tmp, slot)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        except Exception:
            return None
        with self._lock:
            self._writes += 1
        return slot

    def invalidate(self, key: str) -> bool:
        try:
            self.slot(key).unlink()
            return True
        except OSError:
            return False

    def clear(self) -> int:
        removed = 0
        root = self.root
        if not root.exists():
            return 0
        for path in root.rglob("*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
        return removed

    def stats(self) -> dict:
        with self._lock:
            hits, misses, writes = self._hits, self._misses, self._writes
        entries = 0
        root = self.root
        if root.exists():
            entries = sum(1 for _ in root.rglob("*.json"))
        attempted = hits + misses
        return {
            "hits": hits,
            "misses": misses,
            "writes": writes,
            "entries": entries,
            "hit_rate": round(hits / attempted, 4) if attempted else 0.0,
        }


class BatchRunner:
    """Batch analysis where a rerun only fills the failed items.

    Each batch keeps one record per uploaded file (content hash, cache key and
    status).  ``run`` reuses a successful item's cached report and never calls
    the analyser again; ``retry_failed`` touches only items with status
    ``error``.  Failures are *not* cached, so a retry really runs the analysis.
    """

    def __init__(
        self,
        cache: ResultCache | None = None,
        root: str | Path | None = None,
        options: dict | None = None,
        versions: dict | None = None,
    ) -> None:
        self.cache = cache if cache is not None else ResultCache()
        self._root = Path(root) if root is not None else None
        self.options = dict(options or {})
        self.versions = dict(versions or {})

    @property
    def root(self) -> Path:
        return self._root if self._root is not None else default_batch_dir()

    def _batch_dir(self, batch_id: str) -> Path:
        return self.root / batch_id

    def _record_path(self, batch_id: str) -> Path:
        return self._batch_dir(batch_id) / "batch.json"

    def _save(self, batch: dict) -> None:
        batch["updated_at"] = datetime.now().isoformat(timespec="seconds")
        path = self._record_path(batch["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def create(self, files: list[str | Path], *, options: dict | None = None, versions: dict | None = None) -> dict:
        options = dict(self.options if options is None else options)
        versions = dict(self.versions if versions is None else versions)
        batch_id = uuid.uuid4().hex[:12]
        items = []
        for i, file_path in enumerate(files, 1):
            path = Path(file_path)
            digest = sha256_file(path)
            items.append(
                {
                    "id": f"item-{i:02d}",
                    "name": path.name,
                    "path": str(path.resolve()),
                    "sha256": digest,
                    "cache_key": result_cache_key(digest, options, versions),
                    "status": "pending",
                    "source": "",
                    "error": "",
                    "report_path": "",
                    "elapsed_ms": 0,
                }
            )
        batch = {
            "id": batch_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "options": options,
            "versions": versions,
            "items": items,
            "stats": self._stats(items),
        }
        self._save(batch)
        return batch

    def get(self, batch_id: str) -> Optional[dict]:
        path = self._record_path(batch_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _report_path(self, batch_id: str, item: dict) -> Path:
        return self._batch_dir(batch_id) / "reports" / f"{item['id']}.json"

    def _write_report(self, batch_id: str, item: dict, report: dict) -> str:
        path = self._report_path(batch_id, item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        item["report_path"] = str(path)
        return str(path)

    def _read_report(self, item: dict) -> Optional[dict]:
        if not item.get("report_path"):
            return None
        try:
            return json.loads(Path(item["report_path"]).read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _stats(items: list[dict]) -> dict:
        done = sum(1 for it in items if it.get("status") == "done")
        error = sum(1 for it in items if it.get("status") == "error")
        pending = sum(1 for it in items if it.get("status") == "pending")
        return {
            "total": len(items),
            "done": done,
            "error": error,
            "pending": pending,
            "cache_hits": sum(1 for it in items if it.get("source") == "cache"),
            "processed": sum(1 for it in items if it.get("source") == "processed"),
            "reused": sum(1 for it in items if it.get("source") == "reused"),
        }

    def _process_one(
        self,
        batch: dict,
        item: dict,
        process: Callable[[str, dict], dict],
        *,
        force: bool = False,
    ) -> None:
        batch_id = batch["id"]
        started = time.monotonic()
        report = None
        if not force and result_cache_enabled():
            hit = self.cache.load(item["cache_key"])
            if hit is not None:
                report = hit["report"]
                item["source"] = "cache"
        if report is None:
            item["status"] = "pending"
            try:
                report = process(item["path"], batch.get("options") or {})
            except Exception as exc:  # noqa: BLE001 - one bad file must not abort the batch
                item["status"] = "error"
                item["source"] = "processed"
                item["error"] = f"{type(exc).__name__}: {exc}"
                item["elapsed_ms"] = int((time.monotonic() - started) * 1000)
                batch["stats"] = self._stats(batch["items"])
                self._save(batch)
                return
            item["source"] = "processed"
            self.cache.store(
                item["cache_key"],
                report,
                {"batch_id": batch_id, "item": item["id"], "versions": batch.get("versions") or {}},
            )
        item["status"] = "done"
        item["error"] = ""
        item["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        self._write_report(batch_id, item, report)
        batch["stats"] = self._stats(batch["items"])
        self._save(batch)

    def run(
        self,
        batch_id: str,
        process: Callable[[str, dict], dict],
        *,
        only_failed: bool = False,
        force: bool = False,
    ) -> dict:
        """Process the batch; with ``only_failed`` retry only failed items."""
        batch = self.get(batch_id)
        if batch is None:
            raise KeyError(f"unknown batch: {batch_id}")
        for item in batch["items"]:
            if only_failed and item.get("status") != "error":
                continue
            if item.get("status") == "done" and self._read_report(item) is not None and not force:
                item["source"] = "reused"
                continue
            self._process_one(batch, item, process, force=force)
        batch["stats"] = self._stats(batch["items"])
        self._save(batch)
        return batch

    def retry_failed(self, batch_id: str, process: Callable[[str, dict], dict]) -> dict:
        return self.run(batch_id, process, only_failed=True)

    def retry_item(self, batch_id: str, item_id: str, process: Callable[[str, dict], dict]) -> dict:
        """Retry exactly one item (the UI's per-row retry button)."""
        batch = self.get(batch_id)
        if batch is None:
            raise KeyError(f"unknown batch: {batch_id}")
        for item in batch["items"]:
            if item.get("id") == item_id:
                # force=True: a single retry is an explicit action, so do not
                # silently replay a possibly stale cache entry.
                self._process_one(batch, item, process, force=True)
                batch["stats"] = self._stats(batch["items"])
                self._save(batch)
                return batch
        raise KeyError(f"unknown item: {item_id}")

    def report(self, batch_id: str, item_id: str) -> Optional[dict]:
        batch = self.get(batch_id)
        if not batch:
            return None
        for item in batch["items"]:
            if item.get("id") == item_id:
                return self._read_report(item)
        return None


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
            if "progress" in fields:
                try:
                    fields["progress"] = max(int(fields["progress"]), int(job.get("progress") or 0))
                except (TypeError, ValueError):
                    pass
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
            JOBS_DIR.mkdir(parents=True, exist_ok=True)
            (JOBS_DIR / f"{job['id']}.json").write_text(
                json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        try:
            from .history_db import HistoryDB

            HistoryDB().upsert(job, has_report=(JOBS_DIR / job["id"] / "report.json").exists())
        except Exception:
            pass

    def mark_stale_as_interrupted(self) -> int:
        """Turn jobs left "running" by a previous process into retryable records.

        Persisted jobs survive a restart, but the threads that ran them do not.
        Without this, the history page keeps showing 30% forever.
        """
        changed = 0
        for p in JOBS_DIR.glob("*.json"):
            try:
                job = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if job.get("status") not in {"queued", "running"}:
                continue
            job.update(
                status="interrupted",
                stage="已中断（服务重启）",
                error="服务重启时任务还没跑完；如果原文本保留，可在历史页点“重新运行”",
                updated_at=datetime.now().isoformat(timespec="seconds"),
            )
            with self._lock:
                self._jobs[job["id"]] = job
            self._persist(job)
            changed += 1
        return changed

    def recent(self, limit: int = 6) -> list[dict]:
        try:
            from .history_db import HistoryDB

            db = HistoryDB()
            db.sync_dir(JOBS_DIR)
            rows = db.list(limit=limit)
            if rows:
                return rows
        except Exception:
            pass
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
                from .history_db import HistoryDB

                HistoryDB().delete(job_id)
            except OSError:
                pass
            job_dir = JOBS_DIR / job_id
            if job_dir.is_dir():
                shutil.rmtree(job_dir, ignore_errors=True)
                removed["reports"] += 1
        return removed


manager = JobManager()
