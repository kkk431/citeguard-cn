"""pypdfium2 layout fallback: no PyMuPDF dependency, sane line grouping."""

from pathlib import Path


def test_module_source_has_no_pymupdf_import():
    src = Path(__file__).resolve().parents[1] / "src" / "citeguard" / "refs_layout.py"
    text = src.read_text(encoding="utf-8").lower()
    assert "import fitz" not in text
    assert "import pymupdf" not in text


class _FakeTextPage:
    def __init__(self):
        self._rects = [(72.0, 700.0, 300.0, 712.0), (72.0, 688.0, 300.0, 700.0)]

    def count_rects(self):
        return len(self._rects)

    def get_rect(self, i):
        return self._rects[i]

    def get_text_bounded(self, left, bottom, right, top):
        return "First line" if top > 700.5 else "Second line"


class _FakePage:
    def get_size(self):
        return (612.0, 792.0)

    def get_textpage(self):
        return _FakeTextPage()


def test_lines_groups_rects_by_vertical_centre():
    from citeguard.refs_layout import _lines

    lines = _lines(_FakePage())
    assert [text for _, _, text in lines] == ["First line", "Second line"]
    assert lines[0][0] < lines[1][0]
