"""Tests for the topic → literature discovery helper (module E)."""
from __future__ import annotations

import json

import pytest

from citeguard import discover
from citeguard.local_library import Library


def _work(doi="10.1/x", title="人工智能教育应用", year=2024, citations=3, oa=True, cited=None):
    return {
        "id": f"https://openalex.org/W{abs(hash(doi)) % 10**8}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": year,
        "authorships": [
            {"author": {"display_name": "张三"}},
            {"author": {"display_name": "李四"}},
        ],
        "primary_location": {"source": {"display_name": "中国远程教育"}},
        "type": "article",
        "language": "zh",
        "cited_by_count": citations if cited is None else cited,
        "open_access": {"is_oa": oa},
        "best_oa_location": {"pdf_url": "https://example.org/a.pdf"} if oa else {},
    }


def test_to_item_maps_openalex_fields():
    item = discover._to_item(_work())
    assert item["title"] == "人工智能教育应用"
    assert item["doi"] == "10.1/x"
    assert item["authors"] == ["张三", "李四"]
    assert item["venue"] == "中国远程教育"
    assert item["year"] == 2024
    assert item["cited_by"] == 3
    assert item["is_oa"] is True
    assert item["oa_url"].endswith("a.pdf")
    assert item["openalex_id"].startswith("W")


def test_query_overlap_supports_cjk_bigrams():
    assert discover._query_overlap("人工智能 教育", "人工智能教育应用") == 1.0
    assert discover._query_overlap("人工智能", "图书馆服务") == 0.0
    assert 0 < discover._query_overlap("reading comprehension", "Reading comprehension in L2") <= 1


def test_rank_prefers_title_overlap_and_penalises_citations_only():
    generic = discover._to_item(_work(doi="10.1/a", title="高等教育研究", citations=500))
    exact = discover._to_item(_work(doi="10.1/b", title="人工智能教育应用研究", citations=2))
    ranked = discover.rank([generic, exact], "人工智能教育", now_year=2026)
    assert ranked[0]["title"] == "人工智能教育应用研究"
    assert ranked[0]["match_score"] >= ranked[1]["match_score"]


def test_search_papers_passes_filters_and_returns_ranked(monkeypatch):
    captured = {}

    def fake_fetch(url, params):
        captured.update({"url": url, "params": params})
        return {"meta": {"count": 42}, "results": [_work(), _work(doi="10.1/y", title="其他")]}

    monkeypatch.setattr(discover, "_fetch_json", fake_fetch)
    result = discover.search_papers("人工智能教育", limit=5, year_from=2020, oa_only=True)
    assert result["matched"] == 42
    assert len(result["results"]) == 2
    assert result["provider"] == "OpenAlex"
    assert "from_publication_date:2020-01-01" in captured["params"]["filter"]
    assert "is_oa:true" in captured["params"]["filter"]
    assert captured["params"]["per-page"] == 5


def test_search_papers_rejects_short_query():
    with pytest.raises(ValueError):
        discover.search_papers("a")


def test_fetch_json_uses_cache_and_stale_fallback(monkeypatch, tmp_path):
    cache_dir = tmp_path / "discover"
    cache_dir.mkdir()
    monkeypatch.setattr(discover, "_cache_dir", lambda: cache_dir)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"results": [{"title": "x"}]}

    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("network down")
        return FakeResponse()

    monkeypatch.setattr(discover.requests, "get", fake_get)
    first = discover._fetch_json("https://api.openalex.org/works", {"search": "x"})
    second = discover._fetch_json("https://api.openalex.org/works", {"search": "x"})
    assert first == second == {"results": [{"title": "x"}]}
    assert calls["n"] == 1  # second call served from cache


def test_fetch_json_raises_without_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(discover, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(discover.requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(discover.DiscoverError):
        discover._fetch_json("https://api.openalex.org/works", {"search": "x"})


def test_import_entries_dedupes_and_saves(tmp_path):
    path = tmp_path / "library.json"
    items = [
        {"title": "人工智能教育应用", "authors": ["张三"], "year": 2024,
         "venue": "中国远程教育", "doi": "10.1/x", "type": "article"},
        {"title": "人工智能教育应用", "authors": ["张三"], "year": 2024,
         "venue": "中国远程教育", "doi": "10.1/x", "type": "article"},
        {"title": "第二篇", "authors": ["李四"], "year": 2023,
         "venue": "开放教育研究", "doi": "10.1/y", "type": "book-chapter"},
    ]
    stats = discover.import_entries(items, library_path=path)
    assert stats["added"] == 2
    assert stats["skipped"] == 1
    library = Library.load(path)
    assert len(library) == 2
    assert library.entries[1].doc_type == "M"
    assert library.entries[0].source == "openalex-discover"


def test_render_csv_quotes_titles():
    result = {"results": [{"title": 'A "quoted" title', "authors": ["甲", "乙"], "year": 2024,
                            "venue": "刊", "cited_by": 9, "doi": "10.1/x", "is_oa": True,
                            "oa_url": "https://example.org/x"}]}
    text = discover.render_csv(result)
    assert "题名,作者,年份" in text
    assert '"A ""quoted"" title"' in text
    assert "甲; 乙" in text
