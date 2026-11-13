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
    assert payload["offline"] is False
    assert {".pdf", ".docx", ".txt", ".md"} <= set(payload["supported"])


def test_landing_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "引证卫士" in resp.text
    assert 'href="/workspace"' in resp.text
    assert "让每一条引用" in resp.text
    # The landing page is standalone: it must not inherit the product rail.
    assert 'aria-label="主导航"' not in resp.text


def test_workspace_page_renders(client):
    resp = client.get("/workspace")
    assert resp.status_code == 200
    assert "引证卫士" in resp.text
    assert 'id="upload-form"' in resp.text
    assert 'id="start-btn"' in resp.text
    assert 'aria-label="主导航"' in resp.text
    assert "工作台" in resp.text
    # 功能页不应再出现落地页的营销段落
    assert "怎么工作" not in resp.text
    assert "产品数字" not in resp.text
    assert "让每一条引文" not in resp.text
    assert "最近报告" in resp.text


def test_history_page_renders(client):
    resp = client.get("/history")
    assert resp.status_code == 200
    text = resp.text
    assert "全部报告" in text
    assert "sk-" not in text


def test_history_groups_repeated_runs_of_the_same_file():
    import web.app as webapp

    jobs = [
        {"id": "c", "filename": "paper.pdf", "status": "done"},
        {"id": "b", "name": "paper.pdf", "status": "done"},
        {"id": "a", "filename": "other.pdf", "status": "done"},
    ]
    grouped = webapp._group_jobs_by_file(jobs)
    assert [job["id"] for job in grouped] == ["c", "a"]
    assert grouped[0]["runs"] == 2
    assert grouped[1]["runs"] == 1


def test_history_grouping_prefers_a_run_with_a_report():
    import web.app as webapp

    jobs = [
        {"id": "failed", "filename": "paper.pdf", "status": "error", "has_report": False},
        {"id": "ok", "filename": "paper.pdf", "status": "done", "has_report": True},
    ]
    grouped = webapp._group_jobs_by_file(jobs)
    assert [job["id"] for job in grouped] == ["ok"]
    assert grouped[0]["runs"] == 2


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
    assert "运行状态" in resp.text
    assert "标签质量审计" in resp.text
    assert "中文覆盖率试点" in resp.text
    assert "万方" in resp.text


def test_benchmark_status_never_leaks_secrets(plain_client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret-should-not-leak")
    resp = plain_client.get("/benchmark")
    assert resp.status_code == 200
    assert "运行状态" in resp.text
    assert "sk-secret-should-not-leak" not in resp.text


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
    assert 'id="triage-filter"' in page.text

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

    ris = client.get(f"/api/report/{job_id}/export?format=ris")
    assert ris.status_code == 200
    assert "x-research-info-systems" in ris.headers["content-type"]
    assert "TY  - " in ris.text and "ER  - " in ris.text

    enw = client.get(f"/api/report/{job_id}/export?format=enw")
    assert enw.status_code == 200
    assert "%0 " in enw.text

    bib = client.get(f"/api/report/{job_id}/export?format=bibtex")
    assert bib.status_code == 200
    assert "x-bibtex" in bib.headers["content-type"]
    assert bib.text.lstrip().startswith("@")

    csl = client.get(f"/api/report/{job_id}/export?format=csl")
    assert csl.status_code == 200
    assert "citationstyles.csl+json" in csl.headers["content-type"]
    import json as _json

    assert isinstance(_json.loads(csl.text), list)

    fixed = client.get(f"/api/report/{job_id}/fixed")
    assert fixed.status_code == 200
    fixed_data = fixed.json()
    assert fixed_data["summary"]["total"] == 12
    assert fixed_data["items"][0]["after"]
    fixed_txt = client.get(f"/api/report/{job_id}/fixed.txt")
    assert fixed_txt.status_code == 200
    assert fixed_txt.text.lstrip("\ufeff").startswith("引证卫士")

    import io
    import zipfile

    bundle = client.get(f"/api/report/{job_id}/bundle")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
        names = set(zf.namelist())
    assert {"report.json", "report.html", "report.ris", "report.enw", "manifest.json"} <= names

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

def test_compare_page_renders(plain_client):
    resp = plain_client.get("/compare")
    assert resp.status_code == 200
    assert "多篇文献对比" in resp.text


def test_compare_api_rejects_without_judge(plain_client, monkeypatch):
    from citeguard import compare

    monkeypatch.setattr(compare, "available", lambda: False)
    resp = plain_client.post(
        "/api/compare", files=[("files", ("a.txt", b"x", "text/plain"))]
    )
    assert resp.status_code == 503


def test_compare_api_validates_file_count(client, monkeypatch):
    from citeguard import compare

    monkeypatch.setattr(compare, "available", lambda: True)
    resp = client.post(
        "/api/compare", files=[("files", ("a.txt", b"x", "text/plain"))]
    )
    assert resp.status_code == 400


def test_compare_job_end_to_end(client, monkeypatch):
    from citeguard import compare

    monkeypatch.setattr(compare, "available", lambda: True)

    def fake_extract(text, *, use_cache=True):
        return {
            "fields": {key: f"{key}-内容" for key in compare.FIELD_KEYS},
            "model": "fake",
            "excerpt_chars": len(text),
            "latency_ms": 1,
            "cached": False,
        }

    monkeypatch.setattr(compare, "extract_profile", fake_extract)
    files = [
        ("files", ("paper_a.txt", "标题A\n摘要：研究问题A。".encode("utf-8"), "text/plain")),
        ("files", ("paper_b.txt", "标题B\n摘要：研究问题B。".encode("utf-8"), "text/plain")),
    ]
    resp = client.post("/api/compare", files=files)
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "done", job

    data = client.get(f"/api/compare/{job_id}").json()
    result = data["result"]
    assert [paper["name"] for paper in result["papers"]] == ["paper_a", "paper_b"]
    assert result["papers"][0]["fields"]["method"] == "method-内容"

    md = client.get(f"/api/compare/{job_id}/export?format=md")
    assert md.status_code == 200
    assert "多篇文献对比" in md.text
    csv_resp = client.get(f"/api/compare/{job_id}/export?format=csv")
    assert csv_resp.status_code == 200
    assert "字段" in csv_resp.text
    bad = client.get(f"/api/compare/{job_id}/export?format=bib")
    assert bad.status_code == 400


def test_discover_page_renders(plain_client):
    resp = plain_client.get("/discover")
    assert resp.status_code == 200
    assert "discover-form" in resp.text
    assert "discover-end" in resp.text
    assert "全选已加载" in resp.text


def test_discover_api_rejects_short_query(plain_client):
    resp = plain_client.post("/api/discover", json={"query": "a"})
    assert resp.status_code in (400, 422)


def test_discover_api_returns_results(plain_client, monkeypatch):
    import web.app as webapp
    def fake_search(query, **kwargs):
        assert query == "ai education"
        assert kwargs["limit"] == 5
        return {
            "query": query,
            "matched": 2,
            "results": [
                {"title": "Paper A", "authors": ["A"], "year": 2020, "venue": "V",
                 "doi": "10.1/a", "cited_by": 3, "is_oa": False, "oa_url": "",
                 "openalex_id": "W1"},
                {"title": "Paper B", "authors": [], "year": 2021, "venue": "",
                 "doi": "", "cited_by": 0, "is_oa": True, "oa_url": "https://x",
                 "openalex_id": "W2"},
            ],
        }

    monkeypatch.setattr(webapp.discover, "search_papers", fake_search)
    resp = plain_client.post("/api/discover", json={"query": "ai education", "limit": 5})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["matched"] == 2
    assert [item["title"] for item in payload["results"]] == ["Paper A", "Paper B"]


def test_discover_api_maps_upstream_error(plain_client, monkeypatch):
    import web.app as webapp
    def boom(query, **kwargs):
        raise webapp.discover.DiscoverError("OpenAlex 请求失败：500")

    monkeypatch.setattr(webapp.discover, "search_papers", boom)
    resp = plain_client.post("/api/discover", json={"query": "test topic"})
    assert resp.status_code == 502
    assert "OpenAlex" in resp.json()["detail"]


def test_discover_import_returns_counts(plain_client, monkeypatch):
    import web.app as webapp
    monkeypatch.setattr(
        webapp.discover,
        "import_entries",
        lambda items: {"added": len(items), "skipped": 1, "count": 7},
    )
    resp = plain_client.post(
        "/api/discover/import",
        json={"items": [{"title": "Paper A", "year": 2020}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["added"] == 1
    assert resp.json()["count"] == 7


def test_discover_import_rejects_empty(plain_client):
    resp = plain_client.post("/api/discover/import", json={"items": []})
    assert resp.status_code == 400


def test_discover_export_csv(plain_client, monkeypatch):
    import web.app as webapp
    monkeypatch.setattr(
        webapp.discover,
        "search_papers",
        lambda query, **kwargs: {"query": query, "matched": 1, "results": []},
    )
    monkeypatch.setattr(webapp.discover, "render_csv", lambda result: "title,doi\nA,\n")
    resp = plain_client.get("/api/discover/export?query=test")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")


def test_access_token_guard(plain_client, monkeypatch):
    import web.app as webapp

    monkeypatch.setattr(webapp.config, "ACCESS_TOKEN", "s3cret")
    plain_client.cookies.clear()
    assert plain_client.get("/api/library").status_code == 401
    assert (
        plain_client.get("/api/library", headers={"X-Access-Token": "s3cret"}).status_code == 200
    )
    # Opening a page with ?token= stores an HttpOnly cookie for later fetches.
    plain_client.cookies.clear()
    assert plain_client.get("/?token=s3cret").status_code == 200
    assert plain_client.get("/api/library").status_code == 200
    plain_client.cookies.clear()
    assert plain_client.get("/api/library").status_code == 401


def test_rate_limit_blocks_post_floods(plain_client, monkeypatch):
    import web.app as webapp

    monkeypatch.setattr(webapp.config, "ACCESS_TOKEN", "")
    monkeypatch.setattr(webapp.config, "RATE_LIMIT_PER_MIN", 2)
    webapp._rate_buckets.clear()
    # Empty library -> handler answers 400, but every POST still consumes a slot.
    for _ in range(2):
        assert plain_client.post("/api/library/enrich").status_code == 400
    resp = plain_client.post("/api/library/enrich")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "60"

def test_library_add_accepts_manual_entry(client):
    payload = {
        "title": "中文期刊题录手工补录测试",
        "authors": "张三；李四",
        "year": "2024",
        "venue": "某中文期刊",
    }
    resp = client.post("/api/library/add", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["added"] == 1 and body["count"] == 1

    again = client.post("/api/library/add", json=payload)
    assert again.status_code == 200
    assert again.json()["added"] == 0  # same title deduped

    listing = client.get("/api/library").json()
    assert listing["count"] == 1
    assert listing["entries"][0]["title"] == payload["title"]


def test_library_bulk_accepts_multiple_lines(client):
    text = "\n".join(
        [
            "[1] 张三. 中文引文核验方法[J]. 情报学报, 2024, 12(3): 10-20.",
            "[2] 李四. 另一篇中文论文[J]. 图书馆论坛, 2023, 43(2): 1-9.",
            "...",
        ]
    )
    resp = client.post("/api/library/bulk", json={"text": text})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["added"] == 2
    assert body["count"] == 2
    listing = client.get("/api/library").json()
    assert listing["count"] == 2
    titles = " ".join(e["title"] for e in listing["entries"])
    assert "中文引文核验方法" in titles and "另一篇中文论文" in titles

def test_library_demo_loads_bundled_offline_library(client):
    """One click must seed the 10-reference offline demo pack (conference fallback)."""
    resp = client.post("/api/library/demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 10
    assert body["added"] == 10
    listing = client.get("/api/library").json()
    assert listing["count"] == 10

    again = client.post("/api/library/demo")
    assert again.status_code == 200
    assert again.json()["added"] == 0  # idempotent


def test_compare_reports_positional_deltas():
    import web.app as webapp

    a = {
        "input": "old.pdf",
        "generated_at": "2026-10-27 10:00",
        "stats": {"total": 2, "Exact": 1, "Minor": 0, "Major": 1, "Unverified": 0,
                  "avg_compliance": 80, "risk_index": 30},
        "references": [
            {"parsed": {"title": "A"}, "verify": {"status": "Exact"}},
            {"parsed": {"title": "B"}, "verify": {"status": "Major"}},
        ],
    }
    b = {
        "input": "new.pdf",
        "generated_at": "2026-10-27 11:00",
        "stats": {"total": 2, "Exact": 2, "Minor": 0, "Major": 0, "Unverified": 0,
                  "avg_compliance": 95, "risk_index": 10},
        "references": [
            {"parsed": {"title": "A"}, "verify": {"status": "Exact"}},
            {"parsed": {"title": "B"}, "verify": {"status": "Exact"}},
        ],
    }
    out = webapp._compare_reports(a, b)
    assert out["stats"]["Major"]["delta"] == -1
    assert out["stats"]["avg_compliance"]["delta"] == 15
    assert out["changed"] == 1
    assert out["changes"][0]["from"] == "Major"
    assert out["changes"][0]["to"] == "Exact"
    assert out["positional"] is True


def test_compare_api_requires_two_reports(plain_client):
    r = plain_client.get("/api/compare?a=nope&b=missing")
    assert r.status_code == 404

def test_rerun_submits_retained_text(plain_client, monkeypatch):
    import web.app as webapp

    job = webapp.manager.create(filename="old.pdf")
    d = webapp.config.DATA_DIR / "jobs" / job["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "input.txt").write_text("保留的正文与参考文献", encoding="utf-8")
    (d / "options.json").write_text('{"support_max": 7}', encoding="utf-8")

    captured = {}
    monkeypatch.setattr(webapp.manager, "submit", lambda jid, fn, *a, **k: captured.update(jid=jid, args=a, kwargs=k))
    r = plain_client.post(f"/api/jobs/{job['id']}/rerun")
    assert r.status_code == 202
    body = r.json()
    assert body["rerun_of"] == job["id"]
    assert captured["jid"] == body["job_id"]
    assert captured["kwargs"]["text"] == "保留的正文与参考文献"
    assert captured["kwargs"]["support_max"] == 7


def test_rerun_without_retained_text_returns_409(plain_client):
    import web.app as webapp

    job = webapp.manager.create(filename="gone.pdf")
    r = plain_client.post(f"/api/jobs/{job['id']}/rerun")
    assert r.status_code == 409


def test_stale_running_job_becomes_interrupted(plain_client):
    import web.app as webapp

    job = webapp.manager.create(filename="crashed.pdf")
    webapp.manager.update(job["id"], status="running", progress=30)
    changed = webapp.manager.mark_stale_as_interrupted()
    assert changed >= 1
    again = webapp.manager.get(job["id"])
    assert again["status"] == "interrupted"
    assert "重启" in again["error"]

def test_support_check_endpoint_returns_verdict(plain_client, monkeypatch):
    import web.app as webapp

    monkeypatch.setattr(
        webapp.support,
        "judge_support",
        lambda claim, evidence: {
            "label": "partial",
            "confidence": 0.7,
            "reason": "只覆盖一个分句",
            "evidence": "原文一句",
            "audit": {"fully_covered": False},
        },
    )
    r = plain_client.post("/api/support/check", json={"claim": "A 通过 B 影响 C", "evidence": "A 影响 B"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["label"] == "partial"
    assert body["audit"]["fully_covered"] is False
    assert body["prompt_version"]


def test_support_check_validates_fields(plain_client):
    r = plain_client.post("/api/support/check", json={"claim": "只有主张"})
    assert r.status_code == 400
    r = plain_client.post("/api/support/check", json={"claim": "", "evidence": "x"})
    assert r.status_code == 400


def test_support_check_reports_unavailable(plain_client, monkeypatch):
    import web.app as webapp

    monkeypatch.setattr(webapp.support, "judge_support", lambda claim, evidence: None)
    r = plain_client.post("/api/support/check", json={"claim": "c", "evidence": "e"})
    assert r.status_code == 503
    assert r.json()["code"] == "judge_unavailable"


def test_support_check_refuses_offline(plain_client, monkeypatch):
    import web.app as webapp

    monkeypatch.setattr(webapp.config, "OFFLINE", True)
    r = plain_client.post("/api/support/check", json={"claim": "c", "evidence": "e"})
    assert r.status_code == 503
    assert r.json()["code"] == "offline"

def test_support_batch_validation(client):
    r = client.post("/api/support/batch", json={"items": []})
    assert r.status_code == 400
    r = client.post("/api/support/batch", json={"items": [{"claim": "x"}]})
    assert r.status_code == 400
    r = client.post("/api/support/batch", json={"items": [{"claim": "x", "evidence": "y"}] * 51})
    assert r.status_code == 400
def test_job_events_unknown_job(client):
    r = client.get("/api/jobs/not-a-job/events")
    assert r.status_code == 404


def test_job_events_stream_ends_on_done(client):
    from web import app as webapp
    job = webapp.manager.create("demo.pdf")
    webapp.manager.update(job["id"], status="done", progress=100, stage="完成")
    with client.stream("GET", f"/api/jobs/{job['id']}/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert '"status": "done"' in body
    assert '"progress": 100' in body
    lines = [ln for ln in body.splitlines() if ln.startswith("data: ")]
    assert lines and lines[0].startswith("data: {")


def test_batch_page_renders(plain_client):
    r = plain_client.get("/batch")
    assert r.status_code == 200
    assert "批量核验" in r.text
    assert "batch.js" in r.text
    assert "一次粘贴，最多 50 条" in r.text


def test_library_suggest_returns_ranked_candidates(client, monkeypatch):
    from citeguard import metadata_verify as mv
    cand = mv.Candidate(
        source="openalex",
        title="Attention Is All You Need",
        doi="10.1/x",
        year=2017,
        authors=["A. Vaswani"],
        raw={"cited_by_count": 100},
    )
    monkeypatch.setattr(mv, "_title_candidates", lambda ref: [cand])
    r = client.get("/api/library/suggest", params={"title": "Attention is all you need"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["candidates"][0]["sim"] == 1.0
    assert body["candidates"][0]["cited_by"] == 100


def test_models_api_lists_and_switches(plain_client, tmp_path, monkeypatch):
    import web.app as webapp

    monkeypatch.setenv("CITEGUARD_MODEL_REGISTRY", str(tmp_path / "reg.json"))
    monkeypatch.setattr(webapp, "_probe_judge", lambda entry: {"ok": False, "error": "down"})

    r = plain_client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is None
    assert any(m["id"] == "local-qwen3-14b" for m in body["models"])

    r = plain_client.post("/api/models/active", json={"id": "local-qwen3-14b"})
    assert r.status_code == 409

    r = plain_client.post("/api/models/active", json={"id": "local-qwen3-14b", "force": True})
    assert r.status_code == 200
    assert r.json()["active"] == "local-qwen3-14b"

    r = plain_client.post("/api/models/active", json={"id": "nope"})
    assert r.status_code == 400


def test_model_settings_page_renders(plain_client):
    r = plain_client.get("/settings/models")
    assert r.status_code == 200
    assert "判定模型" in r.text


def test_report_page_has_aria_live_verdict(client):
    response = client.get("/report/does-not-exist")
    # unknown job returns 404; static template check instead
    assert response.status_code == 404

    from pathlib import Path
    html = Path("web/templates/report.html").read_text(encoding="utf-8")
    assert 'id="verdict" aria-live="polite"' in html
    js = Path("web/static/js/report.js").read_text(encoding="utf-8")
    assert 'e.key === "j" || e.key === "k"' in js


def test_favicon_served_as_svg(plain_client):
    r = plain_client.get("/favicon.ico")
    assert r.status_code == 200
    assert "svg" in r.headers["content-type"]
    r2 = plain_client.get("/static/img/favicon.svg")
    assert r2.status_code == 200
    assert "<svg" in r2.text

def test_navigation_groups_are_clear(plain_client):
    r = plain_client.get("/workspace")
    assert r.status_code == 200
    assert 'aria-label="主导航"' in r.text
    # 五个任务分组；具体页面放在分组内的标签里，不再平铺在导航。
    for label in ("工作台", "报告", "题录库", "工具", "关于"):
        assert label in r.text
    assert "rail-more" not in r.text


def test_section_tabs_group_related_tasks(plain_client):
    workspace = plain_client.get("/workspace").text
    assert 'aria-label="功能分区"' in workspace
    for label in ("论文体检", "快速判定", "批量判定"):
        assert label in workspace

    history = plain_client.get("/history").text
    for label in ("全部报告", "批量聚合"):
        assert label in history

    tools = plain_client.get("/figure").text
    for label in ("图表核验", "多篇对比", "文献发现"):
        assert label in tools

    about = plain_client.get("/about").text
    for label in ("关于", "评测", "模型"):
        assert label in about


def test_report_checks_use_a_side_drawer():
    from pathlib import Path
    html = Path("web/templates/report.html").read_text(encoding="utf-8")
    assert 'id="checks-drawer"' in html
    assert 'id="open-checks"' in html
    assert 'id="advanced-checks"' not in html
    assert 'data-checks-pane="citation"' in html
    assert "检查明细" in html

def test_history_trend_endpoint_returns_daily_points(plain_client):
    r = plain_client.get("/api/history/trend", params={"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 7
    assert isinstance(body["points"], list)
    assert body["source"] == "data/jobs/*/report.json"


def test_chart_pages_load_the_chart_layer(plain_client):
    aggregate = plain_client.get("/aggregate").text
    assert 'id="ag-charts"' in aggregate
    assert "echarts.min.js" in aggregate
    assert "aggregate.js" in aggregate

    from pathlib import Path as _Path
    history_tpl = _Path("web/templates/history.html").read_text(encoding="utf-8")
    assert 'id="history-trend"' in history_tpl
    assert "echarts.min.js" in history_tpl
    assert "全部报告" in plain_client.get("/history").text

    library = plain_client.get("/library").text
    library_tpl = _Path("web/templates/library.html").read_text(encoding="utf-8")
    assert 'id="lib-chart-years"' in library_tpl
    assert 'id="library-year-data"' in library_tpl
    assert "\u672c\u5730\u9898\u5f55\u5e93" in library

    benchmark = plain_client.get("/benchmark").text
    assert "CiteBench-CN v2" in benchmark
    assert 'id="cb2-detection"' in benchmark
    assert "benchmark.js" in benchmark

    batch = plain_client.get("/batch").text
    assert 'id="bt-result"' in batch
    assert "echarts.min.js" in batch


def test_echarts_vendor_is_bundled():
    from pathlib import Path
    vendor = Path("web/static/vendor/echarts.min.js")
    assert vendor.exists()
    assert vendor.stat().st_size > 900_000


def test_long_lists_use_the_shared_pager():
    from pathlib import Path
    base = Path("web/templates/base.html").read_text(encoding="utf-8")
    assert "pager.js" in base
    pager = Path("web/static/js/pager.js").read_text(encoding="utf-8")
    assert "window.CGList" in pager
    assert "pager-btn" in pager

    for name, mount in (
        ("history.html", "history-pager"),
        ("library.html", "library-pager"),
        ("aggregate.html", "ag-pager"),
    ):
        html = Path("web/templates/" + name).read_text(encoding="utf-8")
        assert 'id="' + mount + '"' in html, name
    batch = Path("web/static/js/batch.js").read_text(encoding="utf-8")
    assert "bt-pager" in batch
    assert "CGList.create" in batch


def test_report_checks_drawer_is_wired():
    from pathlib import Path
    js = Path("web/static/js/report.js").read_text(encoding="utf-8")
    assert "checks-drawer" in js
    assert "openChecksDrawer" in js
    assert "data-checks-tab" in js

def test_citemap_routes_return_validated_payload(client):
    import shutil
    from citeguard import config

    src = ROOT / "data" / "evidence_map"
    dst = config.DATA_DIR / "evidence_map"
    if not dst.exists():
        shutil.copytree(src, dst)
    topics = client.get("/api/citemap/topics")
    assert topics.status_code == 200
    body = topics.json()
    assert body["schema_version"] == "1.0"
    assert len(body["topics"]) == 2
    topic_id = body["topics"][0]["topic_id"]
    payload = client.get(f"/api/citemap/{topic_id}")
    assert payload.status_code == 200
    assert payload.json()["topic"]["topic_id"] == topic_id
    assert len(payload.json()["papers"]) == 15
    missing = client.get("/api/citemap/not-a-topic")
    assert missing.status_code == 404
    assert missing.json()["known_topics"]
    page = client.get(f"/citemap?topic={topic_id}")
    assert page.status_code == 200
    assert "citemap-app" in page.text


def test_library_tags_api_roundtrip(client):
    payload = {"title": "带标签的中文题录", "authors": "张三", "year": "2024"}
    assert client.post("/api/library/add", json=payload).status_code == 200

    r = client.post("/api/library/0/tags", json={"mode": "replace", "tags": ["AI", "教育", "ai"]})
    assert r.status_code == 200, r.text
    assert r.json()["tags"] == ["AI", "教育"]

    r = client.post("/api/library/0/tags", json={"mode": "add", "tags": ["方法"]})
    assert r.json()["tags"] == ["AI", "教育", "方法"]

    r = client.post("/api/library/0/tags", json={"mode": "remove", "tags": ["教育"]})
    assert r.json()["tags"] == ["AI", "方法"]

    entries = client.get("/api/library").json()["entries"]
    assert entries[0]["tags"] == ["AI", "方法"]

    assert client.post("/api/library/99/tags", json={"tags": []}).status_code == 404
    assert client.post("/api/library/0/tags", json={"mode": "bogus", "tags": []}).status_code == 400
    too_many = ["t%d" % i for i in range(9)]
    assert client.post("/api/library/0/tags", json={"tags": too_many}).status_code == 400


def test_library_duplicates_api_groups_and_merges(client):
    import web.app as webapp
    from citeguard.local_library import Library, LibraryEntry

    lib = Library.load(webapp.config.LIBRARY_FILE)
    lib.entries.append(LibraryEntry(title="重复题录甲", doi="10.9999/dup", year=2020, tags=["a"]))
    lib.entries.append(LibraryEntry(title="重复题录乙", doi="10.9999/dup", year=2020, tags=["b"]))
    lib.save(webapp.config.LIBRARY_FILE)

    body = client.get("/api/library/duplicates").json()
    assert body["count"] == 1
    group = body["groups"][0]
    assert group["ids"] == [0, 1]
    assert "doi" in group["reason"].lower()

    merged = client.post(
        "/api/library/duplicates/merge",
        json={"keep_id": 0, "drop_ids": [1]},
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["merged"] == 1
    assert merged.json()["count"] == 1
    assert merged.json()["kept"]["tags"] == ["a", "b"]

    bad = client.post("/api/library/duplicates/merge", json={"keep_id": 0, "drop_ids": []})
    assert bad.status_code == 400


def test_library_page_exposes_tags_and_merge(client):
    html = client.get("/library").text
    assert 'id="library-dupes-btn"' in html
    assert 'id="library-tag-modal"' in html
    assert "标签" in html
