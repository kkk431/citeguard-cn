"""PDF page furniture removal (running headers/footers, page numbers).

These lines land in the middle of the reference list after text extraction and
break entry splitting, so they are stripped before splitting.
"""
from __future__ import annotations

from citeguard.pdf_extract import strip_repeated_lines


def _page(body: str, header: str) -> str:
    return f"{header}\n{body}\n"


def test_repeated_header_lines_are_removed():
    pages = []
    for i in range(6):
        pages.append(_page(f"[{i + 1}] 张三. 题名{i}[J]. 期刊, 2020, 12(3): 45-56.", "心理科学进展"))
    text = "\n".join(pages)

    cleaned = strip_repeated_lines(text)

    assert "心理科学进展" not in cleaned
    assert cleaned.count("[1] 张三") == 1


def test_header_with_changing_page_numbers_is_removed():
    pages = []
    for i in range(5):
        pages.append(_page(f"[{i + 1}] 李四. 论文{i}[J]. 期刊, 2021, 4(2): 1-9.", f"软件学报 {100 + i}"))
    text = "\n".join(pages)

    cleaned = strip_repeated_lines(text)

    assert "软件学报" not in cleaned
    assert "论文3" in cleaned


def test_short_document_is_untouched():
    text = "参考文献\n[1] 张三. 题名[J]. 期刊, 2020."

    assert strip_repeated_lines(text) == text


def test_reference_entries_are_not_dropped_as_furniture():
    lines = [f"[{i}] 作者{i}. 题名{i}[J]. 期刊, 20{10 + i}, 1({i}): 1-9." for i in range(1, 41)]
    text = "\n".join(lines)

    cleaned = strip_repeated_lines(text)

    assert len(cleaned.splitlines()) == 40
