"""Tests for the A3 library dashboard snapshot."""
from __future__ import annotations

import json

import pytest

from citeguard.library_stats import (
    TAG_NOTE,
    duplicate_summary,
    language_of,
    summarize,
)
from citeguard.local_library import Library, LibraryEntry


def make_entry(**overrides) -> LibraryEntry:
    data = {
        "title": "Example entry",
        "authors": ["A. Author"],
        "venue": "Journal",
        "year": 2020,
        "volume": "1",
        "issue": "2",
        "pages": "1-10",
        "doi": "10.1000/example",
        "abstract": "An abstract.",
        "source": "local:ris",
        "tags": ["tag"],
    }
    data.update(overrides)
    return LibraryEntry(**data)


def test_empty_library_is_zero_not_error():
    snapshot = summarize(Library())
    assert snapshot["library"]["total"] == 0
    assert snapshot["completeness"]["overall"]["total"] == 0
    assert snapshot["completeness"]["overall"]["pct"] == 0.0
    assert snapshot["years"]["missing"] == 0
    assert snapshot["years"]["median"] is None
    assert snapshot["venues"]["top"] == []
    assert snapshot["duplicates"]["group_count"] == 0
    assert snapshot["tags"]["unique"] == 0
    assert snapshot["coverage"]["reports_provided"] is False
    assert TAG_NOTE in snapshot["notes"]
    json.dumps(snapshot, ensure_ascii=False)  # serialisable


def test_duplicate_groups_by_doi_and_title_year():
    library = Library(
        [
            make_entry(title="One", doi="https://doi.org/10.1000/DUP", year=2021),
            make_entry(title="Two", doi="10.1000/dup", year=2022),
            make_entry(title="Same title", doi="", year=2023),
            make_entry(title="same  TITLE", doi="", year=2023),
            make_entry(title="Unique", doi="10.1000/unique", year=2023),
        ]
    )
    summary = duplicate_summary(library)
    assert summary["group_count"] == 2
    assert summary["entries_in_groups"] == 4
    reasons = {group["reason"] for group in summary["groups"]}
    assert reasons == {"doi", "title_year"}
    assert all(group["count"] == 2 for group in summary["groups"])


def test_year_and_source_distribution():
    library = Library(
        [
            make_entry(title="A", year=2020, source="local:ris"),
            make_entry(title="B", year=2020, source="local:ris"),
            make_entry(title="C", year=None, source="local:endnote"),
            make_entry(title="D", year=2018, source=""),
        ]
    )
    snapshot = summarize(library)
    years = snapshot["years"]
    assert years["with_year"] == 3
    assert years["missing"] == 1
    assert years["min"] == 2018 and years["max"] == 2020
    assert years["median"] == 2020
    assert {row["year"]: row["count"] for row in years["by_year"]} == {"2018": 1, "2020": 2}

    sources = {row["source"]: row for row in snapshot["sources"]["rows"]}
    assert sources["local:ris"]["total"] == 2
    assert sources["local:endnote"]["total"] == 1
    assert sources["未标注"]["total"] == 1
    assert snapshot["sources"]["total"] == 4


def test_tags_are_user_labels_not_semantic_classes():
    library = Library(
        [
            make_entry(title="A", tags=["Methods", "methods"]),
            make_entry(title="B", tags=[]),
            make_entry(title="C", tags=["Data"]),
        ]
    )
    tags = summarize(library)["tags"]
    assert tags["tagged"] == 2
    assert tags["untagged"] == 1
    assert tags["unique"] == 2
    assert tags["rows"][0] == {"tag": "Methods", "count": 2, "pct": 66.7}
    assert tags["note"] == TAG_NOTE


def test_completeness_by_language_and_missing_fields_are_not_errors():
    library = Library(
        [
            make_entry(title="中文题名", doi="10.1000/zh", year=2022),
            make_entry(title="English title", doi="", year=None, abstract=""),
        ]
    )
    snapshot = summarize(library)
    assert language_of("中文题名") == "zh"
    assert language_of("English title") == "en"
    assert language_of("1234") == "unknown"

    overall = snapshot["completeness"]["overall"]
    assert overall["total"] == 2
    assert overall["complete"] == 1
    assert overall["pct"] == 50.0
    assert overall["missing_fields"]["doi"] == 1
    assert overall["missing_fields"]["year"] == 1
    assert overall["missing_fields"]["abstract"] == 1
    assert overall["missing_fields"]["venue"] == 0

    by_language = {row["key"]: row for row in snapshot["completeness"]["by_language"]}
    assert by_language["zh"]["complete"] == 1
    assert by_language["en"]["missing_fields"]["doi"] == 1


def test_coverage_from_reports_and_trend():
    report = {
        "job_id": "job-a",
        "generated_at": "2026-11-26T20:11:48",
        "references": [
            {"verify": {"doi_status": "local"}},
            {"verify": {"sources": ["openalex", "local"]}},
            {"verify": {"doi_status": "crossref", "sources": ["openalex"]}},
        ],
    }
    snapshot = summarize(Library([make_entry()]), [report])
    coverage = snapshot["coverage"]
    assert coverage["reports_provided"] is True
    assert coverage["reports"] == 1
    assert coverage["references"] == 3
    assert coverage["library_hits"] == 2
    assert coverage["pct"] == 66.7
    assert coverage["by_report"][0]["job_id"] == "job-a"
    assert coverage["trend"] == [
        {"month": "2026-11", "reports": 1, "references": 3, "library_hits": 2, "pct": 66.7}
    ]
    assert coverage["entries"]["entries_with_created_at"] == 0
    assert coverage["entries"]["note"]


def test_coverage_skips_unreadable_reports(tmp_path):
    good = tmp_path / "report.json"
    good.write_text(
        json.dumps({"generated_at": "2026-10-01T00:00:00", "references": [{"verify": {"best": {"source": "local"}}}]}),
        encoding="utf-8",
    )
    bad = tmp_path / "missing.json"
    snapshot = summarize(Library(), [str(good), str(bad)])
    coverage = snapshot["coverage"]
    assert coverage["reports"] == 1
    assert coverage["skipped"] == [str(bad)]
    assert coverage["references"] == 1
    assert coverage["pct"] == 100.0


def test_snapshot_is_json_and_real_shape_has_required_sections():
    snapshot = summarize(Library([make_entry()]))
    for section in (
        "sources",
        "years",
        "venues",
        "duplicates",
        "completeness",
        "tags",
        "coverage",
    ):
        assert section in snapshot
    assert snapshot["schema"] == 1
    assert snapshot["venues"]["top"][0] == {"venue": "Journal", "count": 1, "pct": 100.0}
    encoded = json.dumps(snapshot, ensure_ascii=False)
    assert json.loads(encoded)["library"]["total"] == 1
