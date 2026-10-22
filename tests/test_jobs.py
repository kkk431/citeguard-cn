"""Tests for the in-process job manager used by the web app."""
from __future__ import annotations

import json
import time

import pytest

from citeguard import jobs


def _wait_done(manager, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = manager.get(job_id)
        if state and state["status"] in {"done", "error"}:
            return state
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not settle: {manager.get(job_id)}")


@pytest.fixture
def manager():
    mgr = jobs.JobManager(max_workers=1)
    yield mgr
    mgr._executor.shutdown(wait=True)


def test_create_and_get_job(manager, isolated_project):
    job = manager.create(filename="paper.txt")
    assert len(job["id"]) == 12
    assert job["status"] == "queued"
    assert manager.get(job["id"])["filename"] == "paper.txt"
    assert (jobs.JOBS_DIR / f"{job['id']}.json").exists()


def test_update_persists_to_disk(manager, isolated_project):
    job = manager.create(filename="paper.txt")
    manager.update(job["id"], progress=42, stage="核验", status="running")

    reloaded = json.loads((jobs.JOBS_DIR / f"{job['id']}.json").read_text(encoding="utf-8"))
    assert reloaded["progress"] == 42
    assert reloaded["stage"] == "核验"
    assert reloaded["status"] == "running"


def test_update_ignores_unknown_job(manager, isolated_project):
    manager.update("does-not-exist", progress=10)  # must not raise
    assert manager.get("does-not-exist") is None


def test_submit_success_marks_done(manager, isolated_project):
    job = manager.create(filename="paper.txt")

    def task(job_id):
        manager.update(job_id, progress=50)

    manager.submit(job["id"], task)
    state = _wait_done(manager, job["id"])
    assert state["status"] == "done"
    assert state["progress"] == 100
    assert state["stage"] == "完成"


def test_submit_failure_records_error(manager, isolated_project):
    job = manager.create(filename="paper.txt")

    def task(job_id):
        raise ValueError("boom")

    manager.submit(job["id"], task)
    state = _wait_done(manager, job["id"])
    assert state["status"] == "error"
    assert state["error"] == "ValueError: boom"
    assert state["stage"] == "失败"


def test_get_recovers_job_from_disk(isolated_project):
    other = jobs.JobManager(max_workers=1)
    try:
        job = other.create(filename="disk.txt")
        # Simulate a restart: fresh manager with no in-memory state.
        fresh = jobs.JobManager(max_workers=1)
        try:
            recovered = fresh.get(job["id"])
            assert recovered is not None and recovered["filename"] == "disk.txt"
        finally:
            fresh._executor.shutdown(wait=True)
    finally:
        other._executor.shutdown(wait=True)


def test_recent_jobs_listing(manager, isolated_project):
    first = manager.create(filename="a.txt")
    second = manager.create(filename="b.txt")
    recent = manager.recent(limit=10)
    assert {j["id"] for j in recent} >= {first["id"], second["id"]}
    assert all("filename" in j for j in recent)
