"""Word (.docx) input and reference-heading detection.

Chinese students write theses in Word, and the reference list often sits in a
table rather than in body paragraphs. These tests pin that behaviour down,
together with the heading variants seen in real papers.
"""
from __future__ import annotations

import docx
import pytest

from citeguard.pdf_extract import extract_text, split_references

BODY = "深度学习在图像分类中取得显著进展[1]。注意力机制被广泛用于序列建模[2]。"
REFS = [
    "[1] He K, Zhang X, Ren S, et al. Deep residual learning for image "
    "recognition[C]. Proceedings of the IEEE Conference on Computer Vision "
    "and Pattern Recognition, 2016: 770-778.",
    "[2] Vaswani A, Shazeer N, Parmar N, et al. Attention is all you need[C]. "
    "Advances in Neural Information Processing Systems, 2017: 5998-6008.",
]


def _make_docx(path, *, refs_in_table: bool):
    document = docx.Document()
    document.add_paragraph("基于深度学习的图像分类综述")
    document.add_paragraph(BODY)
    document.add_paragraph("参考文献")
    if refs_in_table:
        table = document.add_table(rows=len(REFS), cols=1)
        for row, ref in zip(table.rows, REFS):
            row.cells[0].text = ref
    else:
        for ref in REFS:
            document.add_paragraph(ref)
    document.save(str(path))
    return path


def test_docx_body_and_table_references(tmp_path):
    path = _make_docx(tmp_path / "paper.docx", refs_in_table=True)

    text = extract_text(path)

    assert "基于深度学习的图像分类综述" in text
    assert REFS[0][:20] in text  # table cells are not dropped
    assert REFS[1][:20] in text


def test_docx_split_returns_body_and_references(tmp_path):
    path = _make_docx(tmp_path / "paper.docx", refs_in_table=True)

    body, refs_text = split_references(extract_text(path))

    assert "注意力机制" in body
    assert "参考文献" not in refs_text
    assert "[1] He K" in refs_text
    assert "[2] Vaswani A" in refs_text


def test_docx_paragraph_references_roundtrip(tmp_path):
    path = _make_docx(tmp_path / "paper.docx", refs_in_table=False)

    body, refs_text = split_references(extract_text(path))

    assert "深度学习" in body
    assert refs_text.count("[") >= 2


def test_empty_docx_raises_with_hint(tmp_path):
    path = tmp_path / "empty.docx"
    docx.Document().save(str(path))

    with pytest.raises(RuntimeError, match="Word 文件里没有读到文字"):
        extract_text(path)


def test_legacy_doc_reports_save_as_hint(tmp_path):
    path = tmp_path / "old.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0")

    with pytest.raises(ValueError, match="另存为"):
        extract_text(path)


def test_unsupported_suffix_message(tmp_path):
    path = tmp_path / "paper.rtf"
    path.write_bytes(b"{\\rtf1}")

    with pytest.raises(ValueError, match="不支持的文件类型"):
        extract_text(path)


def test_gbk_text_file_is_readable(tmp_path):
    path = tmp_path / "refs.txt"
    path.write_bytes("[1] 张三. 题名[J]. 期刊, 2020, 12(3): 45-56.\n".encode("gb18030"))

    assert "张三" in extract_text(path)


@pytest.mark.parametrize(
    "heading",
    [
        "参考文献",
        "## 参考文献",
        "7 参考文献",
        "参考文献（References）",
        "参考文献：",
        "References",
        "REFERENCES",
        "Bibliography",
        "Works Cited",
        "7. 参考文献",
    ],
)
def test_reference_heading_variants(heading):
    text = f"正文内容[1]。\n{heading}\n[1] 张三. 题名[J]. 期刊, 2020.\n"

    body, refs_text = split_references(text)

    assert "正文内容" in body
    assert "[1] 张三" in refs_text


def test_heading_with_inline_first_reference():
    text = "正文[1]。\n参考文献：[1] 张三. 题名[J]. 期刊, 2020.\n"

    body, refs_text = split_references(text)

    assert "正文" in body
    assert refs_text.startswith("[1] 张三")


def test_heading_like_word_inside_sentence_is_not_a_heading():
    text = "本节说明参考文献的著录要求。\n[1] 张三. 题名[J]. 期刊, 2020.\n"

    body, refs_text = split_references(text)

    assert refs_text == ""
    assert "本节说明" in body


def test_no_heading_returns_whole_text_as_references():
    text = "[1] 张三. 题名[J]. 期刊, 2020.\n[2] 李四. 另一篇[J]. 期刊, 2021.\n"

    body, refs_text = split_references(text)

    assert body == text
    assert refs_text == ""
