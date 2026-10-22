"""Tests for the GB/T 7714-2025 field-rule engine."""
from __future__ import annotations

import pytest

from citeguard.gbt7714 import (
    check_authors,
    check_punctuation,
    check_reference,
    check_reference_list,
    summarize,
)
from citeguard.reference_parser import Reference, parse_reference


def _journal_ref(**overrides) -> Reference:
    values = dict(
        raw="[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/x.",
        index=1,
        authors=["张三"],
        title="题名",
        doc_type="J",
        venue="期刊",
        year=2020,
        volume="31",
        issue="2",
        pages="10-20",
        doi="10.1234/x",
    )
    values.update(overrides)
    return Reference(**values)


def test_present_required_fields_produce_no_field_errors():
    result = check_reference(parse_reference(
        "[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/x."
    ))
    bad_fields = {"title", "venue", "year", "volume", "issue", "pages", "doi"}
    assert not [i for i in result.issues if i.level == "error" and i.field in bad_fields]


def test_missing_required_fields_reported_as_errors():
    result = check_reference(Reference(raw="[1] ???", doc_type="J", title=""))
    fields = {i.field for i in result.issues if i.level == "error"}
    assert "title" in fields
    assert "venue" in fields
    assert "year" in fields


def test_missing_volume_and_issue_warns():
    result = check_reference(_journal_ref(volume="", issue=""))
    assert any(i.field == "volume" and i.level == "warning" for i in result.issues)


def test_recommended_doi_warns_when_missing():
    result = check_reference(_journal_ref(doi=""))
    assert any(i.field == "doi" and i.level == "warning" for i in result.issues)


def test_all_caps_author_warns_about_2015_style():
    issues = check_authors(_journal_ref(authors=["ZHANG San"]))
    assert issues and "2015" in issues[0].message


def test_missing_final_period_warns():
    issues = check_punctuation(_journal_ref(raw="张 三. 题名[J]. 期刊, 2020, 31(2): 10-20"))
    assert any("末尾" in i.message for i in issues)


def test_unknown_type_code_warns():
    result = check_reference(_journal_ref(doc_type="QQ", raw="张三. 题名[QQ]. 期刊, 2020."))
    assert any(i.field == "doc_type" and i.level == "warning" for i in result.issues)


def test_eb_without_url_is_error():
    ref = Reference(raw="[1] 机构. 网页[EB/OL]. (2020-01-01)[2021-01-01]. https://x.org.",
                    doc_type="EB", title="网页", url="https://x.org", access_date="2021-01-01")
    good = check_reference(ref)
    assert not [i for i in good.issues if i.field == "url" and i.level == "error"]
    bad = check_reference(Reference(raw="[1] 机构. 网页[EB].", doc_type="EB", title="网页"))
    assert any(i.field == "url" and i.level == "error" for i in bad.issues)


def test_summarize_counts_and_average():
    results = check_reference_list([_journal_ref(), _journal_ref(volume="", issue="")])
    summary = summarize(results)
    assert summary["count"] == 2
    assert summary["errors"] == sum(r.errors for r in results)
    assert summary["clean"] == sum(1 for r in results if r.errors == 0)
    assert 0 <= summary["avg_score"] <= 100


def test_summarize_empty_list():
    assert summarize([]) == {"count": 0, "avg_score": 0, "errors": 0, "warnings": 0, "clean": 0}


def test_canonical_entry_has_no_punctuation_error():
    """Regression: 题名[J] is correct GB/T 7714 order; only 题名.[J] is an error."""
    result = check_reference(parse_reference(
        "[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/x."
    ))
    punctuation_errors = [i for i in result.issues if i.field == "punctuation" and i.level == "error"]
    assert punctuation_errors == []
    assert result.errors == 0
