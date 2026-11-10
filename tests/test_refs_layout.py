import pytest

fitz = pytest.importorskip("pymupdf")


def _make_pdf(path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 620), "References", fontsize=12)
    page.insert_text((72, 650), "A. Author. A study of things. Journal of Tests, 2020.", fontsize=9)
    page.insert_text((82, 662), "Continued line of the same entry.", fontsize=9)
    page.insert_text((72, 690), "B. Writer. Another study of more things. 2021.", fontsize=9)
    page.insert_text((82, 702), "With a second continued line.", fontsize=9)
    doc.save(str(path))
    doc.close()


def test_extract_hanging_indent_entries(tmp_path):
    from citeguard.refs_layout import extract_reference_entries

    pdf = tmp_path / "refs.pdf"
    _make_pdf(pdf)
    entries = extract_reference_entries(pdf)
    assert len(entries) == 2, entries
    assert "A study of things" in entries[0]
    assert "Continued line" in entries[0]
    assert "Another study" in entries[1]


def test_extract_returns_empty_without_reference_heading(tmp_path):
    from citeguard.refs_layout import extract_reference_entries

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 720), "Introduction", fontsize=12)
    page.insert_text((72, 700), "This paper studies something.", fontsize=9)
    pdf = tmp_path / "plain.pdf"
    doc.save(str(pdf))
    doc.close()
    assert extract_reference_entries(pdf) == []

def test_recover_title_from_org_url_entry():
    from citeguard.refs_layout import recover_title

    entry = (
        "AI@Meta. Llama 3 model card, 2024a. "
        "URL https://github.com/meta-llama/llama3/blob/main/MODEL_CARD.md."
    )
    assert recover_title(entry) == "Llama 3 model card"

def test_title_health_flags_urls_and_name_runs():
    from types import SimpleNamespace
    from citeguard.refs_layout import title_health

    refs = [
        SimpleNamespace(title="Learning long-term dependencies with gradient descent"),
        SimpleNamespace(title="URL ob/main/MODEL_CARD.md"),
        SimpleNamespace(title="A, B, C, D, E, F, G, H"),
    ]
    assert title_health(refs) == 1 / 3
