"""SQLite index for job history (JSON stays the export/backup format).

The per-job JSON files remain authoritative so existing installs keep working;
this index makes /history and /api/jobs O(log n) instead of globbing and parsing
every JSON file on each page load. Export back to JSON stays supported.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    name TEXT,
    created_at TEXT,
    updated_at TEXT,
    status TEXT,
    stage TEXT,
    progress INTEGER DEFAULT 0,
    error TEXT,
    filename TEXT,
    has_report INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

FIELDS = ("id", "name", "filename", "created_at", "updated_at", "status", "stage", "progress", "error")


def default_path() -> Path:
    override = os.environ.get("CITEGUARD_HISTORY_DB")
    if override:
        return Path(override)
    return config.DATA_DIR / "history.db"


class HistoryDB:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_path()

    def _conn(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "filename" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN filename TEXT")
        return conn

    def upsert(self, job: dict, has_report: bool = False) -> None:
        row = {k: job.get(k) for k in FIELDS}
        row["progress"] = int(job.get("progress") or 0)
        row["has_report"] = 1 if has_report else 0
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs (id,name,filename,created_at,updated_at,status,stage,progress,error,has_report) "
                "VALUES (:id,:name,:filename,:created_at,:updated_at,:status,:stage,:progress,:error,:has_report) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, created_at=excluded.created_at, "
                "filename=excluded.filename, updated_at=excluded.updated_at, status=excluded.status, stage=excluded.stage, "
                "progress=excluded.progress, error=excluded.error, has_report=excluded.has_report",
                row,
            )

    def delete(self, job_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def list(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY coalesce(updated_at, created_at) DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, job_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def export_json(self, dest: str | Path) -> int:
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        rows = self.list(limit=100000)
        for row in rows:
            (dest / f"{row['id']}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(rows)

    def _meta(self, key: str) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else ""

    def _synced_at(self) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key='synced_at'").fetchone()
        try:
            return float(row["value"]) if row else 0.0
        except (TypeError, ValueError):
            return 0.0

    def sync_dir(self, jobs_dir: str | Path, force: bool = False) -> int:
        """Import job JSON files whose mtime is newer than the last sync."""
        jobs_dir = Path(jobs_dir).resolve()
        paths = list(jobs_dir.glob("*.json"))
        if not paths:
            return 0
        stored_dir = self._meta("jobs_dir")
        if stored_dir and stored_dir != str(jobs_dir):
            # The DB is being pointed at a different jobs directory (tests,
            # alternate installs): rebuild instead of mixing two histories.
            with self._conn() as conn:
                conn.execute("DELETE FROM jobs")
            force = True
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key,value) VALUES ('jobs_dir', ?)", (str(jobs_dir),))
        newest = max(p.stat().st_mtime for p in paths)
        if not force and newest <= self._synced_at():
            return 0
        count = 0
        for p in paths:
            try:
                job = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not job.get("id"):
                continue
            has_report = (jobs_dir / job["id"] / "report.json").exists()
            self.upsert(job, has_report=has_report)
            count += 1
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key,value) VALUES ('synced_at', ?)", (str(newest),))
        return count
