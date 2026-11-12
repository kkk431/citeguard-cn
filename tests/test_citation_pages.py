"""Page-view evidence: cited pages are rendered once and served with the report."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from citeguard import pipeline


@pytest.fixture
def client(isolated_project):
    import web.app as webapp

    return TestClient(webapp.app)


def test_save_citation_pages_renders_cited_pages_only(tmp_path, monkeypatch):
    from citeguard import pdf_extract

    monkeypatch.setattr(pdf_extract, "page_texts", lambda path: ["p1", "p2", "p3", "p4", "p5"])
    monkeypatch.setattr(pdf_extract, "render_page_png", lambda path, n, dpi=150: b"PNG" + bytes([n]))
    report = {"citations": {"items": [{"page": 2}, {"page": 2}, {"page": 5}, {"page": 0}, {}]}}

    saved = pipeline._save_citation_pages("paper.pdf", report, tmp_path)

    assert saved == [2, 5]
    assert report["citation_pages"] == [2, 5]
    assert (tmp_path / "pages" / "p2.png").read_bytes() == b"PNG\x02"
    assert (tmp_path / "pages" / "p5.txt").read_text(encoding="utf-8") == "p5"


def test_save_citation_pages_noop_without_pages(tmp_path):
    report = {"citations": {"items": [{"page": None}]}}
    assert pipeline._save_citation_pages("paper.pdf", report, tmp_path) == []
    assert "citation_pages" not in report


def test_page_view_endpoints(client, isolated_project):
    job = "pg1"
    folder = isolated_project / "jobs" / job
    (folder / "pages").mkdir(parents=True)
    (folder / "report.json").write_text(json.dumps({"references": []}), encoding="utf-8")
    (folder / "pages" / "p3.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (folder / "pages" / "p3.txt").write_text("这一页有引用 [1]。", encoding="utf-8")

    meta = client.get(f"/api/report/{job}/page/3")
    assert meta.status_code == 200
    body = meta.json()
    assert body["page"] == 3
    assert "引用" in body["text"]
    assert body["image"] == f"/api/report/{job}/page/3.png"

    img = client.get(f"/api/report/{job}/page/3.png")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"

    assert client.get(f"/api/report/{job}/page/9").status_code == 404
    assert client.get(f"/api/report/{job}/page/9.png").status_code == 404
