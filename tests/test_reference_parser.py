"""Tests for the heuristic Chinese/English reference parser."""
from __future__ import annotations

import pytest

from citeguard.reference_parser import (
    _expand_numeric,
    parse_intext_citations,
    parse_reference,
    parse_reference_list,
    split_entries,
)

JOURNAL_ZH = (
    "[1] 张三, 李四. 中文引文核验方法研究[J]. 中国科技期刊研究, 2020, 31(2): 10-20. "
    "DOI: 10.1234/abc.123."
)
JOURNAL_EN = (
    "[7] Cécile Tannier, Isabelle Thomas. A Fractal Approach to Identifying Urban Boundaries[J]. "
    "Geographical Analysis, 2011, 43(2): 211-227. DOI: 10.1111/j.1538-4632.2011.00814.x."
)


def test_split_entries_bracket_indices():
    entries = split_entries("[1] A. T1[J]. J, 2020.\n[2] B. T2[J]. J, 2021.")
    assert len(entries) == 2
    assert entries[0].startswith("[1]") and entries[1].startswith("[2]")


def test_split_entries_blank_line_fallback():
    entries = split_entries("A. T1[J]. J, 2020.\n\nB. T2[J]. J, 2021.")
    assert len(entries) == 2


def test_split_entries_line_fallback_for_long_lines():
    long_line = "A. A title that is definitely longer than fifteen characters[J]. J, 2020."
    assert split_entries(long_line) == [long_line]


def test_split_entries_empty():
    assert split_entries("   ") == []


def test_parse_journal_reference_fields():
    ref = parse_reference(JOURNAL_ZH)
    assert ref.index == 1
    assert ref.doc_type == "J"
    assert ref.authors == ["张三", "李四"]
    assert ref.title == "中文引文核验方法研究"
    assert ref.venue == "中国科技期刊研究"
    assert ref.year == 2020
    assert ref.volume == "31"
    assert ref.issue == "2"
    assert ref.pages == "10-20"
    assert ref.doi == "10.1234/abc.123"


def test_parse_english_journal_reference():
    ref = parse_reference(JOURNAL_EN)
    assert ref.title.startswith("A Fractal Approach")
    assert ref.year == 2011
    assert ref.venue == "Geographical Analysis"
    assert ref.pages == "211-227"
    assert ref.doi == "10.1111/j.1538-4632.2011.00814.x"


def test_parse_book_fields_place_and_publisher():
    ref = parse_reference("[2] 王五. 信息计量学[M]. 北京: 科学出版社, 2019.")
    assert ref.doc_type == "M"
    assert ref.title == "信息计量学"
    assert ref.place == "北京"
    assert ref.publisher == "科学出版社"
    assert ref.year == 2019


def test_parse_thesis_fields_place_and_institution():
    ref = parse_reference("[3] 赵六. 学位论文题名[D]. 上海: 复旦大学, 2021.")
    assert ref.doc_type == "D"
    assert ref.place == "上海"
    assert ref.institution == "复旦大学"
    assert ref.year == 2021


def test_parse_reference_list_numbers_entries():
    refs = parse_reference_list("[1] A. T1[J]. J, 2020.\n[2] B. T2[J]. J, 2021.")
    assert [r.index for r in refs] == [1, 2]


def test_sample_paper_has_twelve_references(sample_refs):
    assert len(sample_refs) == 12
    assert sample_refs[0].doi == "10.1360/972013-150"
    assert sample_refs[-1].doi == "10.9999/fake.0002.2024"


def test_sample_paper_duplicate_doi_with_year_drift(sample_refs):
    # [1] and [9] intentionally share a DOI but differ by one year.
    assert sample_refs[0].doi == sample_refs[8].doi
    assert sample_refs[0].year != sample_refs[8].year


def test_parse_numeric_intext_ranges_and_lists():
    cites = [c for c in parse_intext_citations("A[1] B[2-4] C[5,7].") if c.kind == "numeric"]
    assert [c.numbers for c in cites] == [[1], [2, 3, 4], [5, 7]]


def test_parse_author_year_intext():
    cites = parse_intext_citations("已有研究表明（张三, 2020）。")
    assert len(cites) == 1
    cite = cites[0]
    assert cite.kind == "author_year"
    assert cite.authors == ["张三"]
    assert cite.year == 2020


def test_expand_numeric_ignores_invalid_ranges():
    assert _expand_numeric("5-2") == []
    assert _expand_numeric("2,5-7") == [2, 5, 6, 7]


def test_parse_reference_without_type_code_defaults_to_journal():
    ref = parse_reference("张三. 题名. 期刊, 2020. https://example.org/x")
    assert ref.doc_type == "J"
    assert ref.url == "https://example.org/x"


def test_bare_url_lines_are_not_references():
    refs = parse_reference_list(
        "[1] https://doi.org/10.1177/00336882231162868\n"
        "[2] 张三. 题名[J]. 期刊, 2020, 1(1): 1-9. https://doi.org/10.1/abc\n"
    )

    assert len(refs) == 1
    assert refs[0].index == 1  # renumbered after dropping the URL-only line
    assert "题名" in refs[0].title
