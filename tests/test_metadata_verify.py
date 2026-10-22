"""Tests for multi-source metadata verification (all HTTP is faked)."""
from __future__ import annotations

import pytest

from citeguard import metadata_verify as mv
from citeguard.metadata_verify import Candidate, Reference, VerifyResult
from citeguard.reference_parser import parse_reference

from helpers import (
    FakeResponse,
    crossref_message,
    crossref_records,
    install_fake_get,
    make_doi_handler,
    openalex_work,
)

REF = parse_reference(
    "[1] 张三, 李四. 中文引文核验方法研究[J]. 中国科技期刊研究, 2020, 31(2): 10-20. "
    "DOI: 10.1234/abc.123."
)


def _ref_without_doi(**overrides) -> Reference:
    values = dict(
        raw="[2] 张三. 元数据核验方法[J]. 情报学报, 2020, 39(5): 501-510.",
        index=2,
        authors=["张三"],
        title="元数据核验方法",
        doc_type="J",
        venue="情报学报",
        year=2020,
        volume="39",
        issue="5",
        pages="501-510",
    )
    values.update(overrides)
    return Reference(**values)


def test_norm_title_strips_case_and_punctuation():
    assert mv.norm_title("Deep Learning: A Survey!") == "deeplearningasurvey"
    assert mv.norm_title("中文：引文核验") == "中文引文核验"


def test_title_sim_bounds():
    assert mv.title_sim("Same Title", "same title!") == pytest.approx(1.0)
    assert mv.title_sim("", "something") == 0.0


def test_verify_doi_exact(monkeypatch, isolated_cache):
    records = crossref_records([REF])
    install_fake_get(monkeypatch, mv, make_doi_handler(records))

    result = mv.verify_reference(REF)

    assert result.status == "Exact"
    assert result.doi_status == "resolved"
    assert result.best is not None and result.best.doi == "10.1234/abc.123"
    assert result.mismatches == []
    assert "crossref:doi" in result.sources


def test_verify_doi_year_drift_is_minor(monkeypatch, isolated_cache):
    records = crossref_records([REF])
    records[REF.doi] = crossref_message(REF, year=2021)
    install_fake_get(monkeypatch, mv, make_doi_handler(records))

    result = mv.verify_reference(REF)

    assert result.status == "Minor"
    assert "year" in result.mismatches


def test_verify_doi_404_is_major(monkeypatch, isolated_cache):
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(404, {"status": "not found"}))

    result = mv.verify_reference(REF)

    assert result.status == "Major"
    assert result.doi_status == "not_found"


def test_verify_doi_network_error_is_unknown(monkeypatch, isolated_cache):
    def boom(url, params):
        raise mv.requests.ConnectionError("network down")

    install_fake_get(monkeypatch, mv, boom)

    result = mv.verify_reference(REF)

    assert result.status == "Unknown"
    assert result.doi_status == "error"


def test_verify_doi_title_mismatch_is_major(monkeypatch, isolated_cache):
    records = crossref_records([REF])
    records[REF.doi] = crossref_message(REF, title="完全不同的另一篇论文题名")
    install_fake_get(monkeypatch, mv, make_doi_handler(records))

    result = mv.verify_reference(REF)

    assert result.status == "Major"
    assert "title" in result.mismatches


def test_verify_doi_cross_language_title_is_minor(monkeypatch, isolated_cache):
    ref = Reference(
        raw="[3] 张三. 中文引文核验方法研究[J]. 期刊, 2020. DOI: 10.1234/lang.",
        index=3,
        authors=["张三"],
        title="中文引文核验方法研究",
        doc_type="J",
        venue="期刊",
        year=2020,
        doi="10.1234/lang",
    )
    records = {"10.1234/lang": crossref_message(ref, title="Citation verification for Chinese papers")}
    install_fake_get(monkeypatch, mv, make_doi_handler(records))

    result = mv.verify_reference(ref)

    assert result.status == "Minor"
    assert "title_language" in result.mismatches


def test_verify_no_doi_openalex_exact(monkeypatch, isolated_cache):
    ref = _ref_without_doi()

    def handler(url, params):
        if url.endswith("/works") and "openalex" in url:
            return FakeResponse(200, {"results": [openalex_work(ref)]})
        return FakeResponse(404, {"status": "not found"})

    install_fake_get(monkeypatch, mv, handler)

    result = mv.verify_reference(ref)

    assert result.status == "Exact"
    assert result.doi_status == "none"
    assert "openalex" in result.sources


def test_verify_no_doi_not_found_is_unverified_not_fabricated(monkeypatch, isolated_cache):
    """A plain search miss must not be reported as a fabricated citation."""
    ref = _ref_without_doi()
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(404, {"status": "not found"}))

    result = mv.verify_reference(ref)

    assert result.status == "Unverified"
    assert "no usable candidate" in " ".join(result.notes)


def test_verify_weak_title_match_is_unverified(monkeypatch, isolated_cache):
    """Candidates exist but none is close: unverified, not major."""
    ref = _ref_without_doi(title="累积生态风险对大学生健康危险行为的影响")
    unrelated = {"id": "W1", "title": "Urban ecology of coastal cities", "publication_year": 2019}

    def handler(url, params):
        if "openalex" in url:
            return FakeResponse(200, {"results": [unrelated]})
        return FakeResponse(404, {"status": "not found"})

    install_fake_get(monkeypatch, mv, handler)

    result = mv.verify_reference(ref)

    assert result.status == "Unverified"
    assert result.title_sim < 0.78


def test_verify_no_doi_partial_title_is_minor(monkeypatch, isolated_cache):
    ref = _ref_without_doi(title="Metadata verification of references", venue="Journal")
    longer_title = "Metadata verification of references in Chinese journals"
    assert 0.78 <= mv.title_sim(ref.title, longer_title) < 0.90

    def handler(url, params):
        if url.endswith("/works") and "openalex" in url:
            return FakeResponse(200, {"results": [openalex_work(ref, title=longer_title)]})
        return FakeResponse(404, {"status": "not found"})

    install_fake_get(monkeypatch, mv, handler)

    result = mv.verify_reference(ref)

    assert result.status == "Minor"
    assert result.mismatches == ["title"]


def test_verify_uses_cache_on_second_call(monkeypatch, isolated_cache):
    records = crossref_records([REF])
    calls = install_fake_get(monkeypatch, mv, make_doi_handler(records))

    first = mv.verify_reference(REF)
    crossref_calls = [c for c in calls if "api.crossref.org/works/" in c["url"]]
    second = mv.verify_reference(REF)
    crossref_calls_after = [c for c in calls if "api.crossref.org/works/" in c["url"]]

    assert first.status == second.status == "Exact"
    assert len(crossref_calls) == 1
    # successful responses are cached: the DOI is not fetched from Crossref twice
    assert len(crossref_calls_after) == len(crossref_calls)
    assert list(isolated_cache.glob("*.json"))


def test_lookup_doi_status_not_found(monkeypatch, isolated_cache):
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(404, {"status": "not found"}))

    candidates, status = mv.lookup_doi_status("10.1234/missing")

    assert candidates == []
    assert status == "not_found"


def test_verify_many_reports_progress(monkeypatch):
    seen: list[tuple[int, int]] = []

    def fake_verify(ref, use_arxiv=True):
        return VerifyResult(status="Exact", title_sim=1.0)

    monkeypatch.setattr(mv, "verify_reference", fake_verify)

    refs = [_ref_without_doi(index=i) for i in range(1, 4)]
    results = mv.verify_many(refs, progress=False, progress_cb=lambda i, n: seen.append((i, n)))

    assert [r.status for r in results] == ["Exact", "Exact", "Exact"]
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_pick_best_prefers_candidate_with_abstract():
    ref = _ref_without_doi()
    plain = Candidate(source="openalex", title=ref.title)
    with_abstract = Candidate(source="crossref", title=ref.title, abstract="abstract text")
    assert mv._pick_best(ref, [plain, with_abstract]) is with_abstract


def test_field_mismatches_detects_drift():
    ref = _ref_without_doi()
    cand = Candidate(
        source="crossref",
        title=ref.title,
        year=2019,
        authors=ref.authors,
        venue="其他期刊",
        volume="40",
        pages="1-2",
    )
    mismatches = mv._field_mismatches(ref, cand)
    assert set(mismatches) == {"year", "venue", "volume", "pages"}


def test_doi_resolved_without_candidates_degrades_gracefully(monkeypatch, isolated_cache):
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(200, {}))

    result = mv.verify_reference(REF)

    assert result.status in {"Unknown", "Major"}
