"""OCR fallback for scanned PDFs (optional dependency)."""
from __future__ import annotations

import pytest

from citeguard.ocr import ocr_available

pytestmark = pytest.mark.skipif(not ocr_available(), reason="OCR extra not installed")

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _font_path():
    from pathlib import Path

    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return ""


def _make_scanned_pdf(path):
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")

    font_path = _font_path()
    if not font_path:
        pytest.skip("no CJK font available")
    image = Image.new("RGB", (1600, 1754), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, 44)
    lines = [
        "参考文献",
        "[1] 张三. 论引文核验的可验证性[J]. 计算机学报, 2020, 43(5): 1-10.",
        "[2] 李四. 中文文献元数据覆盖研究[J]. 图书情报工作, 2021, 65(3): 20-28.",
    ]
    y = 100
    for line in lines:
        draw.text((80, y), line, fill="black", font=font)
        y += 100
    image.save(str(path), "PDF", resolution=150.0)
    return path


def test_scanned_pdf_is_ocred(tmp_path):
    from citeguard.pdf_extract import extract_text

    path = _make_scanned_pdf(tmp_path / "scan.pdf")
    text = extract_text(path)

    assert len(text) > 20
    assert "参考文献" in text
    assert "计算机学报" in text


def test_ocr_text_can_be_parsed_into_references(tmp_path):
    from citeguard.pdf_extract import extract_text, split_references
    from citeguard.reference_parser import parse_reference_list

    path = _make_scanned_pdf(tmp_path / "scan.pdf")
    _body, refs_text = split_references(extract_text(path))
    refs = parse_reference_list(refs_text)

    assert len(refs) >= 2
    # OCR noise ("[J]" -> "[]", inserted letters) is expected; the parser must
    # still recover authors, title, source and year.
    first = refs[0]
    assert first.authors == ["张三"]
    assert "核验" in first.title
    assert "计算机学报" in (first.venue or first.raw)
    assert first.year == 2020
    assert first.volume == "43"
