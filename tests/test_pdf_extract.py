"""Tests for text/PDF extraction and body/reference splitting."""
from __future__ import annotations

import pytest

from citeguard.pdf_extract import extract_text, normalize_text, split_references


def test_normalize_text_collapses_whitespace():
    assert normalize_text("a\u00a0 b\t\tc\u3000d") == "a b c d"


def test_normalize_text_caps_blank_lines():
    assert normalize_text("a\n\n\n\nb") == "a\n\nb"


def test_split_references_chinese_heading():
    text = "正文第一段[1]。\n\n## 参考文献\n[1] 张三. 题名[J]. 期刊, 2020, 1(2): 3-4.\n"
    body, refs = split_references(text)
    assert "正文第一段" in body
    assert "参考文献" not in refs
    assert refs.strip().startswith("[1] 张三")


def test_split_references_english_heading():
    body, refs = split_references("Body text.\n\nReferences\n[1] A. B. Title[J]. J, 2020.\n")
    assert body.strip() == "Body text."
    assert "[1] A. B. Title" in refs


def test_split_references_markdown_bullet_heading():
    body, refs = split_references("# Title\n\n- References\n[1] A. T[J]. J, 2020.\n")
    assert "# Title" in body
    assert refs.strip().startswith("[1]")


def test_split_references_without_heading_returns_whole_text():
    text = "no heading here, just text"
    assert split_references(text) == (text, "")


def test_extract_text_reads_txt(tmp_path):
    p = tmp_path / "paper.txt"
    p.write_text("Hello\u3000World", encoding="utf-8")
    assert extract_text(p) == "Hello World"


def test_extract_text_reads_markdown(tmp_path):
    p = tmp_path / "paper.md"
    p.write_text("# 标题\n\n正文", encoding="utf-8")
    assert "# 标题" in extract_text(p)


def test_extract_text_rejects_unknown_suffix(tmp_path):
    p = tmp_path / "paper.rtf"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        extract_text(p)


def test_extract_text_rejects_legacy_doc_with_hint(tmp_path):
    p = tmp_path / "old.doc"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        extract_text(p)
    assert ".docx" in str(excinfo.value)


def test_extract_text_reads_docx_paragraphs_and_tables(tmp_path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("第一段正文")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "参考文献"
    table.rows[0].cells[1].text = "[1] 张三. 题名[J]. 期刊, 2020."
    doc.add_paragraph("尾段正文")
    path = tmp_path / "paper.docx"
    doc.save(path)

    text = extract_text(path)

    assert "第一段正文" in text
    assert "尾段正文" in text
    assert "参考文献" in text
    assert "[1] 张三" in text


def test_extract_text_unreadable_pdf_raises_runtime_error(tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.4\nthis is not a real pdf body")
    with pytest.raises(RuntimeError):
        extract_text(p)


def test_utf8_bom_does_not_drop_first_reference(tmp_path):
    """Regression: a BOM-prefixed .txt must keep its first [1] entry."""
    from citeguard.reference_parser import parse_reference_list

    body = "[1] 张三. 题名一[J]. 期刊, 2020.\n[2] 李四. 题名二[J]. 期刊, 2021."
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))

    refs = parse_reference_list(extract_text(path))

    assert len(refs) == 2
    assert refs[0].index == 1


def test_ocr_standalone_reference_numbers_are_merged():
    """OCR often puts "[n]" on its own line; merge it into the entry."""
    from citeguard.ocr import _merge_reference_numbers

    text = (
        "正文引用[1]。\n\n参考文献\n"
        "[1]\n张三. 题名[J]. 期刊, 2020, 1(2): 3-4.\n"
        "[2]\n李四. 题名二[J]. 期刊, 2021, 2(1): 5-6.\n"
    )

    merged = _merge_reference_numbers(text)

    assert "[1] 张三. 题名[J]." in merged
    assert "[2] 李四. 题名二[J]." in merged
    assert "正文引用[1]。" in merged  # body untouched
