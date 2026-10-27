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


def test_arxiv_identifier_fills_missing_year():
    """Preprints often omit the year; arXiv:YYMM.NNNNN is deterministic."""
    ref = parse_reference(
        "[4] Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. “Layer Normalization”. "
        "In: arXiv preprint arXiv:1607.06450"
    )
    assert ref.title == "Layer Normalization"
    assert ref.year == 2016
    assert ref.extra.get("year_from_arxiv") is True


def test_arxiv_year_ignores_invalid_month_and_old_ids():
    assert parse_reference("X. A paper. arXiv:1613.12345").year is None
    ref = parse_reference("X. A paper. arXiv:hep-th/9901001")
    assert ref.year == 1999


def test_bare_url_labeled_lines_are_not_references():
    """A PDF link line sometimes keeps its "url:" label - still not a citation."""
    refs = parse_reference_list(
        "[36] url: https://doi.org/10.5281/zenodo.5371628.\n"
        "[37] 张三. 题名[J]. 期刊, 2020, 1(1): 1-9.\n"
    )

    assert len(refs) == 1
    assert refs[0].title == "题名"


def test_bare_url_lines_are_not_references():
    refs = parse_reference_list(
        "[1] https://doi.org/10.1177/00336882231162868\n"
        "[2] 张三. 题名[J]. 期刊, 2020, 1(1): 1-9. https://doi.org/10.1/abc\n"
    )

    assert len(refs) == 1
    assert refs[0].index == 1  # renumbered after dropping the URL-only line
    assert "题名" in refs[0].title


# ---------------------------------------------------------------------------
# Web citations (common in Chinese humanities / social-science reference lists)
# ---------------------------------------------------------------------------

def test_webpage_reference_without_type_code():
    ref = parse_reference(
        "[15] Stanford University. Bio-X: About Bio-X. "
        "http://biox.stanford.edu/about/history.html"
    )
    assert ref.doc_type == "EB"
    assert ref.authors == ["Stanford University"]
    assert ref.title == "Bio-X: About Bio-X"
    assert ref.url == "http://biox.stanford.edu/about/history.html"
    assert ref.venue == ""  # the institution is the author, not the venue


def test_webpage_reference_keeps_long_corporate_author_whole():
    ref = parse_reference(
        "[17] Harvard John A. Paulson School of Engineering and Applied Sciences. "
        "PhD in Applied Mathematics. "
        "https://www.seas.harvard.edu/programs/graduate/applied-mathematics"
    )
    assert ref.doc_type == "EB"
    assert ref.authors == [
        "Harvard John A. Paulson School of Engineering and Applied Sciences"
    ]
    assert ref.title == "PhD in Applied Mathematics"


def test_webpage_reference_joins_sub_unit_to_author():
    ref = parse_reference(
        "[23] Harvard Medical School. Department of Biomedical Informatics. "
        "Bioinformatics and Integrative Genomics (BIG) PhD Track. https://bigphd.hms.harvard.edu/"
    )
    assert ref.authors == ["Harvard Medical School. Department of Biomedical Informatics"]
    assert ref.title.startswith("Bioinformatics and Integrative Genomics")


def test_apa_style_author_list_continuation_is_not_title():
    ref = parse_reference(
        "[22] Sakr, M.F. and Goldstein, S.C. Cloud Computing: 15-619/15-819, "
        "Carnegie Mellon University. http://www.cs.cmu.edu/~msakr/15619-s24/"
    )
    assert ref.authors == ["Sakr, M.F", "Goldstein, S.C"]
    assert ref.title.startswith("Cloud Computing")


def test_initials_without_final_period_are_one_author():
    ref = parse_reference(
        "[32] Meyer, A.R. Responsible Research Approach. "
        "https://people.csail.mit.edu/meyer/AreaII/ethics/page-03.html"
    )
    assert ref.authors == ["Meyer, A.R"]
    assert ref.title == "Responsible Research Approach"


def test_cjk_transliterated_author_with_interpunct():
    ref = parse_reference(
        "[12] 拉尔夫·泰勒. 课程与教学的基本原理[M]. 施良方, 译. 北京: 人民教育出版社, 1994: 2."
    )
    assert ref.authors == ["拉尔夫·泰勒"]
    assert ref.title == "课程与教学的基本原理"
    assert ref.doc_type == "M"


def test_apa_corporate_author_is_not_split_on_commas():
    ref = parse_reference(
        "[26] National Academies of Sciences, Engineering, and Medicine (2018) "
        "Graduate STEM Education for the 21st Century. The National Academies Press. "
        "https://doi.org/10.17226/24913"
    )
    assert ref.authors == ["National Academies of Sciences, Engineering, and Medicine"]
    assert ref.title.startswith("Graduate STEM Education")


def test_webpage_apa_entry_with_url_tail_is_eb():
    ref = parse_reference(
        "[35] Yale University, Graduate School of Arts and Sciences (2021) "
        "Sharing the Report of the Humanities Doctoral Education Advisory Working Group. "
        "https://gsas.yale.edu/about/news-announcements/sharing-report"
    )
    assert ref.doc_type == "EB"
    assert ref.authors == ["Yale University, Graduate School of Arts and Sciences"]
    assert ref.title.startswith("Sharing the Report")
    assert ref.venue == ""


def test_doi_digits_are_not_year_publisher_or_pages():
    """A DOI such as 10.1007/978-1-4614-2062-0 must not yield year 2062."""
    ref = parse_reference(
        "[2] Carayannis, E.G., Campbell, D.F. Mode 3 Knowledge Production in "
        "Quadruple Helix Innovation Systems: 21st-Century Democracy, Innovation, "
        "and Entrepreneurship for Development[M]. Springer, 29. "
        "https://doi.org/10.1007/978-1-4614-2062-0, 2012: 29."
    )
    assert ref.doc_type == "M"
    assert ref.year == 2012
    assert ref.doi == "10.1007/978-1-4614-2062-0"
    assert ref.publisher != "1007/978-1-4614-2062-0"
    assert "doi.org" not in ref.publisher


def test_ocr_lost_closing_bracket_of_type_marker():
    """OCR often reads "[J]" as "[J." — the type and fields must still parse."""
    ref = parse_reference(
        "[1]张英浩,盛科荣,孙威,等.中国直播电商经济的时空演变特征与区域发展模式"
        "[J.地理学报,2026,81(4):1157-"
    )
    assert ref.doc_type == "J"
    assert ref.authors == ["张英浩", "盛科荣", "孙威"]
    assert ref.title == "中国直播电商经济的时空演变特征与区域发展模式"
    assert ref.venue == "地理学报"
    assert (ref.volume, ref.issue) == ("81", "4")


def test_ocr_empty_type_marker_and_year_issue_not_volume():
    """A lost "[J]" leaves "[]"; "2022(4)" is year+issue, not volume 2022."""
    ref = parse_reference("[2]迟妍.古典园林在现代景观设计中的作用[].陶瓷,2022(4):167-169.")
    assert ref.doc_type == "J"
    assert ref.extra.get("type_marker_lost") is True
    assert ref.title == "古典园林在现代景观设计中的作用"
    assert ref.year == 2022
    assert ref.volume == ""
    assert ref.issue == "4"
    assert ref.pages == "167-169"


def test_ocr_garbled_type_marker_is_repaired():
    """RapidOCR reads "[J]" as "[刀." / "[."; the entry must keep its boundary."""
    ref = parse_reference(
        "[14] 马浩杰,史妍欣,陈沁文.乡村振兴背景下花木电商发展路径探析"
        "[刀.现代营销, 2023(33): 107-109."
    )
    assert ref.doc_type == "J"
    assert ref.title == "乡村振兴背景下花木电商发展路径探析"
    assert ref.venue == "现代营销"
    assert ref.year == 2023
    assert ref.issue == "33"
    assert ref.pages == "107-109"
    assert ref.extra.get("type_marker_lost") is True

    ref2 = parse_reference(
        "[19] 董翰松.AI与大数据在电商供应链优化中的应用效果及经济价值评估"
        "[.电子商务评论,2025,14(12):3031-3040."
    )
    assert ref2.doc_type == "J"
    assert ref2.title.startswith("AI与大数据")
    assert ref2.venue == "电子商务评论"
    assert (ref2.volume, ref2.issue) == ("14", "12")


def test_ocr_merged_type_marker_with_venue():
    """OCR can read "[J]." as "[" so the venue is glued to the title."""
    ref = parse_reference(
        "张英浩,盛科荣,孙威,等.中国直播电商经济的时空演变特征与区域发展模式"
        "[地理学报,2026,81(4):1157-1177."
    )
    assert ref.doc_type == "J"
    assert ref.authors == ["张英浩", "盛科荣", "孙威"]
    assert ref.title == "中国直播电商经济的时空演变特征与区域发展模式"
    assert ref.venue == "地理学报"
    assert ref.year == 2026
    assert (ref.volume, ref.issue) == ("81", "4")
    assert ref.pages == "1157-1177"
    assert ref.extra.get("type_marker_lost") is True


def test_leading_unnumbered_entry_is_recovered():
    """OCR sometimes loses only the first "[1]"; keep that entry before [2]."""
    refs = parse_reference_list(
        "张英浩,盛科荣,孙威,等.中国直播电商经济的时空演变特征与区域发展模式"
        "[地理学报,2026,81(4):1157-1177.\n"
        "[2] 迟妍.古典园林在现代景观设计中的作用[].陶瓷,2022(4):167-169."
    )
    assert len(refs) == 2
    assert refs[0].title == "中国直播电商经济的时空演变特征与区域发展模式"
    assert refs[0].venue == "地理学报"
    assert refs[1].index == 2
    assert refs[1].title == "古典园林在现代景观设计中的作用"


def test_leading_page_furniture_is_not_a_reference():
    """A header without a year+volume/issue pattern must not become an entry."""
    refs = parse_reference_list(
        "第 81 卷 第 4 期 地理学报 2026 年 4 月 1157-1177\n"
        "[2] 迟妍.古典园林在现代景观设计中的作用[].陶瓷,2022(4):167-169.\n"
        "[3] 沈添天.全域电商视域下的传统园林IP价值重构与产业链延伸策略"
        "[].电子商务评论,2026,15(2):955-961."
    )
    assert len(refs) == 2
    assert refs[0].title == "古典园林在现代景观设计中的作用"
    assert refs[1].title.startswith("全域电商")


def test_ocr_full_stop_after_author_is_the_title_boundary():
    ref = parse_reference(
        "[13] 钱皓宇。短视频营销对游客文创产品购买意愿的影响研究"
        "——以南京钟山风景区为例[].电子商务评论,2025,14(8): 1944-1949."
    )
    assert ref.authors == ["钱皓宇"]
    assert ref.title.startswith("短视频营销")
    assert ref.venue == "电子商务评论"
    assert (ref.volume, ref.issue) == ("14", "8")
    assert ref.pages == "1944-1949"


def test_date_only_wrapped_fragment_is_not_a_reference():
    refs = parse_reference_list(
        "[9] 王志高.年轻人用创意让古典园林破圈[EB/OL].中国江苏网,2024-10-17."
        " https://example.org/news\n"
        "[10] 2025-06-25. https://www.example.org/magazine?id=73\n"
        "[11] 钱雅琴.苏州园林景区经营管理模式优化研究[D].苏州:苏州大学,2021."
    )
    assert len(refs) == 2
    assert [r.index for r in refs] == [1, 2]
    assert refs[1].title == "苏州园林景区经营管理模式优化研究"

def test_arxiv_venue_is_split_from_title():
    ref = parse_reference(
        "[2] Dzmitry Bahdanau, Kyunghyun Cho, and Yoshua Bengio. "
        "Neural machine translation by jointly learning to align and translate. "
        "CoRR, abs/1409.0473, 2014."
    )
    assert ref.title == "Neural machine translation by jointly learning to align and translate"
    assert ref.venue.startswith("CoRR")
    assert ref.year == 2014

def test_title_journal_tail_is_split_without_type_marker():
    ref = parse_reference(
        "[13] Sepp Hochreiter and Jürgen Schmidhuber. Long short-term memory. "
        "Neural computation, 9(8):1735–1780, 1997."
    )
    assert ref.title == "Long short-term memory"
    assert ref.venue == "Neural computation"
    assert (ref.volume, ref.issue, ref.pages) == ("9", "8", "1735-1780")
    assert ref.year == 1997
    assert ref.authors == ["Sepp Hochreiter", "Jürgen Schmidhuber"]


def test_title_journal_tail_keeps_penn_treebank_title():
    ref = parse_reference(
        "[25] Mitchell P Marcus, Mary Ann Marcinkiewicz, and Beatrice Santorini. "
        "Building a large annotated corpus of english: The penn treebank. "
        "Computational linguistics, 19(2):313–330, 1993."
    )
    assert ref.title == "Building a large annotated corpus of english: The penn treebank"
    assert ref.venue == "Computational linguistics"
    assert (ref.volume, ref.issue, ref.pages, ref.year) == ("19", "2", "313-330", 1993)


def test_preprint_venue_tail_survives_question_mark():
    ref = parse_reference(
        "[16] Łukasz Kaiser and Samy Bengio. Can active memory replace attention? "
        "In Advances in Neural Information Processing Systems, 2016."
    )
    assert ref.title == "Can active memory replace attention"
    assert "Advances" in ref.venue


def test_split_entries_acl_author_year_list():
    """ACL/EMNLP style: Authors. 2019. Title. (no parentheses, no [n])."""
    text = "\n".join(
        f"Author{i}, A., and Coauthor{i}, B. {2000 + i}. Title number {i}. In Proceedings, pages 1-2."
        for i in range(6)
    )
    entries = split_entries(text)
    assert len(entries) == 6
    assert entries[0].startswith("Author0")
    assert entries[-1].startswith("Author5")


def test_url_fragment_lines_are_not_entries():
    from citeguard.reference_parser import parse_reference_list

    refs = parse_reference_list(
        "[1] A. Author. 2020. A real paper. In: Proc.\n"
        "url: https://doi.org/10.5281/zenodo.5371628."
    )
    assert len(refs) == 1
    assert "zenodo" not in (refs[0].title or "").lower()


def test_year_only_title_is_blanked_not_used():
    from citeguard.reference_parser import parse_reference_list

    refs = parse_reference_list(
        "[1] Kevin Clark, Minh-Thang Luong. 2018.\n"
        "[2] A. Author. 2019. A real title. In: Proc."
    )
    assert len(refs) == 2
    assert refs[0].title == ""
    assert refs[0].extra.get("title_missing") is True

def test_split_at_unparenthesised_year_for_initial_authors():
    from citeguard.reference_parser import parse_reference

    ref = parse_reference(
        "Z. Chen, H. Zhang, X. Zhang, and L. Zhao. 2018. Quora question pairs."
    )
    assert ref.title == "Quora question pairs"
    assert ref.year == 2018
    assert ref.authors[0] == "Z. Chen"


def test_merge_author_year_only_block_into_following_title():
    from citeguard.reference_parser import _merge_titleless_blocks

    merged = _merge_titleless_blocks(
        ["Z. Chen, H. Zhang, X. Zhang, and L. Zhao. 2018.", "Quora question pairs."]
    )
    assert len(merged) == 1
    assert merged[0].startswith("Z. Chen")
    assert merged[0].endswith("Quora question pairs.")
def test_split_author_year_tail_moves_to_next_entry():
    from citeguard.reference_parser import _split_author_year_tail

    prefix, tail = _split_author_year_tail(
        "Long Papers). Association for Computational Linguistics. "
        "Alex Warstadt, Amanpreet Singh, and Samuel R Bowman. 2018."
    )
    assert prefix.endswith("Computational Linguistics.")
    assert tail.startswith("Alex Warstadt")
    assert tail.endswith("2018.")


def test_split_author_year_tail_ignores_initial_prefix():
    from citeguard.reference_parser import _split_author_year_tail

    block = "Z. Chen, H. Zhang, X. Zhang, and L. Zhao. 2018."
    prefix, tail = _split_author_year_tail(block)
    assert tail == ""
    assert prefix == block