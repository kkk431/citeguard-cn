"""Local reference library: import formats, matching and verification."""
from __future__ import annotations

import json

import pytest

import citeguard.metadata_verify as mv
from citeguard.local_library import (
    Library,
    LibraryEntry,
    entry_to_candidate,
    parse_bibtex,
    parse_csl_json,
    parse_endnote,
    parse_library_text,
    parse_plain_references,
    parse_ris,
)
from citeguard.reference_parser import Reference
from helpers import FakeResponse, install_fake_get

RIS = """TY  - JOUR
TI  - 累积生态风险与青少年的学业和社交能力
AU  - 鲍振宙
AU  - 李董平
JO  - 心理发展与教育
PY  - 2014
VL  - 30
IS  - 5
SP  - 482
EP  - 495
ER  - 
"""

BIB = """@article{he2016,
  title = {Deep Residual Learning for Image Recognition},
  author = {He, Kaiming and Zhang, Xiangyu},
  journal = {CVPR},
  year = {2016},
  pages = {770--778},
}
"""

ENDNOTE = """%0 Journal Article
%T Self-Schemata and Processing Information
%A Markus, H
%J Journal of Personality
%D 1977
%V 35
%P 63-78
"""

CSL = json.dumps(
    [
        {
            "type": "article-journal",
            "title": "变量间的网络分析模型",
            "author": [{"family": "李", "given": "明"}],
            "issued": {"date-parts": [[2020]]},
            "container-title": "心理科学进展",
            "page": "1-10",
        }
    ],
    ensure_ascii=False,
)


def test_parse_ris_fields():
    entries = parse_ris(RIS)

    assert len(entries) == 1
    e = entries[0]
    assert e.title.startswith("累积生态风险")
    assert e.authors == ["鲍振宙", "李董平"]
    assert e.venue == "心理发展与教育"
    assert (e.year, e.volume, e.issue, e.pages) == (2014, "30", "5", "482-495")


def test_parse_bibtex_fields():
    entries = parse_bibtex(BIB)

    assert len(entries) == 1
    assert entries[0].title == "Deep Residual Learning for Image Recognition"
    assert entries[0].year == 2016
    assert entries[0].pages == "770-778"
    assert entries[0].authors == ["He, Kaiming", "Zhang, Xiangyu"]


def test_parse_endnote_fields():
    entries = parse_endnote(ENDNOTE)

    assert len(entries) == 1
    assert entries[0].venue == "Journal of Personality"
    assert entries[0].pages == "63-78"


def test_parse_csl_json_fields():
    entries = parse_csl_json(CSL)

    assert len(entries) == 1
    assert entries[0].year == 2020
    assert entries[0].venue == "心理科学进展"


def test_parse_plain_reference_list():
    entries = parse_plain_references("[1] 张三. 题名[J]. 期刊, 2020, 12(3): 45-56.")

    assert len(entries) == 1
    assert entries[0].title == "题名"
    assert entries[0].year == 2020


@pytest.mark.parametrize(
    "text,filename,expected",
    [(RIS, "a.ris", 1), (BIB, "a.bib", 1), (ENDNOTE, "a.enw", 1), (CSL, "a.json", 1)],
)
def test_parse_library_text_detects_format(text, filename, expected):
    assert len(parse_library_text(text, filename)) == expected


def test_library_search_and_year_tiebreak():
    lib = Library(
        [
            LibraryEntry(title="累积生态风险与大学生的健康危险行为", year=2019),
            LibraryEntry(title="累积生态风险与大学生的健康危险行为", year=2021),
        ]
    )

    hits = lib.search("累积生态风险与大学生的健康危险行为", year=2021)

    assert hits and hits[0][1].year == 2021
    assert lib.search("完全无关的另一个题目") == []


def test_entry_to_candidate_keeps_metadata():
    cand = entry_to_candidate(parse_ris(RIS)[0])

    assert cand.source == "local"
    assert cand.title.startswith("累积生态风险")
    assert cand.volume == "30"


def _ref(title="累积生态风险与青少年的学业和社交能力", year=2014, venue="心理发展与教育"):
    return Reference(
        raw=f"[1] 鲍振宙, 李董平. {title}[J]. {venue}, {year}, 30(5): 482-495.",
        index=1,
        title=title,
        authors=["鲍振宙", "李董平"],
        venue=venue,
        year=year,
        volume="30",
        issue="5",
        pages="482-495",
        doc_type="J",
    )


def test_verify_uses_library_match_as_exact(monkeypatch, isolated_cache):
    library = Library(parse_ris(RIS))
    calls = install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(500))

    result = mv.verify_reference(_ref(), library=library)

    assert result.status == "Exact"
    assert result.sources == ["local"]
    assert result.doi_status == "local"
    assert calls == []  # no network needed


def test_verify_flags_field_mismatch_from_library(monkeypatch, isolated_cache):
    library = Library(parse_ris(RIS))
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(500))

    result = mv.verify_reference(_ref(year=2016), library=library)

    assert result.status == "Minor"
    assert "year" in result.mismatches


def test_verify_falls_through_when_library_misses(monkeypatch, isolated_cache):
    library = Library(parse_ris(RIS))
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(404, {"status": "not found"}))

    result = mv.verify_reference(_ref(title="完全不同的另一个题目"), library=library)

    assert result.status == "Unverified"
    assert "local" not in result.sources


def test_verify_many_accepts_library(monkeypatch, isolated_cache):
    library = Library(parse_ris(RIS))
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(500))

    results = mv.verify_many([_ref()], progress=False, library=library)

    assert results[0].status == "Exact"


def test_pipeline_reports_library_stats(isolated_project, monkeypatch):
    from citeguard.pipeline import analyze_text

    library = Library(parse_ris(RIS))
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(500))
    text = (
        "本文讨论累积生态风险[1]。\n"
        "参考文献\n"
        "[1] 鲍振宙, 李董平. 累积生态风险与青少年的学业和社交能力[J]. 心理发展与教育, 2014, 30(5): 482-495.\n"
    )

    report = analyze_text(text, "test.txt", support_max=0, library=library)

    assert report["stats"]["library_entries"] == 1
    assert report["stats"]["library_hits"] == 1
    assert report["stats"]["Exact"] == 1
    assert report["references"][0]["verify"]["sources"] == ["local"]


# ---------------------------------------------------------------------------
# Web API: import / list / clear + analysis picks the library up
# ---------------------------------------------------------------------------

@pytest.fixture
def client(isolated_project, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from citeguard import config

    monkeypatch.setattr(config, "LIBRARY_FILE", tmp_path / "library.json")
    import web.app as webapp

    return TestClient(webapp.app)


def test_library_import_list_and_clear(client):
    resp = client.post(
        "/api/library/import",
        files={"file": ("cnki.ris", RIS.encode("utf-8"), "application/x-research-info-systems")},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 1
    assert client.get("/api/library").json()["count"] == 1
    page = client.get("/library")
    assert page.status_code == 200
    assert "累积生态风险" in page.text

    cleared = client.post("/api/library/clear")
    assert cleared.json()["count"] == 0
    assert client.get("/api/library").json()["count"] == 0


def test_library_import_rejects_unknown_format(client):
    resp = client.post(
        "/api/library/import",
        files={"file": ("data.bin", b"\x00\x01\x02", "application/octet-stream")},
    )

    assert resp.status_code == 400


def test_analysis_uses_imported_library(client, monkeypatch):
    client.post(
        "/api/library/import",
        files={"file": ("cnki.ris", RIS.encode("utf-8"), "application/x-research-info-systems")},
    )
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(500))

    resp = client.post(
        "/api/analyze",
        data={
            "text": "本文讨论累积生态风险[1]。\n参考文献\n"
            "[1] 鲍振宙, 李董平. 累积生态风险与青少年的学业和社交能力[J]. 心理发展与教育, 2014, 30(5): 482-495.\n",
            "support_max": "0",
        },
    )
    assert resp.status_code == 202, resp.text
    from helpers import wait_for_job

    job = wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "done", job
    report = client.get(f"/api/report/{job['id']}").json()
    assert report["stats"]["library_hits"] == 1
    assert report["stats"]["Exact"] == 1
