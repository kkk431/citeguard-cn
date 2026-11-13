"""Local reference library: import formats, matching and verification."""
from __future__ import annotations

import json
import sqlite3

import pytest

import citeguard.metadata_verify as mv
from citeguard import library_db
from citeguard.local_library import (
    Library,
    LibraryEntry,
    LibraryError,
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


def test_library_export_roundtrip_bibtex_and_ris():
    from citeguard.local_library import to_bibtex, to_ris

    library = Library(parse_ris(RIS))

    bib = to_bibtex(library)
    ris = to_ris(library)

    assert "@article{" in bib and "累积生态风险" in bib
    assert "TY  - JOUR" in ris and "ER  - " in ris
    assert len(parse_library_text(bib, "x.bib")) == 1
    assert len(parse_library_text(ris, "x.ris")) == 1


def test_library_export_endpoints(client):
    client.post(
        "/api/library/import",
        files={"file": ("cnki.ris", RIS.encode("utf-8"), "application/x-research-info-systems")},
    )

    bib = client.get("/api/library/export?format=bibtex")
    ris = client.get("/api/library/export?format=ris")
    bad = client.get("/api/library/export?format=xlsx")

    assert bib.status_code == 200 and "@article{" in bib.text
    assert ris.status_code == 200 and "TY  - JOUR" in ris.text
    assert bad.status_code == 400


def test_library_export_empty_returns_404(client):
    assert client.get("/api/library/export?format=bibtex").status_code == 404


def test_parse_ris_fields():
    entries = parse_ris(RIS)

    assert len(entries) == 1
    e = entries[0]
    assert e.title.startswith("累积生态风险")
    assert e.authors == ["鲍振宙", "李董平"]
    assert e.venue == "心理发展与教育"
    assert (e.year, e.volume, e.issue, e.pages) == (2014, "30", "5", "482-495")


def test_parse_ris_abstract_is_kept():
    text = (
        "TY  - JOUR\nTI  - 题名\nAU  - 张三\nJO  - 期刊\nPY  - 2020\n"
        "AB  - 本文研究发现累积生态风险显著提高青少年的健康危险行为。\nER  - \n"
    )

    entry = parse_ris(text)[0]

    assert entry.abstract.startswith("本文研究发现")
    assert entry_to_candidate(entry).abstract.startswith("本文研究发现")


def test_library_abstract_feeds_support_judge(isolated_project, monkeypatch):
    from citeguard import support as sp
    from citeguard.pipeline import analyze_text
    from helpers import deepseek_support_response, install_fake_post

    ris = (
        "TY  - JOUR\nTI  - 累积生态风险与青少年的学业和社交能力\nAU  - 鲍振宙\n"
        "JO  - 心理发展与教育\nPY  - 2014\nVL  - 30\nIS  - 5\nSP  - 482\nEP  - 495\n"
        "AB  - 累积生态风险显著正向预测青少年的学业和社交能力。\nER  - \n"
    )
    library = Library(parse_ris(ris))
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(500))
    install_fake_post(monkeypatch, sp, lambda url, body: deepseek_support_response("support"))
    monkeypatch.setattr(sp.config, "DEEPSEEK_API_KEY", "sk-test")

    text = (
        "累积生态风险显著提高青少年的学业和社交能力[1]。\n"
        "参考文献\n"
        "[1] 鲍振宙, 李董平. 累积生态风险与青少年的学业和社交能力[J]. 心理发展与教育, 2014, 30(5): 482-495.\n"
    )
    report = analyze_text(text, "test.txt", support_max=5, library=library)

    assert report["stats"]["support_meta"]["candidates"] >= 1
    assert report["references"][0]["support"]["label"] == "support"


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


def test_abstract_from_candidates_requires_close_match():
    from citeguard.local_library import abstract_from_candidates, LibraryEntry
    from citeguard.metadata_verify import Candidate

    entry = LibraryEntry(title="累积生态风险与青少年的学业和社交能力", year=2014)
    wrong = Candidate(source="openalex", title="累积生态风险与青少年健康行为", year=2014, abstract="wrong")
    right = Candidate(source="openalex", title=entry.title, year=2014, abstract="right abstract")
    miscal = Candidate(source="openalex", title=entry.title, year=2009, abstract="wrong year")

    assert abstract_from_candidates(entry, [wrong]) == ""
    assert abstract_from_candidates(entry, [miscal]) == ""
    assert abstract_from_candidates(entry, [wrong, right]) == "right abstract"


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
    # This export has no abstract: metadata checks still work, but the
    # claim-support judge needs one, so the UI must say so.
    assert resp.json()["with_abstract"] == 0
    assert resp.json()["imported_no_abstract"] == 1
    assert client.get("/api/library").json()["count"] == 1
    page = client.get("/library")
    assert page.status_code == 200
    assert "累积生态风险" in page.text
    assert "没有摘要" in page.text

    cleared = client.post("/api/library/clear")
    assert cleared.json()["count"] == 0
    assert client.get("/api/library").json()["count"] == 0


def test_library_import_counts_abstracts(client):
    ris_with_abstract = RIS.replace("ER  - ", "AB  - 本文检验了累积生态风险的调节效应。\nER  - ")
    resp = client.post(
        "/api/library/import",
        files={"file": ("cnki-abstract.ris", ris_with_abstract.encode("utf-8"), "application/x-research-info-systems")},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["with_abstract"] == 1
    assert resp.json()["imported_no_abstract"] == 0
    page = client.get("/library")
    assert "没有摘要" not in page.text


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


# ---------------------------------------------------------------------------
# Web API: management table (list / delete / enrich) added in 0.3.7
# ---------------------------------------------------------------------------

def _import(client, ris_text: str, filename: str = "cnki.ris"):
    return client.post(
        "/api/library/import",
        files={"file": (filename, ris_text.encode("utf-8"), "application/x-research-info-systems")},
    )


def test_library_api_lists_all_entries_with_stable_indexes(client):
    second = RIS.replace("累积生态风险与青少年的学业和社交能力", "自我决定理论视角下的学习动机研究")
    _import(client, RIS)
    _import(client, second, "second.ris")

    payload = client.get("/api/library?limit=2000").json()
    assert payload["count"] == 2
    assert payload["missing_abstract"] == 2
    assert [e["index"] for e in payload["entries"]] == [0, 1]
    assert payload["entries"][0]["title"].startswith("累积生态风险")
    assert payload["truncated"] is False

    page = client.get("/api/library?limit=1").json()
    assert page["count"] == 2
    assert len(page["entries"]) == 1
    assert page["truncated"] is True


def test_library_delete_removes_one_entry_and_reports_missing_index(client):
    _import(client, RIS)
    _import(client, RIS.replace("累积生态风险与青少年的学业和社交能力", "第二篇测试题录"), "two.ris")

    resp = client.delete("/api/library/0")
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 1
    remaining = client.get("/api/library").json()
    assert remaining["count"] == 1
    assert "第二篇测试题录" in remaining["entries"][0]["title"]

    assert client.delete("/api/library/9").status_code == 404


def test_library_import_reports_added_and_skipped_duplicates(client):
    first = _import(client, RIS)
    assert first.json()["added"] == 1
    assert first.json()["skipped"] == 0

    again = _import(client, RIS)
    assert again.status_code == 200
    assert again.json()["imported"] == 1
    assert again.json()["added"] == 0
    assert again.json()["skipped"] == 1
    assert again.json()["count"] == 1


def test_library_enrich_endpoint_persists_filled_abstract(client, monkeypatch):
    _import(client, RIS)
    import web.app as webapp

    def fake_enrich(library, limit=10):
        entry = library.entries[0]
        entry.abstract = "从公开元数据补来的摘要"
        return {
            "tried": 1,
            "enriched": 1,
            "missing": 0,
            "errors": 0,
            "remaining": 0,
            "total_missing": 1,
            "details": [{"title": entry.title, "status": "enriched", "chars": 12}],
        }

    monkeypatch.setattr(webapp, "enrich_missing", fake_enrich)
    resp = client.post("/api/library/enrich?limit=3")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["enriched"] == 1
    assert payload["remaining"] == 0
    assert payload["with_abstract"] == 1

    listed = client.get("/api/library").json()
    assert listed["with_abstract"] == 1
    assert listed["missing_abstract"] == 0
    # Persisted, not just mutated in memory.
    assert client.get("/api/library").json()["entries"][0]["abstract"] == "从公开元数据补来的摘要"


def test_library_enrich_empty_library_is_a_400(client):
    assert client.post("/api/library/enrich").status_code == 400


def test_add_dedupes_by_doi_even_with_different_titles():
    from citeguard.local_library import Library, LibraryEntry

    lib = Library()
    lib.add([LibraryEntry(title="A study of things", doi="10.1/ABC")])
    lib.add([LibraryEntry(title="A study of things (preprint)", doi="10.1/abc")])
    assert len(lib) == 1
    lib.add([LibraryEntry(title="Another paper", doi="10.2/xyz")])
    assert len(lib) == 2


# ---------------------------------------------------------------------------
# Tags and duplicate merge (library format version 2)
# ---------------------------------------------------------------------------

def _entry(title="A study of citation practice", year=2020, tags=None, **fields):
    return LibraryEntry(title=title, year=year, tags=list(tags or []), **fields)


def test_tags_set_add_remove_and_normalise():
    lib = Library([_entry()])

    entry = lib.set_tags(0, ["  方法 ", "方法", "综述", ""])
    assert entry.tags == ["方法", "综述"]
    assert entry.to_dict()["tags"] == ["方法", "综述"]

    entry = lib.add_tags(0, ["方法", "REVIEW", "review"])
    assert entry.tags == ["方法", "综述", "REVIEW"]

    entry = lib.remove_tags(0, ["review", "missing"])
    assert entry.tags == ["方法", "综述"]


def test_tags_reject_oversized_too_many_and_non_string_values():
    lib = Library([_entry()])

    with pytest.raises(LibraryError, match="最多 8 个"):
        lib.set_tags(0, [f"t{i}" for i in range(9)])
    with pytest.raises(LibraryError, match="24 个字符"):
        lib.set_tags(0, ["x" * 25])
    with pytest.raises(LibraryError):
        lib.set_tags(0, "not-a-list")
    with pytest.raises(LibraryError):
        lib.set_tags(0, [1])
    assert lib.entries[0].tags == []

    lib.set_tags(0, [f"t{i}" for i in range(8)])
    with pytest.raises(LibraryError, match="最多 8 个"):
        lib.add_tags(0, ["overflow"])
    assert len(lib.entries[0].tags) == 8


def test_unknown_entry_raises_library_error():
    lib = Library([_entry(doi="10.1000/known")])

    for unknown in (5, -1, True, "unknown title", "10.9999/missing"):
        with pytest.raises(LibraryError):
            lib.set_tags(unknown, ["x"])

    assert isinstance(LibraryError("x"), ValueError)
    assert lib.entries[0].tags == []


def test_tags_can_be_addressed_by_id_doi_or_title():
    lib = Library([
        _entry(title="A study of citation practice", doi="10.1000/ABC", year=2020),
        _entry(title="另一种题名", doi="10.1000/xyz", year=2021),
    ])

    assert lib.set_tags("https://doi.org/10.1000/abc", ["a"]).tags == ["a"]
    assert lib.set_tags("a  study OF citation practice", ["b"]).tags == ["b"]
    assert lib.set_tags("1", ["c"]).tags == ["c"]
    assert lib.set_tags("10.1000/xyz", ["d"]).tags == ["d"]


def test_tags_persist_in_json_and_sidecar(tmp_path):
    path = tmp_path / "library.json"
    lib = Library([_entry(tags=["方法", "综述"])])
    lib.save(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 2
    assert raw["entries"][0]["tags"] == ["方法", "综述"]
    assert Library.load(path).entries[0].tags == ["方法", "综述"]
    assert library_db.read_library(library_db.db_path_for(path)).entries[0].tags == ["方法", "综述"]

    # JSON is authoritative; when it is lost the sidecar still carries tags.
    path.unlink()
    assert Library.load(path).entries[0].tags == ["方法", "综述"]


def test_old_json_without_tags_loads_with_empty_tags(tmp_path):
    path = tmp_path / "library.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "count": 2,
                "entries": [
                    {"title": "Old paper", "authors": ["ZHANG San"], "year": 2020},
                    {"title": "Broken tags", "tags": "oops"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    library = Library.load(path)
    assert [entry.tags for entry in library.entries] == [[], []]


def test_find_duplicates_by_doi_does_not_delete():
    lib = Library([
        _entry(title="Original title", doi="10.1/ABC"),
        _entry(title="Different title", doi="https://doi.org/10.1/abc"),
        _entry(title="Unique paper", doi="10.2/unique"),
    ])

    groups = lib.find_duplicates()

    assert len(groups) == 1
    assert groups[0]["ids"] == [0, 1]
    assert groups[0]["reason"] == "doi"
    assert [entry["title"] for entry in groups[0]["entries"]] == ["Original title", "Different title"]
    assert len(lib) == 3


def test_find_duplicates_by_title_and_year_ignores_case_and_spaces():
    lib = Library([
        _entry(title="Deep  Learning for Graphs", year=2020),
        _entry(title="deep learning for graphs", year=2020),
        _entry(title="Deep Learning for Graphs", year=2021),
    ])

    groups = lib.find_duplicates()

    assert len(groups) == 1
    assert groups[0]["ids"] == [0, 1]
    assert groups[0]["reason"] == "title_year"


def test_merge_duplicates_keeps_fields_tags_and_removes_drops():
    keep = _entry(title="Keep", year=2020, tags=["方法"])
    drop = _entry(
        title="Drop",
        year=2019,
        tags=["综述", "方法"],
        abstract="来自重复条目的摘要",
        doi="10.1/merged",
        authors=["LI Si"],
        venue="测试期刊",
    )
    lib = Library([keep, drop, _entry(title="Other", year=2018)])

    assert lib.merge_duplicates(0, [1]) == 1
    assert len(lib) == 2

    merged = lib.entries[0]
    assert (merged.title, merged.year) == ("Keep", 2020)  # kept values win
    assert merged.abstract == "来自重复条目的摘要"
    assert merged.doi == "10.1/merged"
    assert merged.authors == ["LI Si"]
    assert merged.venue == "测试期刊"
    assert merged.tags == ["方法", "综述"]


def test_merge_rejects_illegal_or_over_budget_requests():
    lib = Library([_entry(title="A"), _entry(title="B")])

    with pytest.raises(LibraryError, match="保留条目"):
        lib.merge_duplicates(0, [0])
    with pytest.raises(LibraryError, match="越界"):
        lib.merge_duplicates(0, [9])
    with pytest.raises(LibraryError, match="没有需要合并"):
        lib.merge_duplicates(0, [])
    assert len(lib) == 2

    filled = Library([
        _entry(title="C", tags=[f"t{i}" for i in range(7)]),
        _entry(title="D", tags=["u1", "u2"]),
    ])
    with pytest.raises(LibraryError, match="最多 8 个"):
        filled.merge_duplicates(0, [1])
    assert len(filled) == 2  # rejected before mutating either entry


def test_merge_duplicates_saves_when_library_was_loaded(tmp_path):
    path = tmp_path / "library.json"
    Library([_entry(title="A", tags=["x"]), _entry(title="B", tags=["y"])]).save(path)

    loaded = Library.load(path)
    assert loaded.merge_duplicates(0, [1]) == 1

    reloaded = Library.load(path)
    assert len(reloaded) == 1
    assert reloaded.entries[0].tags == ["x", "y"]


def test_sidecar_v1_without_tags_is_migrated(tmp_path):
    db_path = tmp_path / "library.json.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            norm_title TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            authors TEXT NOT NULL DEFAULT '[]',
            venue TEXT NOT NULL DEFAULT '',
            year INTEGER,
            volume TEXT NOT NULL DEFAULT '',
            issue TEXT NOT NULL DEFAULT '',
            pages TEXT NOT NULL DEFAULT '',
            doi TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            abstract TEXT NOT NULL DEFAULT '',
            doc_type TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'local',
            raw TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    conn.execute(
        "INSERT INTO entries(norm_title, title, authors) VALUES('oldpaper', 'Old paper', '[]')"
    )
    conn.commit()
    conn.close()

    library = library_db.read_library(db_path)
    assert len(library) == 1
    assert library.entries[0].tags == []

    library.entries[0].tags = ["经典"]
    library_db.write_library(library, db_path)
    again = library_db.read_library(db_path)
    assert again.entries[0].tags == ["经典"]

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
        schema = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]
    finally:
        conn.close()
    assert "tags" in columns
    assert schema == "2"
