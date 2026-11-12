"""Triage state (todo / fixed / ignored) and its report APIs."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from citeguard import triage


def test_set_and_load_state():
    triage.set_state("job1", 2, "todo", "先核对 DOI")
    out = triage.load("job1")
    assert out["counts"]["todo"] == 1
    assert out["items"]["2"]["note"] == "先核对 DOI"

    triage.set_state("job1", 2, "fixed")
    out = triage.load("job1")
    assert out["counts"] == {"todo": 0, "fixed": 1, "ignored": 0}


def test_invalid_state_and_index_rejected():
    with pytest.raises(ValueError):
        triage.set_state("job1", 1, "done")
    with pytest.raises(ValueError):
        triage.set_state("job1", 0, "todo")
    with pytest.raises(ValueError):
        triage.load("../etc/passwd")


def test_auto_mark_fixed_keeps_ignored_and_is_idempotent():
    triage.set_state("job2", 1, "ignored")
    triage.set_state("job2", 2, "todo")
    changed = triage.auto_mark_fixed("job2", [1, 2, 2])
    assert changed == 1
    out = triage.load("job2")
    assert out["items"]["1"]["state"] == "ignored"
    assert out["items"]["2"]["state"] == "fixed"
    assert triage.auto_mark_fixed("job2", [2]) == 0


@pytest.fixture
def client(isolated_project):
    import web.app as webapp

    return TestClient(webapp.app)


def _report(data_dir, job_id, refs):
    folder = data_dir / "jobs" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"references": refs, "stats": {"total": len(refs)}}
    (folder / "report.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_triage_api_roundtrip(client, isolated_project):
    _report(isolated_project, "tri1", [{"index": 1, "parsed": {"title": "A"}, "verify": {"status": "Minor"}}])

    assert client.get("/api/report/missing/triage").status_code == 404
    resp = client.post("/api/report/tri1/triage", json={"index": 1, "state": "todo"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["counts"]["todo"] == 1

    bad = client.post("/api/report/tri1/triage", json={"index": 1, "state": "nope"})
    assert bad.status_code == 400
    got = client.get("/api/report/tri1/triage").json()
    assert got["items"]["1"]["state"] == "todo"


def test_diff_auto_closes_resolved_entries(client, isolated_project):
    _report(
        isolated_project,
        "old1",
        [{"index": 1, "parsed": {"title": "X"}, "verify": {"status": "Unverified"},
          "compliance": {"issues": [{"level": "error", "field": "volume", "message": "缺少卷"}]}}],
    )
    _report(
        isolated_project,
        "new1",
        [{"index": 1, "parsed": {"title": "X"}, "verify": {"status": "Exact"}, "compliance": {"issues": []}}],
    )
    triage.set_state("new1", 1, "todo")
    resp = client.get("/api/report/new1/diff?against=old1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["resolved"] == 1
    assert body["auto_closed"] == 1
    assert triage.load("new1")["items"]["1"]["state"] == "fixed"
