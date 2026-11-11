"""SQLite history index: sync, list, export, delete."""
from __future__ import annotations

import json
from pathlib import Path

from citeguard.history_db import HistoryDB


def _job(root: Path, job_id: str, updated: str, report: bool = False) -> None:
    data = {"id": job_id, "name": f"{job_id}.pdf", "created_at": "2026-11-11T10:00:00", "updated_at": updated, "status": "done", "stage": "完成", "progress": 100, "error": ""}
    (root / f"{job_id}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if report:
        (root / job_id).mkdir()
        (root / job_id / "report.json").write_text("{}", encoding="utf-8")


def test_sync_list_and_export(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    _job(jobs, "b", "2026-11-11T11:00:00", report=True)
    _job(jobs, "a", "2026-11-11T12:00:00")
    db = HistoryDB(tmp_path / "history.db")
    assert db.sync_dir(jobs, force=True) == 2
    rows = db.list(limit=10)
    assert [r["id"] for r in rows] == ["a", "b"]
    assert rows[1]["has_report"] == 1 and rows[0]["has_report"] == 0

    out = tmp_path / "export"
    assert db.export_json(out) == 2
    assert (out / "a.json").exists()

    db.delete("a")
    assert [r["id"] for r in db.list()] == ["b"]


def test_sync_skips_when_unchanged(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    _job(jobs, "x", "2026-11-11T11:00:00")
    db = HistoryDB(tmp_path / "history.db")
    assert db.sync_dir(jobs) == 1
    assert db.sync_dir(jobs) == 0
    _job(jobs, "y", "2026-11-11T13:00:00")
    assert db.sync_dir(jobs) == 2
