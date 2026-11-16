"""Citation-chain API: on-demand, cached, and honest about missing targets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import web.app as webapp
from citeguard import config, retraction


def _report() -> dict:
    base = {
        "parsed": {"title": "人工智能研究", "year": "2021", "doi": "10.1/a"},
        "verify": {"status": "Exact"},
    }
    return {
        "input": {"name": "paper.pdf"},
        "references": [
            {"index": 1, **base},
            {
                "index": 2,
                "parsed": {"title": "未匹配", "doi": "10.1/b"},
                "verify": {"status": "Unverified"},
            },
            {
                "index": 3,
                "parsed": {"title": "无 DOI", "doi": ""},
                "verify": {"status": "Exact"},
            },
        ],
    }


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    job = config.DATA_DIR / "jobs" / "jobchain"
    job.mkdir(parents=True)
    (job / "report.json").write_text(json.dumps(_report(), ensure_ascii=False), encoding="utf-8")
    return TestClient(webapp.app)


def test_chain_check_uses_only_matched_doi_references(client, monkeypatch):
    calls = []

    def fake(doi, max_refs=12):
        calls.append(doi)
        return {
            "status": "indirect",
            "checked": 2,
            "coverage": 1.0,
            "retracted": [{"id": "W1", "doi": "https://doi.org/10.1/old", "title": "Old"}],
            "title": "Citing",
            "detail": "found",
        }

    monkeypatch.setattr(retraction, "check_chain", fake)
    body = client.post("/api/report/jobchain/citation-chain").json()
    assert calls == ["10.1/a"]
    assert body["available"] is True
    assert body["summary"]["indirect"] == 1
    assert body["items"][0]["index"] == 1

    cached = client.get("/api/report/jobchain/citation-chain").json()
    assert cached["cached"] is True
    assert cached["summary"]["indirect"] == 1


def test_chain_is_unavailable_without_matched_doi(client):
    # Replace the report with one that has no eligible reference.
    job = config.DATA_DIR / "jobs" / "jobchain"
    (job / "report.json").write_text(
        json.dumps({"references": [{"index": 1, "parsed": {}, "verify": {"status": "Exact"}}]}),
        encoding="utf-8",
    )
    body = client.post("/api/report/jobchain/citation-chain").json()
    assert body["available"] is False
    assert "DOI" in body["reason"]


def test_chain_deduplicates_repeated_dois(client, monkeypatch):
    calls = []

    def fake(doi, max_refs=12):
        calls.append(doi)
        return {
            "status": "clean",
            "checked": 1,
            "coverage": 1.0,
            "retracted": [],
            "title": "Same work",
            "detail": "ok",
        }

    monkeypatch.setattr(retraction, "check_chain", fake)
    report = {
        "references": [
            {
                "index": 1,
                "parsed": {"title": "同一篇", "doi": "https://doi.org/10.1/same"},
                "verify": {"status": "Exact"},
            },
            {
                "index": 2,
                "parsed": {"title": "同一篇（重复）", "doi": "10.1/SAME"},
                "verify": {"status": "Minor"},
            },
        ]
    }
    job = config.DATA_DIR / "jobs" / "jobchain"
    (job / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    body = client.post("/api/report/jobchain/citation-chain").json()
    assert calls == ["10.1/same"]
    assert body["summary"]["checked"] == 1


def test_chain_404_when_report_is_missing(client):
    assert client.post("/api/report/nope/citation-chain").status_code == 404
    assert client.get("/api/report/nope/citation-chain").status_code == 404
