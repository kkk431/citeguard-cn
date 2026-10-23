"""GB/T-style entry generation from database metadata."""
from __future__ import annotations

from citeguard.format_gbt import format_gbt_entry, format_from_reference, format_reference_list
from citeguard.reference_parser import parse_reference


def test_journal_entry_uses_first_three_authors_and_etal():
    entry = format_gbt_entry(
        title="Deep residual learning for image recognition",
        authors=["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"],
        doc_type="J",
        venue="IEEE Transactions on Pattern Analysis and Machine Intelligence",
        year=2016,
        volume="40",
        issue="6",
        pages="770-778",
        doi="10.1109/TPAMI.2016.2577031",
    )

    assert entry.startswith("Kaiming He, Xiangyu Zhang, Shaoqing Ren, et al. ")
    assert "[J]" in entry
    assert "2016, 40(6): 770-778." in entry
    assert entry.endswith("DOI: 10.1109/TPAMI.2016.2577031.")


def test_chinese_journal_entry_uses_deng():
    entry = format_gbt_entry(
        title="累积生态风险与青少年的学业和社交能力",
        authors=["鲍振宙", "李董平", "张卫", "王艳辉"],
        doc_type="J",
        venue="心理发展与教育",
        year=2014,
        volume="30",
        issue="5",
        pages="482-495",
    )

    assert entry.startswith("鲍振宙, 李董平, 张卫, 等. ")
    assert "心理发展与教育, 2014, 30(5): 482-495." in entry


def test_book_entry_has_place_and_publisher():
    entry = format_gbt_entry(
        title="数据结构",
        authors=["严蔚敏"],
        doc_type="M",
        place="北京",
        publisher="清华大学出版社",
        year=2020,
    )

    assert "[M]" in entry
    assert "北京, 清华大学出版社, 2020." in entry


def test_missing_year_still_renders():
    entry = format_gbt_entry(
        title="Some title",
        authors=["A B"],
        doc_type="J",
        venue="Some Journal",
        pages="1-10",
    )

    assert "[J]" in entry
    assert "Some Journal" in entry
    assert entry.endswith("1-10.")


def test_format_from_reference_retypesets_parsed_entry():
    ref = parse_reference(
        "[1] 张三, 李四, 王五, 赵六. 题名[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/x."
    )
    entry = format_from_reference(ref)

    assert entry.startswith("张三, 李四, 王五, 等. ")
    assert "题名[J]." in entry
    assert "期刊, 2020, 31(2): 10-20." in entry
    assert "DOI: 10.1234/x." in entry


def test_format_from_reference_keeps_book_place_and_publisher():
    ref = parse_reference("[2] 李四. 数据结构[M]. 北京: 清华大学出版社, 2020.")

    entry = format_from_reference(ref)

    assert "[M]" in entry
    assert "北京, 清华大学出版社, 2020." in entry


def test_format_reference_list_keeps_indexes_and_skips_empty():
    from citeguard.reference_parser import Reference

    refs = [
        parse_reference("[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20."),
        Reference(raw="[2] ??", index=2),
    ]
    out = format_reference_list(refs)

    assert out[0]["index"] == 1
    assert out[0]["entry"].startswith("张三. 题名[J].")
    assert out[1]["index"] == 2
    assert out[1]["entry"] == ""
