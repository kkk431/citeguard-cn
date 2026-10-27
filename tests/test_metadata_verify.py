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


def test_version_source_keeps_cited_year_when_another_source_agrees():
    """Citing the 2018 arXiv version of a 2019 conference paper is not a wrong year."""
    ref = _ref_without_doi(title="Attention Is All You Need", year=2017, authors=["Ashish Vaswani"])
    chosen = mv.Candidate(
        source="openalex",
        title="Attention Is All You Need",
        year=2019,
        authors=["Vaswani, Ashish"],
    )
    earlier = mv.Candidate(
        source="arxiv",
        title="Attention Is All You Need",
        year=2017,
        authors=["Vaswani, Ashish"],
    )
    unrelated = mv.Candidate(
        source="crossref",
        title="Attention Is All You Need",
        year=2022,
        authors=["Someone Else"],
    )

    assert mv._version_sources(ref, [chosen, earlier, unrelated], chosen) == ["arxiv"]


def test_version_source_requires_matching_first_author():
    ref = _ref_without_doi(title="Attention Is All You Need", year=2017, authors=["Ashish Vaswani"])
    chosen = mv.Candidate(source="openalex", title=ref.title, year=2019, authors=["Vaswani, Ashish"])
    different = mv.Candidate(source="arxiv", title=ref.title, year=2017, authors=["John Smith"])

    assert mv._version_sources(ref, [chosen, different], chosen) == []


def test_rate_limited_sources_report_unknown_not_unverified(monkeypatch, isolated_cache):
    """429 from every source means "could not check", not "not found"."""
    ref = _ref_without_doi()
    monkeypatch.setattr(mv.time, "sleep", lambda *_: None)
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(429, {"error": "rate limited"}))

    result = mv.verify_reference(ref)

    assert result.status == "Unknown"
    assert "数据源" in " ".join(result.notes)


def test_weak_match_with_failed_source_is_unknown(monkeypatch, isolated_cache):
    """A weak best match plus a failed source is "could not check", not "not found"."""
    ref = _ref_without_doi(title="累积生态风险对大学生健康危险行为的影响")
    unrelated = {"id": "W1", "title": "Urban ecology of coastal cities", "publication_year": 2019}
    monkeypatch.setattr(mv.time, "sleep", lambda *_: None)

    def handler(url, params):
        if "openalex" in url:
            return FakeResponse(200, {"results": [unrelated]})
        return FakeResponse(429, {"error": "rate limited"})

    install_fake_get(monkeypatch, mv, handler)

    result = mv.verify_reference(ref)

    assert result.status == "Unknown"
    assert "未完成核验" in " ".join(result.notes)


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
    notes = " ".join(result.notes)
    assert "中文文献" in notes
    assert "知网" in notes


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

    def fake_verify(ref, use_arxiv=True, library=None):
        return VerifyResult(status="Exact", title_sim=1.0)

    monkeypatch.setattr(mv, "verify_reference", fake_verify)

    refs = [_ref_without_doi(index=i) for i in range(1, 4)]
    for i, ref in enumerate(refs, 1):
        ref.title = f"不同题名 {i}"  # keep them distinct so nothing is deduplicated
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


def test_author_surname_matching_handles_published_formats():
    # "Surname, Initials" (Chinese GB/T) vs "Given Family" (Crossref/OpenAlex).
    assert mv._first_author_match(["Yu, H."], ["Hui Yu"]) is True
    assert mv._first_author_match(["Markus, H."], ["Hazel Rose Markus"]) is True
    assert mv._first_author_match(["Dweck, C. S.", "Chiu, C."], ["Carol Sorich Dweck", "Chi-yue Chiu"]) is True
    assert mv._author_overlap(["Yu, H.", "Li, X."], ["Hui Yu", "Xiaomin Li"]) == pytest.approx(1.0)
    # A review of the book is not the book: the first author really differs.
    assert mv._first_author_match(["Hayman, W.K."], ["J. G. Clunie"]) is False
    assert mv._author_overlap(["Hayman, W.K."], ["J. G. Clunie"]) == 0.0


def test_author_order_mismatch_uses_family_names():
    assert mv._author_order_mismatch(["Yi, H.X.", "Yang, C.C."], ["Chung-Chun Yang", "Hong-Xun Yi"]) is True
    assert mv._author_order_mismatch(["Yu, H.", "Li, X."], ["Hui Yu", "Xiaomin Li"]) is False


def test_same_title_with_review_record_is_explained(monkeypatch, isolated_cache):
    """A book-review record sharing the title must not look like a plain typo."""
    ref = _ref_without_doi(title="Meromorphic Functions", venue="Clarendon")
    review = {
        "id": "W1",
        "title": "Meromorphic Functions",
        "publication_year": 1964,
        "authorships": [{"author": {"display_name": "J. G. Clunie"}}],
        "primary_location": {"source": {"display_name": "Journal of the London Mathematical Society"}},
    }

    def handler(url, params):
        if "openalex" in url:
            return FakeResponse(200, {"results": [review]})
        return FakeResponse(404, {"status": "not found"})

    install_fake_get(monkeypatch, mv, handler)

    result = mv.verify_reference(ref)

    assert result.status == "Minor"
    assert "authors" in result.mismatches
    assert "书评" in " ".join(result.notes)


def test_url_only_title_is_unverified_not_fabricated():
    """A PDF/OCR artifact must not be reported as a fabricated citation."""
    ref = Reference(
        raw="[1] https://doi.org/10.1177/00336882231162868",
        index=1,
        title="https://doi.org/10.1177/00336882231162868",
    )

    result = mv.verify_reference(ref)

    assert result.status == "Unverified"
    assert any("链接" in note for note in result.notes)


def test_empty_title_is_unverified_not_fabricated():
    """Page furniture / split noise leaves no title: ask for review, never Major."""
    ref = Reference(raw="[1] 550. https://doi.org/10.1177/00336882231162868", index=1, title="")

    result = mv.verify_reference(ref)

    assert result.status == "Unverified"
    assert any("题名解析为空" in note for note in result.notes)


# ---------------------------------------------------------------------------
# Web citations ([EB/OL]): the URL itself is the evidence
# ---------------------------------------------------------------------------

def _web_ref() -> Reference:
    return Reference(
        raw="[1] Stanford University. Bio-X: About Bio-X. http://biox.stanford.edu/about/history.html",
        index=1,
        authors=["Stanford University"],
        title="Bio-X: About Bio-X",
        doc_type="EB",
        url="http://biox.stanford.edu/about/history.html",
    )


def test_link_checker_blocks_private_and_non_http_urls():
    """The checker must not become an SSRF gadget against localhost / intranet."""
    for url in (
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://10.0.0.1/x",
        "http://192.168.1.1/x",
        "ftp://example.org/x",
        "file:///etc/passwd",
    ):
        ok, reason = mv._url_host_is_public(url)
        assert ok is False, url
        assert reason


def test_web_citation_live_page_with_matching_title_is_exact(monkeypatch):
    monkeypatch.setattr(
        mv,
        "check_web_url",
        lambda url: {"state": "live", "status": 200, "final_url": url, "title": "Bio-X: About Bio-X | Stanford"},
    )

    result = mv.verify_reference(_web_ref())

    assert result.status == "Exact"
    assert any("页面标题" in note for note in result.notes)
    assert "url:live" in result.sources


def test_web_citation_dead_link_is_unverified_not_fabricated(monkeypatch):
    monkeypatch.setattr(
        mv,
        "check_web_url",
        lambda url: {"state": "dead", "status": 404, "final_url": url, "title": ""},
    )

    result = mv.verify_reference(_web_ref())

    assert result.status == "Unverified"  # link rot != fabrication
    assert any("HTTP 404" in note for note in result.notes)
    assert "url:dead" in result.sources


def test_web_citation_title_mismatch_is_unverified(monkeypatch):
    monkeypatch.setattr(
        mv,
        "check_web_url",
        lambda url: {"state": "live", "status": 200, "final_url": url, "title": "Stanford University Home"},
    )

    result = mv.verify_reference(_web_ref())

    assert result.status == "Unverified"
    assert any("不一致" in note for note in result.notes)


def test_web_citation_blocked_link_falls_through_to_title_search(monkeypatch):
    """A blocked/private URL gives no opinion: normal title search still runs."""
    ref = Reference(
        raw="[1] 机构. 网页题名[EB/OL]. http://127.0.0.1/x.",
        index=1,
        title="网页题名",
        doc_type="EB",
        url="http://127.0.0.1/x",
    )
    monkeypatch.setattr(mv, "search_openalex", lambda title, limit=5: [])
    monkeypatch.setattr(mv, "search_crossref", lambda title, limit=5: [])
    monkeypatch.setattr(mv, "search_arxiv", lambda title, limit=3: [])

    result = mv.verify_reference(ref)

    assert result.status == "Unverified"


def test_authors_unreliable_flags_initial_fragments_not_whole_names():
    # Fragment list from a broken APA parse: initials pieces are not authors.
    assert mv._authors_unreliable(["Hayman", " W.K."]) is True
    assert mv._authors_unreliable(["Brehm", " S. S.", " Miller"]) is True
    # Whole names from the fixed parser are comparable.
    assert mv._authors_unreliable(["Brehm, S. S.", "Miller, R. S."]) is False


def test_doi_resolved_without_candidates_degrades_gracefully(monkeypatch, isolated_cache):
    install_fake_get(monkeypatch, mv, lambda url, params: FakeResponse(200, {}))

    result = mv.verify_reference(REF)

    assert result.status in {"Unknown", "Major"}


# ---------------------------------------------------------------------------
# China DOI / DataCite landing pages (DOIs registered outside Crossref)
# ---------------------------------------------------------------------------

CNKI_DOI = "10.15886/j.cnki.hnus.202410.0119"

LANDING_HTML = """<!DOCTYPE html>
<html><body>
<div class="feedbackresult">
  <div class="fbHd">多重解析地址选择页面</div>
  <div class="fbBd"><table>
    <tr><td><label>题名：</label>大数据杀熟治理的演化博弈研究</td></tr>
    <tr><td><label>作者：</label>熊浩;张晨;鄢慧丽;</td></tr>
    <tr><td><label>来源：</label>湖南大学学报（社会科学版）</td></tr>
    <tr><td><label>出版机构：</label>同济大学</td></tr>
    <tr><td><label>出版年：</label>2024</td></tr>
    <tr><td><label>DOI码：</label>10.15886/j.cnki.hnus.202410.0119</td></tr>
  </table></div>
</div>
</body></html>"""


def _landing_ref() -> Reference:
    return Reference(
        raw="[4] 熊浩, 张晨, 鄢慧丽. 大数据杀熟治理的演化博弈研究[J]. "
        "湖南大学学报(社会科学版), 2024. DOI: 10.15886/j.cnki.hnus.202410.0119.",
        index=4,
        authors=["熊浩", "张晨", "鄢慧丽"],
        title="大数据杀熟治理的演化博弈研究",
        doc_type="J",
        venue="湖南大学学报(社会科学版)",
        year=2024,
        doi=CNKI_DOI,
    )


def _landing_handler(calls: list[dict]):
    """Crossref/OpenAlex 404, handle exists, DataCite 404, landing page present."""

    def handler(url: str, params: dict) -> FakeResponse:
        if "api.crossref.org/works/" in url or "api.openalex.org" in url:
            return FakeResponse(404, {"status": "not found"})
        if "doi.org/api/handles/" in url:
            return FakeResponse(200, {"responseCode": 1})
        if "api.datacite.org" in url:
            return FakeResponse(404, {"errors": []})
        if url == f"https://doi.org/{CNKI_DOI}":
            return FakeResponse(200, None, text=LANDING_HTML)
        return FakeResponse(404, {"status": "not found"})

    return handler


def test_parse_doi_landing_extracts_cnki_metadata():
    cand = mv._parse_doi_landing(LANDING_HTML, CNKI_DOI)

    assert cand is not None
    assert cand.source == "doi:landing"
    assert cand.title == "大数据杀熟治理的演化博弈研究"
    assert cand.authors == ["熊浩", "张晨", "鄢慧丽"]
    assert cand.venue == "湖南大学学报（社会科学版）"
    assert cand.year == 2024
    assert cand.doi == CNKI_DOI


def test_parse_doi_landing_ignores_unrelated_pages():
    html = "<html><body><h1>Publisher landing page</h1><p>Full text links</p></body></html>"
    assert mv._parse_doi_landing(html, CNKI_DOI) is None
    assert mv._parse_doi_landing("多重解析地址选择页面", CNKI_DOI) is None


def test_lookup_doi_status_landing(monkeypatch, isolated_cache):
    calls = install_fake_get(monkeypatch, mv, _landing_handler([]))

    candidates, status = mv.lookup_doi_status(CNKI_DOI)

    assert status == "resolved_landing"
    assert [c.source for c in candidates] == ["doi:landing"]
    assert any(f"https://doi.org/{CNKI_DOI}" in c["url"] for c in calls)


def test_lookup_doi_status_landing_cache_keeps_candidates(monkeypatch, isolated_cache):
    calls = install_fake_get(monkeypatch, mv, _landing_handler([]))

    first, first_status = mv.lookup_doi_status(CNKI_DOI)
    second, second_status = mv.lookup_doi_status(CNKI_DOI)

    assert first_status == second_status == "resolved_landing"
    assert [c.title for c in first] == [c.title for c in second] == ["大数据杀熟治理的演化博弈研究"]
    landing_fetches = [c for c in calls if c["url"] == f"https://doi.org/{CNKI_DOI}"]
    assert len(landing_fetches) == 1


def test_verify_doi_landing_exact(monkeypatch, isolated_cache):
    install_fake_get(monkeypatch, mv, _landing_handler([]))

    result = mv.verify_reference(_landing_ref())

    assert result.status == "Exact"
    assert result.doi_status == "resolved_landing"
    assert result.sources == ["doi:landing"]
    assert result.mismatches == []
    assert result.best is not None and result.best.source == "doi:landing"
    assert "外部注册机构元数据有限" in " ".join(result.notes)


def test_verify_doi_landing_title_mismatch_is_major(monkeypatch, isolated_cache):
    ref = _landing_ref()
    ref.title = "完全不相关的另一篇论文题名"
    install_fake_get(monkeypatch, mv, _landing_handler([]))

    result = mv.verify_reference(ref)

    assert result.status == "Major"
    assert "title" in result.mismatches
    assert result.sources == ["doi:landing"]


def test_openalex_retracted_flag_is_surfaced(monkeypatch, isolated_cache):
    """A retracted paper should keep its metadata status but carry a warning."""
    ref = _ref_without_doi()
    work = openalex_work(ref)
    work["is_retracted"] = True

    def handler(url, params):
        if url.endswith("/works") and "openalex" in url:
            return FakeResponse(200, {"results": [work]})
        return FakeResponse(404, {"status": "not found"})

    install_fake_get(monkeypatch, mv, handler)

    result = mv.verify_reference(ref)

    assert result.status == "Exact"
    assert result.retracted is True
    assert any("撤稿" in n for n in result.notes)
    # to_dict must expose the flag to the web report
    assert result.to_dict()["retracted"] is True


def test_openalex_retraction_does_not_flip_status(monkeypatch, isolated_cache):
    """Retraction must not turn an accurate citation into Minor/Major."""
    ref = _ref_without_doi()
    work = openalex_work(ref, year=2021)  # year drift => Minor by metadata
    work["is_retracted"] = True

    def handler(url, params):
        if url.endswith("/works") and "openalex" in url:
            return FakeResponse(200, {"results": [work]})
        return FakeResponse(404, {"status": "not found"})

    install_fake_get(monkeypatch, mv, handler)

    result = mv.verify_reference(ref)

    assert result.status == "Minor"
    assert result.retracted is True


def test_retraction_flag_not_set_for_normal_records(monkeypatch, isolated_cache):
    ref = _ref_without_doi()

    def handler(url, params):
        if url.endswith("/works") and "openalex" in url:
            return FakeResponse(200, {"results": [openalex_work(ref)]})
        return FakeResponse(404, {"status": "not found"})

    install_fake_get(monkeypatch, mv, handler)

    result = mv.verify_reference(ref)

    assert result.retracted is False
    assert not any("撤稿" in n for n in result.notes)


def test_title_candidates_uses_wanfang_for_chinese(monkeypatch):
    from citeguard import metadata_verify as mv
    from citeguard import wanfang
    from citeguard.reference_parser import Reference

    monkeypatch.setattr(mv, "search_openalex", lambda title, limit=5: [])
    monkeypatch.setattr(mv, "search_crossref", lambda title, limit=5: [])
    monkeypatch.setattr(wanfang, "available", lambda: True)
    monkeypatch.setattr(
        wanfang,
        "search",
        lambda query, rows=3: [
            {"Title": ["人工智能教育应用"], "Creator": ["张三", "李四"], "PublishYear": 2021,
             "PeriodicalTitle": ["现代教育技术"], "Page": "1-8", "DOI": ""}
        ],
    )
    monkeypatch.setattr(
        wanfang,
        "record_to_candidate_fields",
        lambda record: {
            "title": "人工智能教育应用", "doi": "", "year": 2021,
            "authors": "张三; 李四", "venue": "现代教育技术", "volume": "",
            "issue": "4", "pages": "1-8", "abstract": "摘要", "url": "https://example.org/wf",
        },
    )
    ref = Reference(raw="[1] 张三. 人工智能教育应用[J]. 现代教育技术, 2021(4): 1-8.", title="人工智能教育应用", authors=["张三"], year=2021, venue="现代教育技术")
    sources: list[str] = []
    candidates = mv._title_candidates(ref, sources=sources)
    assert any(c.source == "wanfang" for c in candidates)
    assert "wanfang" in sources


def test_arxiv_id_extraction():
    from types import SimpleNamespace
    from citeguard.metadata_verify import _arxiv_id_of
    def rid(**kw):
        base = dict(doi="", url="", raw="", title="")
        base.update(kw)
        return SimpleNamespace(**base)
    assert _arxiv_id_of(rid(raw="[1] A. Author. arXiv:2205.14135 [cs.LG].")) == "2205.14135"
    assert _arxiv_id_of(rid(url="https://arxiv.org/abs/1810.04805v2")) == "1810.04805"
    assert _arxiv_id_of(rid(doi="10.48550/arXiv.2307.08691")) == "2307.08691"
    assert _arxiv_id_of(rid(title="no id here")) == ""


def test_canonical_venue_spacing():
    from citeguard.metadata_verify import _venue_match
    assert _venue_match("ACL", "Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics")
    assert _venue_match("NeurIPS", "Advances in Neural Information Processing Systems 34")
    assert not _venue_match("ACL", "Nature")


def test_semantic_scholar_off_by_default(monkeypatch):
    from citeguard import metadata_verify as mv
    monkeypatch.delenv("CITEGUARD_S2", raising=False)
    called = []
    monkeypatch.setattr(mv, "_request", lambda *a, **k: called.append(1))
    assert mv.search_semantic_scholar("Attention is all you need") == []
    assert not called


def test_offline_mode_skips_network(monkeypatch):
    """CITEGUARD_OFFLINE must never turn missing network into a fake accusation."""
    from citeguard import config

    monkeypatch.setattr(config, "OFFLINE", True)
    called = []
    monkeypatch.setattr(mv, "_request", lambda *a, **k: called.append(1))
    ref = parse_reference("[1] 张三. 中文引文核验[J]. 情报学报, 2024, 12(3): 10-20.")
    result = mv.verify_reference(ref)
    assert result.status == "Unknown"
    assert result.sources == ["offline"]
    assert "离线模式" in " ".join(result.notes)
    assert not called


def test_agreement_sources_requires_title_and_year():
    ref = _ref_without_doi(title="Attention is all you need", year=2017)
    cands = [
        Candidate(source="openalex", title="Attention is all you need", year=2017),
        Candidate(source="crossref", title="Attention is all you need", year=2017),
        Candidate(source="arxiv", title="Attention is all you need", year=2016),
    ]
    assert mv._agreement_sources(ref, cands) == ["crossref", "openalex"]


def test_agreement_sources_is_empty_for_a_single_weak_lead():
    ref = _ref_without_doi(title="Attention is all you need", year=2017)
    cands = [Candidate(source="openalex", title="A different paper", year=2017)]
    assert mv._agreement_sources(ref, cands) == []

def test_source_circuit_breaker_skips_repeated_failures(monkeypatch):
    from citeguard import metadata_verify as mv

    mv.reset_source_health()
    calls = []

    class _Resp:
        status_code = 429
        headers = {"Retry-After": "600"}

        def json(self):
            return {}

    def fake_get(url, **kwargs):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(mv.requests, "get", fake_get)
    monkeypatch.setattr(mv.time, "sleep", lambda _s: None)
    assert mv.search_openalex("Some Title") == []
    first = len(calls)
    assert first >= 1
    assert mv.search_openalex("Another Title") == []
    assert len(calls) == first
    health = mv.source_health()
    assert health["degraded"].get("openalex", 0) > 0
    assert health["errors"] >= 1
    mv.reset_source_health()
