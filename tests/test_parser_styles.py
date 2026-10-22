"""Reference parsing for the styles Chinese papers actually mix together.

GB/T entries (``[1] 作者. 题名[J]. 刊名, 年, 卷(期): 页码.``) and English
entries (``Vol.``/``No.``/``pp.``/``In:``) often appear in the same list.
"""
from __future__ import annotations

from citeguard.reference_parser import parse_reference


def test_english_volume_issue_and_pp_pages():
    ref = parse_reference(
        "[1] Smith J A, Doe B. A study of testing[J]. Journal of Testing, 2020, "
        "Vol. 45, No. 3: pp. 770-778."
    )

    assert ref.doc_type == "J"
    assert ref.year == 2020
    assert ref.volume == "45"
    assert ref.issue == "3"
    assert ref.pages == "770-778"
    assert ref.title == "A study of testing"


def test_conference_in_prefix_is_stripped_from_venue():
    ref = parse_reference(
        "[2] Zhang S. Paper title[C]. In: Proceedings of the 2020 Conference on X, 2020: 1-10."
    )

    assert ref.doc_type == "C"
    assert ref.venue == "Proceedings of the 2020 Conference on X"
    assert ref.pages == "1-10"


def test_book_edition_is_kept_as_version():
    ref = parse_reference("[3] 张三. 数据结构[M]. 第2版. 北京: 清华大学出版社, 2020.")

    assert ref.doc_type == "M"
    assert ref.version == "第2版"
    assert ref.place == "北京"
    assert ref.publisher == "清华大学出版社"
    assert ref.year == 2020


def test_chinese_thesis_fields():
    ref = parse_reference("[4] 李四. 论文题目[D]. 北京: 清华大学, 2021.")

    assert ref.doc_type == "D"
    assert ref.place == "北京"
    assert ref.institution == "清华大学"
    assert ref.year == 2021


def test_doi_is_not_mistaken_for_pages():
    ref = parse_reference(
        "[5] 王五. 题名[J]. 期刊, 2019, 8(2): 12-20. DOI: 10.1234/abcd.5678."
    )

    assert ref.pages == "12-20"
    assert ref.doi == "10.1234/abcd.5678"


def test_online_resource_marker_and_url():
    ref = parse_reference(
        "[6] 中国互联网络信息中心. 第51次中国互联网络发展状况统计报告[EB/OL]. "
        "(2023-03-02)[2023-06-01]. https://www.cnnic.net.cn/report.pdf."
    )

    assert ref.doc_type == "EB"
    assert ref.has_online_marker is True
    assert ref.url.startswith("https://www.cnnic.net.cn/")
    assert ref.access_date == "2023-06-01"


def test_type_code_inside_title_brackets_is_not_a_type_marker():
    ref = parse_reference("[7] 张三. 基于[图像]识别的系统[J]. 计算机学报, 2020, 12(3): 45-56.")

    assert ref.doc_type == "J"
    assert "图像" in ref.title


# ---------------------------------------------------------------------------
# APA-style lists (many Chinese social-science journals print these)
# ---------------------------------------------------------------------------

def test_apa_chinese_entry():
    from citeguard.reference_parser import parse_reference_list

    refs = parse_reference_list(
        "鲍振宙, 李董平, 张卫(2014). 累积生态风险与青少年的学业和社交能力: 子女责任感的调节效应. "
        "心理发展与教育, 30(5), 482-495.\n"
        "陈建文, 刘艳(2022). 累积生态风险与高职生学习倦怠. 心理发展与教育, 38(4), 576-583.\n"
        "冯永辉(2016). 青少年压力与吸烟行为的关系. 中国临床心理学杂志, 24(1), 77-80."
    )

    assert len(refs) == 3
    first = refs[0]
    assert first.year == 2014
    assert "鲍振宙" in first.authors
    assert first.title.startswith("累积生态风险")
    assert first.venue == "心理发展与教育"
    assert first.volume == "30"
    assert first.issue == "5"
    assert first.pages == "482-495"


def test_apa_english_entry_without_period_after_year():
    ref = parse_reference(
        "Yu, H. and Li, X. (2025) On the Infinite φ-Order Solutions of Second Order "
        "Linear Differential Equations. Computational Methods and Function Theory, 25, 1-20."
    )

    assert ref.year == 2025
    assert ref.title.startswith("On the Infinite")
    assert ref.venue.startswith("Computational Methods")


def test_apa_standalone_book_gets_type_m():
    ref = parse_reference("季成叶(2006). 儿童少年卫生学.")

    assert ref.doc_type == "M"
    assert ref.year == 2006
    assert ref.title == "儿童少年卫生学"


def test_apa_split_wins_over_sparse_numbered_lines():
    from citeguard.reference_parser import split_entries

    text = (
        "1. 前言\n"
        "鲍振宙, 李董平(2014). 累积生态风险研究. 心理发展与教育, 30(5), 482-495.\n"
        "陈建文(2022). 累积生态风险与学习倦怠. 心理发展与教育, 38(4), 576-583.\n"
        "冯永辉(2016). 青少年压力与吸烟行为. 中国临床心理学杂志, 24(1), 77-80."
    )

    entries = split_entries(text)

    assert len(entries) == 3
    assert all("(" in e for e in entries)


def test_chinese_author_comma_title_without_period():
    ref = parse_reference("[7] 宋玉茹, 平台算法推荐下消费者理性决策的理论依据与实践路径[J]. 价格理论与实践, 2025(6): 106-111.")

    assert ref.authors == ["宋玉茹"]
    assert ref.title.startswith("平台算法推荐")
    assert ref.year == 2025


def test_bare_page_number_is_not_an_entry():
    from citeguard.reference_parser import split_entries

    entries = split_entries(
        "[1] 张三. 题名[J]. 期刊, 2020, 12(3): 45-56.\n"
        "[2] 李四. 另一篇[J]. 期刊, 2021, 3(1): 1-9.\n"
        "1177."
    )

    assert len(entries) == 2


def test_wrapped_year_line_is_not_entry_number():
    from citeguard.reference_parser import split_entries

    text = (
        "[1] 熊浩, 张晨. 监管与市场调节下大数据杀熟治理研究[J/OL]. 海南大学学报(社会科学版),\n"
        "2025. https://doi.org/10.15886/j.cnki.hnus.202410.0119, 2026-04-28.\n"
        "[2] 王五. 另一篇[J]. 期刊, 2021, 3(1): 1-9."
    )

    entries = split_entries(text)

    assert len(entries) == 2
    assert entries[0].startswith("[1] 熊浩")
    assert "2025. https" in entries[0]
