"""Repair loop API: preview -> apply -> undo must be reversible and honest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import web.app as webapp
from citeguard import config


def _report() -> dict:
    return {
        "schema": "citeguard.report/1",
        "input": {"name": "paper.pdf", "characters": 100},
        "stats": {"total": 2, "Exact": 2, "Minor": 0, "Major": 0, "Unverified": 0},
        "references": [
            {
                "index": 1,
                "raw": "张三. 人工智能研究. 计算机学报, 2021, 44(1): 1-10",
                "parsed": {
                    "authors": ["张三"],
                    "title": "人工智能研究",
                    "year": "2021",
                    "venue": "计算机学报",
                    "volume": "44",
                    "issue": "1",
                    "pages": "1-10",
                    "doc_type": "",
                },
                "verify": {"status": "Exact", "title_sim": 1.0},
                "format": {"score": 90, "issues": []},
            },
            {
                "index": 2,
                "raw": "李四. 机器学习综述. 软件学报, 2022, 33(2): 20-30",
                "parsed": {
                    "authors": ["李四"],
                    "title": "机器学习综述",
                    "year": "2022",
                    "venue": "软件学报",
                    "volume": "33",
                    "issue": "2",
                    "pages": "20-30",
                    "doc_type": "",
                },
                "verify": {"status": "Exact", "title_sim": 1.0},
                "format": {"score": 90, "issues": []},
            },
        ],
    }


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    job = config.DATA_DIR / "jobs" / "jobrepair"
    job.mkdir(parents=True)
    (job / "report.json").write_text(json.dumps(_report(), ensure_ascii=False), encoding="utf-8")
    return TestClient(webapp.app)


def test_preview_apply_and_undo_roundtrip(client, tmp_path, monkeypatch):
    job = config.DATA_DIR / "jobs" / "jobrepair"
    preview = client.get("/api/report/jobrepair/repair/preview").json()
    assert preview["summary"]["total"] == 2
    assert preview["summary"]["to_apply"] >= 1
    patch_id = preview["patch_id"]

    applied = client.post(
        "/api/report/jobrepair/repair/apply",
        json={"patch_id": patch_id},
    ).json()
    assert applied["applied"] >= 1
    assert (job / "report.fixed.json").exists()
    assert (job / "repair.json").exists()

    state = client.get("/api/report/jobrepair/repair/state").json()
    assert state["fixed"] == applied["applied"]
    assert state["undo"]["available"] is True

    undo = client.post(
        "/api/report/jobrepair/repair/undo",
        json={"patch_id": patch_id},
    ).json()
    assert undo["undone"] == applied["applied"]
    assert undo["state"]["fixed"] == 0
    assert not (job / "report.fixed.json").exists()
    assert not (job / "repair.json").exists()


def test_apply_is_idempotent_and_rejects_expired_undo(client):
    preview = client.get("/api/report/jobrepair/repair/preview").json()
    first = client.post(
        "/api/report/jobrepair/repair/apply", json={"patch_id": preview["patch_id"]}
    ).json()
    assert first["applied"] >= 1
    again = client.post(
        "/api/report/jobrepair/repair/apply", json={"patch_id": preview["patch_id"]}
    ).json()
    assert again["applied"] == 0
    assert again["already_applied"] is True

    repair = config.DATA_DIR / "jobs" / "jobrepair" / "repair.json"
    store = json.loads(repair.read_text(encoding="utf-8"))
    store["expires_at"] = "2000-01-01T00:00:00+00:00"
    repair.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    resp = client.post(
        "/api/report/jobrepair/repair/undo", json={"patch_id": preview["patch_id"]}
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "undo_expired"


def test_preview_rejects_bad_index(client):
    resp = client.get("/api/report/jobrepair/repair/preview", params={"indexes": "99"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_index"
    resp = client.get("/api/report/jobrepair/repair/preview", params={"indexes": "x"})
    assert resp.status_code == 400


def test_repair_state_404_when_report_missing(client):
    assert client.get("/api/report/nope/repair/state").status_code == 404
