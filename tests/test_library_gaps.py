"""Coverage-gap dashboard for the local reference library (A2)."""

from citeguard.local_library import Library, LibraryEntry
from web.app import _library_gaps_csv, _library_gaps_payload


def _sample_library() -> Library:
    return Library(
        [
            LibraryEntry(
                title="中文题录完整",
                authors="张三",
                year="2024",
                venue="情报学报",
                pages="1-10",
                doi="10.9999/zh",
                abstract="摘要",
            ),
            LibraryEntry(title="English title missing fields", authors="Smith"),
        ]
    )


def test_gap_payload_splits_language_and_counts_missing_fields():
    payload = _library_gaps_payload(_sample_library())

    assert payload["total"] == 2
    assert payload["complete"] == 1
    assert payload["complete_pct"] == 50.0
    assert payload["missing"]["doi"] == 1
    assert payload["missing"]["abstract"] == 1

    assert payload["by_language"]["zh"]["total"] == 1
    assert payload["by_language"]["zh"]["complete"] == 1
    assert payload["by_language"]["en"]["total"] == 1
    assert payload["by_language"]["en"]["missing"]["doi"] == 1
    assert payload["by_language"]["en"]["missing"]["abstract"] == 1
    assert payload["by_language"]["unknown"]["total"] == 0

    assert payload["sample_total"] == 1
    sample = payload["samples"][0]
    assert sample["title"] == "English title missing fields"
    assert "doi" in sample["missing"]


def test_gap_csv_lists_every_entry_with_missing_fields():
    text = _library_gaps_csv(_sample_library())
    lines = text.strip().splitlines()

    assert lines[0].startswith("序号,题名,作者")
    assert len(lines) == 3
    assert "中文题录完整" in lines[1]
    assert "完整" in lines[1]
    assert "English title missing fields" in lines[2]
    assert "doi" in lines[2]
