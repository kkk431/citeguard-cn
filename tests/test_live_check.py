"""Offline tests for CiteGuard Live (``citeguard.live_check``).

Every test monkeypatches the metadata search layer or the judge, so no HTTP call
is made and no API key is required.  The important invariants are:

* an evidence quote is an exact slice of the candidate abstract;
* a partial / missing number never becomes a full ``support``;
* transport failure returns ``no_evidence`` instead of raising;
* the CLI prints parseable JSON.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from citeguard import config, live_check, metadata_verify, support
from citeguard.metadata_verify import Candidate

ROOT = Path(__file__).resolve().parents[1]


def _candidate(
    title: str,
    abstract: str,
    *,
    doi: str = "10.1234/live.test",
    source: str = "openalex",
    year: int = 2024,
) -> Candidate:
    return Candidate(
        source=source,
        title=title,
        doi=doi,
        year=year,
        authors=["Test Author"],
        venue="Journal of Test Studies",
        abstract=abstract,
        url="https://openalex.org/W12345678",
    )


def _patch_searches(monkeypatch, openalex=(), crossref=()):
    monkeypatch.setattr(
        live_check,
        "search_openalex",
        lambda title, limit=5: list(openalex),
    )
    monkeypatch.setattr(
        live_check,
        "search_crossref",
        lambda title, limit=5: list(crossref),
    )


@pytest.fixture(autouse=True)
def live_defaults(monkeypatch):
    """Deterministic: online mode, no judge model configured."""
    monkeypatch.setattr(config, "OFFLINE", False)
    monkeypatch.setattr(live_check.support, "judge_available", lambda: False)
    yield


def test_empty_claim_returns_no_evidence():
    result = live_check.check_claim("   ")
    assert result["label"] == "no_evidence"
    assert result["confidence"] == 0.0
    assert result["evidence"] is None
    assert result["candidates"] == []
    assert result["label"] in live_check.LIVE_LABELS


def test_offline_mode_never_searches(monkeypatch):
    monkeypatch.setattr(config, "OFFLINE", True)

    def _must_not_search(title, limit=5):  # noqa: ANN001
        raise AssertionError("search must not run in offline mode")

    monkeypatch.setattr(live_check, "search_openalex", _must_not_search)
    monkeypatch.setattr(live_check, "search_crossref", _must_not_search)
    result = live_check.check_claim("AI tutoring improves learning outcomes")
    assert result["label"] == "no_evidence"
    assert "离线" in result["reason"]
    assert result["evidence"] is None


def test_heuristic_support_quote_is_exact_abstract_slice(monkeypatch):
    abstract = (
        "Intelligent tutoring systems improve student learning outcomes in higher education. "
        "The randomized trial included 420 students."
    )
    _patch_searches(monkeypatch, openalex=[_candidate("Tutoring and outcomes", abstract)])
    result = live_check.check_claim("AI tutoring improves student learning outcomes")
    assert result["label"] == "support"
    assert result["confidence"] > 0.5
    quote = result["evidence"]["quote"]
    assert quote in abstract
    assert result["evidence"]["url"] == "https://openalex.org/W12345678"
    assert result["candidates"][0]["doi"] == "10.1234/live.test"


def test_no_matching_candidate_returns_no_evidence(monkeypatch):
    abstract = "This paper reviews AI policy frameworks in universities."
    _patch_searches(monkeypatch, openalex=[_candidate("AI policy", abstract)])
    result = live_check.check_claim("AI tutoring improves student learning outcomes")
    assert result["label"] == "no_evidence"
    assert result["evidence"] is None
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["abstract"] == abstract


def test_number_mismatch_is_partial_not_support(monkeypatch):
    abstract = "AI tutoring increased test scores by 12% in a randomized trial."
    _patch_searches(monkeypatch, openalex=[_candidate("Tutoring trial", abstract)])
    result = live_check.check_claim("AI tutoring increases test scores by 40%")
    assert result["label"] == "partial"
    assert result["label"] != "support"
    assert result["evidence"]["quote"] in abstract


def test_network_failure_degrades_to_no_evidence(monkeypatch):
    def _boom(title, limit=5):  # noqa: ANN001
        raise RuntimeError("simulated DNS failure")

    monkeypatch.setattr(live_check, "search_openalex", _boom)
    monkeypatch.setattr(live_check, "search_crossref", _boom)
    result = live_check.check_claim("AI tutoring improves learning outcomes", page_url="https://example.org/post")
    assert result["label"] == "no_evidence"
    assert "检索失败" in result["reason"]
    assert "example.org" in result["reason"]
    assert result["evidence"] is None
    json.dumps(result, ensure_ascii=False)


def test_candidates_are_deduped_and_capped_at_five(monkeypatch):
    same = _candidate("Same paper", "Unrelated abstract about weather.", doi="10.1000/same")
    others = [
        _candidate(f"Paper {i}", "Unrelated abstract about weather.", doi=f"10.1000/{i}")
        for i in range(7)
    ]
    _patch_searches(monkeypatch, openalex=[same, *others], crossref=[same])
    result = live_check.check_claim("AI tutoring improves learning outcomes")
    assert result["label"] == "no_evidence"
    dois = [item["doi"] for item in result["candidates"]]
    assert len(dois) <= live_check.MAX_CANDIDATES
    assert len(dois) == len(set(dois))
    assert "10.1000/same" in dois


def test_judge_path_keeps_grounded_quote(monkeypatch):
    abstract = "Intelligent tutoring systems improve student learning outcomes in higher education."
    _patch_searches(monkeypatch, openalex=[_candidate("Tutoring and outcomes", abstract)])
    monkeypatch.setattr(live_check.support, "judge_available", lambda: True)
    monkeypatch.setattr(
        live_check.support,
        "judge_support",
        lambda claim, abstract, title="", doi="": {
            "label": "support",
            "confidence": 0.91,
            "reason": "摘要直接报告了学习收益",
            "evidence": "Intelligent tutoring systems improve student learning outcomes in higher education.",
        },
    )
    result = live_check.check_claim("AI tutoring improves student learning outcomes")
    assert result["label"] == "support"
    assert result["confidence"] == 0.91
    assert result["evidence"]["quote"] in abstract
    assert result["evidence"]["title"] == "Tutoring and outcomes"


def test_fabricated_judge_quote_is_dropped(monkeypatch):
    abstract = "Intelligent tutoring systems improve student learning outcomes in higher education."
    _patch_searches(monkeypatch, openalex=[_candidate("Tutoring and outcomes", abstract)])
    monkeypatch.setattr(live_check.support, "judge_available", lambda: True)
    monkeypatch.setattr(
        live_check.support,
        "judge_support",
        lambda claim, abstract, title="", doi="": {
            "label": "support",
            "confidence": 0.9,
            "reason": "模型称有证据",
            "evidence": "This sentence does not exist in the abstract at all.",
        },
    )
    result = live_check.check_claim("AI tutoring improves student learning outcomes")
    assert result["evidence"] is None
    assert "逐字核对" in result["reason"]
    assert result["confidence"] <= 0.55


def test_judge_transport_failure_falls_back_to_heuristic(monkeypatch):
    abstract = "Intelligent tutoring systems improve student learning outcomes in higher education."
    _patch_searches(monkeypatch, openalex=[_candidate("Tutoring and outcomes", abstract)])
    monkeypatch.setattr(live_check.support, "judge_available", lambda: True)

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("judge endpoint unavailable")

    monkeypatch.setattr(live_check.support, "judge_support", _boom)
    result = live_check.check_claim("AI tutoring improves student learning outcomes")
    assert result["label"] == "support"
    assert "降级" in result["reason"]
    assert result["evidence"]["quote"] in abstract


def test_candidate_parser_reads_openalex_payload(monkeypatch):
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W42",
                "doi": "https://doi.org/10.1234/parsed",
                "title": "Parsed candidate",
                "publication_year": 2025,
                "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
                "primary_location": {"source": {"display_name": "Test Journal"}},
                "biblio": {"first_page": "10", "last_page": "20", "volume": "3", "issue": "2"},
                "abstract_inverted_index": {"AI": [0], "works": [1]},
                "is_retracted": False,
                "cited_by_count": 7,
            }
        ]
    }
    monkeypatch.setattr(metadata_verify, "_cached_json", lambda url, params=None: payload)
    candidates = metadata_verify.search_openalex("parsed candidate")
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Parsed candidate"
    assert candidate.doi == "10.1234/parsed"
    assert candidate.year == 2025
    assert candidate.authors == ["Ada Lovelace"]
    assert candidate.abstract == "AI works"
    assert candidate.url == "https://openalex.org/W42"


def test_result_is_json_serialisable(monkeypatch):
    abstract = "AI tutoring improves learning outcomes."
    _patch_searches(monkeypatch, openalex=[_candidate("T", abstract)])
    result = live_check.check_claim("AI tutoring improves learning outcomes")
    encoded = json.dumps(result, ensure_ascii=False)
    assert json.loads(encoded)["label"] == result["label"]


def test_cli_prints_json_offline():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["CITEGUARD_OFFLINE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "citeguard.live_check", "--claim", "AI 能提升学习效果", "--page-title", "测试页面"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["label"] == "no_evidence"
    assert data["evidence"] is None


def test_page_work_identifies_doi_and_arxiv_with_title_fallback(monkeypatch):
    calls = []

    def _fake_cached(url, params=None):
        calls.append((url, params or {}))
        if "10.1234/example" in url:
            return {"id": "https://openalex.org/W111", "title": "DOI page"}
        if "10.48550/arxiv.2305.01185" in url:
            return {"id": "https://openalex.org/W222", "title": "arXiv page"}
        if params and params.get("search") == "A Paper | Journal":
            return {
                "results": [
                    {"id": "https://openalex.org/W999", "title": "Unrelated Paper"},
                    {"id": "https://openalex.org/W333", "title": "A Paper"},
                ]
            }
        raise AssertionError((url, params))

    monkeypatch.setattr(live_check, "_cached_json", _fake_cached)
    doi_work = live_check._page_work("https://doi.org/10.1234/example", "")
    assert doi_work["id"] == "https://openalex.org/W111"
    arxiv_work = live_check._page_work("https://arxiv.org/pdf/2305.01185v2", "")
    assert arxiv_work["id"] == "https://openalex.org/W222"
    title_work = live_check._page_work("https://example.org/article", "A Paper | Journal")
    assert title_work["id"] == "https://openalex.org/W333"
    assert all(params.get("select") == live_check._PAGE_WORK_SELECT for _, params in calls)


def test_referenced_candidates_reconstruct_abstract(monkeypatch):
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W2222222",
                "doi": "https://doi.org/10.1234/reference",
                "title": "Referenced paper",
                "publication_year": 2021,
                "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
                "primary_location": {"source": {"display_name": "Test Journal"}},
                "abstract_inverted_index": {"Deep": [0], "learning": [1], "works": [2]},
            }
        ]
    }
    captured = {}

    def _fake_cached(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return payload

    monkeypatch.setattr(live_check, "_cached_json", _fake_cached)
    work = {"referenced_works": ["https://openalex.org/W2222222"]}
    candidates = live_check._referenced_candidates(work)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Referenced paper"
    assert candidate.doi == "10.1234/reference"
    assert candidate.year == 2021
    assert candidate.authors == ["Ada Lovelace"]
    assert candidate.venue == "Test Journal"
    assert candidate.abstract == "Deep learning works"
    assert candidate.url == "https://openalex.org/W2222222"
    assert captured["url"] == live_check._OPENALEX_WORKS
    assert captured["params"]["filter"] == "openalex_id:W2222222"
    assert captured["params"]["per-page"] == 50


def test_referenced_candidates_caps_at_40(monkeypatch):
    captured = []

    def _fake_cached(url, params=None):
        captured.append(dict(params or {}))
        return {"results": []}

    monkeypatch.setattr(live_check, "_cached_json", _fake_cached)
    work = {"referenced_works": [f"https://openalex.org/W{i:07d}" for i in range(41)]}
    assert live_check._referenced_candidates(work) == []
    assert len(captured) == 1
    assert len(captured[0]["filter"].split("|")) == 40


def test_page_candidates_are_used_first_and_skip_keyword_search(monkeypatch):
    page_ref = _candidate(
        "Reference from the current paper",
        "Intelligent tutoring systems improve student learning outcomes in higher education.",
        doi="10.1000/page-ref",
    )
    monkeypatch.setattr(
        live_check,
        "_page_work",
        lambda page_url, page_title="": {
            "id": "https://openalex.org/W100",
            "referenced_works": ["https://openalex.org/W200"],
        },
    )
    monkeypatch.setattr(live_check, "_referenced_candidates", lambda work: [page_ref])

    def _must_not_search(title, limit=5):  # noqa: ANN001
        raise AssertionError("keyword search should be skipped when references are usable")

    monkeypatch.setattr(live_check, "search_openalex", _must_not_search)
    monkeypatch.setattr(live_check, "search_crossref", _must_not_search)
    result = live_check.check_claim(
        "AI tutoring improves student learning outcomes",
        page_url="https://doi.org/10.1000/current",
    )
    assert result["label"] == "support"
    assert result["candidates"][0]["doi"] == "10.1000/page-ref"
    assert result["evidence"]["title"] == "Reference from the current paper"


def test_merge_keeps_page_candidate_when_keyword_duplicates_it():
    page = _candidate("Page reference", "Page abstract", doi="10.1000/shared")
    duplicate = _candidate("Crossref duplicate", "Keyword abstract", doi="10.1000/shared")
    other = _candidate("Keyword only", "Other abstract", doi="10.1000/other")
    merged = live_check._merge_candidates([page], [duplicate, other])
    assert merged[0] is page
    assert [item.doi for item in merged] == ["10.1000/shared", "10.1000/other"]


def test_page_identification_failure_falls_back_to_keyword_search(monkeypatch):
    abstract = "Intelligent tutoring systems improve student learning outcomes in higher education."
    monkeypatch.setattr(live_check, "_page_work", lambda page_url, page_title="": None)
    _patch_searches(monkeypatch, openalex=[_candidate("Tutoring and outcomes", abstract)])
    result = live_check.check_claim(
        "AI tutoring improves student learning outcomes",
        page_url="https://example.org/not-a-paper",
        page_title="Not a paper page",
    )
    assert result["label"] == "support"
    assert result["candidates"][0]["doi"] == "10.1234/live.test"
    assert result["evidence"]["quote"] in abstract

def test_page_reference_ranking_prefers_title_over_long_abstract(monkeypatch):
    """Page references are ranked by title; a long generic abstract must not win."""
    from citeguard import live_check as lc

    claim = "Attention is all you need for sequence modeling [12]."
    terms = lc._terms(claim)
    numbers = lc._numbers(claim)
    title_match = lc.Candidate(
        title="Attention is All You Need",
        abstract="A long abstract about unrelated biology and clinical trials.",
        source="test",
    )
    abstract_match = lc.Candidate(
        title="Unrelated title",
        abstract="Attention is all you need for sequence modeling.",
        source="test",
    )
    assert lc._page_candidate_score(terms, numbers, title_match) > lc._page_candidate_score(
        terms, numbers, abstract_match
    )
