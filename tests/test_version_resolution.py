from __future__ import annotations

from citeguard.metadata_verify import Candidate
from citeguard.reference_parser import Reference
from citeguard.version_resolution import (
    extract_arxiv_id,
    normalize_doi,
    resolve_versions,
    version_kind,
)


def ref(**kw) -> Reference:
    base = dict(raw="x", authors=["Ashish Vaswani"], title="Attention Is All You Need", year=2017)
    base.update(kw)
    return Reference(**base)


def test_doi_and_arxiv_alias_normalization():
    assert normalize_doi("https://doi.org/10.1000/ABC.") == "10.1000/abc"
    assert normalize_doi("doi: 10.1000/abc") == "10.1000/abc"
    assert extract_arxiv_id("arXiv:1706.03762v5") == "1706.03762"
    assert extract_arxiv_id("https://arxiv.org/abs/2401.00001") == "2401.00001"


def test_same_record_from_two_sources_is_one_version():
    cands = [
        Candidate(source="openalex", title="Attention Is All You Need", doi="10.1000/x", year=2017,
                  authors=["Vaswani, Ashish"], venue="NeurIPS"),
        Candidate(source="crossref", title="Attention Is All You Need.", doi="10.1000/X", year=2017,
                  authors=["Ashish Vaswani"], venue="NeurIPS"),
    ]
    res = resolve_versions(ref(), cands)
    assert res.status == "same_version"
    assert res.cited_year_supported
    assert res.chosen is not None
    assert all(not p["doi"].lower().endswith(".") for p in res.provenance)


def test_preprint_and_published_are_a_version_family_not_a_wrong_year():
    cands = [
        Candidate(source="arxiv", title="Attention Is All You Need", doi="", year=2017,
                  authors=["Vaswani, Ashish"], url="https://arxiv.org/abs/1706.03762"),
        Candidate(source="openalex", title="Attention Is All You Need", doi="10.5555/3295222",
                  year=2017, authors=["Vaswani, Ashish"], venue="NeurIPS"),
        Candidate(source="crossref", title="Attention Is All You Need", doi="10.5555/3295222",
                  year=2019, authors=["Vaswani, Ashish"], venue="NeurIPS 2019"),
    ]
    res = resolve_versions(ref(year=2017), cands)
    assert res.status == "version_family"
    assert res.cited_year_supported
    assert "year" in res.conflicts or res.cited_year_supported


def test_a_different_first_author_is_a_conflict_not_a_version():
    cands = [
        Candidate(source="crossref", title="Attention Is All You Need", doi="10.1000/x", year=2017,
                  authors=["Someone Else"], venue="NeurIPS"),
    ]
    res = resolve_versions(ref(), cands)
    assert res.status == "conflict"
    assert "authors" in res.conflicts


def test_no_close_candidate_is_insufficient():
    res = resolve_versions(ref(), [Candidate(source="crossref", title="Completely Different", year=2017)])
    assert res.status == "insufficient"


def test_version_kind_flags_arxiv_as_preprint():
    assert version_kind(Candidate(source="arxiv", title="x", url="https://arxiv.org/abs/1706.03762")) == "preprint"
    assert version_kind(Candidate(source="openalex", title="x", doi="10.1000/x", venue="NeurIPS")) == "published"
