"""End-to-end tests for the FastAPI app.

The full sample paper is uploaded through ``/api/analyze``; the background job is
polled to completion and the resulting report structure is asserted. All outbound
HTTP is replaced by the deterministic Crossref double, so the suite is offline and
does not need ``DEEPSEEK_API_KEY`` (support degrades to ``not_checked``).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from citeguard import metadata_verify as mv
from citeguard.reference_parser import parse_reference

from helpers import (
    ROOT,
    crossref_message,
    crossref_records,
    install_fake_get,
    make_doi_handler,
    wait_for_job,
)

SAMPLE = ROOT / "web" / "static" / "samples" / "sample_paper.txt"


@pytest.fixture
def client(isolated_project):
    import web.app as webapp

    return TestClient(webapp.app)


@pytest.fixture
def plain_client():
    import web.app as webapp

    return TestClient(webapp.app)


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["version"]
    assert {".pdf", ".docx", ".txt", ".md"} <= set(payload["supported"])


def test_index_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "引证卫士" in resp.text


def test_about_page_renders(client):
    resp = client.get("/about")
    assert resp.status_code == 200
    assert "CiteGuard" in resp.text


def test_benchmark_api_serves_shipped_results(plain_client):
    resp = plain_client.get("/api/benchmark")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["available"] is True
    assert payload["n"] == 250
    assert "Exact" in (payload.get("per_class") or {})


def test_benchmark_page_renders(plain_client):
    resp = plain_client.get("/benchmark")
    assert resp.status_code == 200
    assert "CiteBench" in resp.text


def test_analyze_requires_input(client):
    resp = client.post("/api/analyze")
    assert resp.status_code == 400


def test_analyze_rejects_unsupported_suffix(client):
    resp = client.post("/api/analyze", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert resp.status_code == 400


def test_analyze_rejects_oversized_upload(client, monkeypatch, isolated_project):
    import web.app as webapp

    monkeypatch.setattr(webapp, "MAX_UPLOAD_BYTES", 8)
    resp = client.post(
        "/api/analyze",
        files={"file": ("big.txt", b"0123456789" * 4, "text/plain")},
    )
    assert resp.status_code == 413
    assert not list((isolated_project / "uploads").iterdir())


def test_unknown_job_and_report_return_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/report/nope").status_code == 404
    assert client.get("/report/nope").status_code == 404
    assert client.get("/api/report/nope/export").status_code == 404


def test_e2e_upload_sample_paper(client, monkeypatch, isolated_project, sample_refs):
    records = crossref_records(sample_refs)
    calls = install_fake_get(monkeypatch, mv, make_doi_handler(records))

    with SAMPLE.open("rb") as fh:
        resp = client.post(
            "/api/analyze",
            files={"file": (SAMPLE.name, fh, "text/plain")},
        )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    job = wait_for_job(client, job_id)
    assert job["status"] == "done", job
    assert job["progress"] == 100
    assert job["filename"] == SAMPLE.name
    assert job["error"] == ""

    resp = client.get(f"/api/report/{job_id}")
    assert resp.status_code == 200
    report = resp.json()

    assert report["job_id"] == job_id
    stats = report["stats"]
    assert stats["total"] == 12
    assert stats["intext_citations"] == 12
    assert stats["Exact"] == 8
    assert stats["Minor"] == 2
    assert stats["Major"] == 2
    assert stats["Unknown"] == 0
    assert stats["Exact"] + stats["Minor"] + stats["Major"] + stats["Unknown"] == stats["total"]
    assert 0 <= stats["avg_compliance"] <= 100
    assert 0 <= stats["risk_index"] <= 100
    # no key -> the judge is skipped and everything is reported as not_checked
    assert stats["support"]["not_checked"] == 12

    assert len(report["references"]) == 12
    expected_keys = {"index", "raw", "parsed", "verify", "compliance", "support"}
    for item in report["references"]:
        assert expected_keys <= set(item)
        assert item["verify"]["status"] in {"Exact", "Minor", "Major", "Unknown"}
        assert "score" in item["compliance"]
    assert calls, "the fake HTTP transport should have been exercised"
    assert {"judge_available", "cap", "candidates"} <= set(stats["support_meta"])
    assert stats["support_meta"]["judge_available"] is False

    # uploads are deleted after extraction (privacy)
    assert not list((isolated_project / "uploads").iterdir())

    # report HTML page
    page = client.get(f"/report/{job_id}")
    assert page.status_code == 200
    assert job_id in page.text
    assert "引证卫士" in page.text

    # exports
    md = client.get(f"/api/report/{job_id}/export?format=md")
    assert md.status_code == 200
    assert "markdown" in md.headers["content-type"]
    assert "# 引证卫士" in md.text

    as_json = client.get(f"/api/report/{job_id}/export?format=json")
    assert as_json.status_code == 200
    assert as_json.json()["job_id"] == job_id

    html = client.get(f"/api/report/{job_id}/export?format=html")
    assert html.status_code == 200
    assert "<!doctype html>" in html.text

    refs = client.get(f"/api/report/{job_id}/export?format=refs")
    assert refs.status_code == 200
    assert "text/plain" in refs.headers["content-type"]
    assert refs.text.startswith("[1] ")

    assert client.get(f"/api/report/{job_id}/export?format=pdf").status_code == 400


def test_e2e_pasted_reference_text(client, monkeypatch):
    ref = parse_reference(
        "[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/paste."
    )
    install_fake_get(monkeypatch, mv, make_doi_handler({ref.doi: crossref_message(ref)}))
    pasted = (
        "[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/paste.\n"
    )

    resp = client.post("/api/analyze", data={"text": pasted})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "done", job

    report = client.get(f"/api/report/{job_id}").json()
    assert report["stats"]["total"] == 1
    assert report["stats"]["Exact"] == 1
    assert report["input"] == "粘贴文本"


def test_e2e_upload_docx(client, monkeypatch, tmp_path):
    from docx import Document

    refs = [
        parse_reference("[1] 张三. 题名一[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/d1."),
        parse_reference("[2] 李四. 题名二[J]. 期刊, 2021, 65(3): 5-9. DOI: 10.1234/d2."),
    ]
    doc = Document()
    doc.add_paragraph("正文引用[1]与[2]。")
    doc.add_paragraph("参考文献")
    for ref in refs:
        doc.add_paragraph(ref.raw)
    path = tmp_path / "paper.docx"
    doc.save(path)

    records = {ref.doi: crossref_message(ref) for ref in refs}
    install_fake_get(monkeypatch, mv, make_doi_handler(records))

    with path.open("rb") as fh:
        resp = client.post(
            "/api/analyze",
            files={"file": (path.name, fh, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "done", job

    report = client.get(f"/api/report/{job_id}").json()
    assert report["stats"]["total"] == 2
    assert report["stats"]["Exact"] == 2
    assert report["stats"]["intext_citations"] == 2


def test_rejected_upload_does_not_create_job(client, isolated_project):
    import citeguard.jobs as jobs

    before = len(jobs.manager._jobs)
    client.post("/api/analyze", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert len(jobs.manager._jobs) == before
