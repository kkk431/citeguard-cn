import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import citeguard.metadata_verify as mv
import web.app as webapp


def _write_report(project, job_id="repljob"):
    d = project / "jobs" / job_id
    d.mkdir(parents=True, exist_ok=True)
    report = {
        "references": [
            {
                "index": 1,
                "raw": "Old, 2020. Wrong paper[J]. J, 2020.",
                "parsed": {"title": "Wrong paper", "authors": ["Old"], "year": 2020},
                "verify": {"status": "Minor"},
                "cited_in": [{"sentence": "某研究发现这个现象非常普遍。", "key": "[1]", "page": 2}],
                "support": {"claim": "某研究发现这个现象非常普遍。"},
            }
        ]
    }
    (d / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return job_id


def test_replacement_endpoint_returns_candidates(isolated_project, monkeypatch):
    job_id = _write_report(isolated_project)
    monkeypatch.setattr(
        mv,
        "search_openalex",
        lambda query, limit=10: [
            SimpleNamespace(
                title="A supporting paper",
                authors=["Smith J"],
                year=2021,
                venue="Journal of Tests",
                doi="10.1/abc",
                source="openalex",
                url="https://doi.org/10.1/abc",
                raw={},
            )
        ],
    )
    client = TestClient(webapp.app)
    r = client.get(f"/api/report/{job_id}/replacement?index=1")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert "[J]" in data["candidates"][0]["entry"]
    assert "线索" in data["note"]


def test_replacement_endpoint_rejects_bad_index_and_empty_query(isolated_project):
    job_id = _write_report(isolated_project)
    client = TestClient(webapp.app)
    assert client.get(f"/api/report/{job_id}/replacement?index=9").status_code == 404
    d = isolated_project / "jobs" / job_id
    report = json.loads((d / "report.json").read_text(encoding="utf-8"))
    report["references"][0]["cited_in"] = []
    report["references"][0]["support"] = {}
    report["references"][0]["parsed"] = {"title": "x"}
    (d / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert client.get(f"/api/report/{job_id}/replacement?index=1").status_code == 400
