"""Abstract enrichment for the local library (web "自动补摘要" action).

The option must be conservative: only entries without an abstract are touched,
only close title matches count, and one broken entry cannot abort the batch.
"""
from __future__ import annotations

import pytest

from citeguard import abstract_enrich
from citeguard.local_library import Library, LibraryEntry
from citeguard.metadata_verify import Candidate

TITLE = "累积生态风险与大学生的健康危险行为"


def _entry(title: str = TITLE, **kwargs) -> LibraryEntry:
    base = {"title": title, "year": 2019}
    base.update(kwargs)
    return LibraryEntry(**base)


def _candidate(title: str = TITLE, year: int | None = 2019, abstract: str = "摘要正文") -> Candidate:
    return Candidate(source="openalex", title=title, year=year, abstract=abstract)


def test_enrich_missing_fills_only_entries_without_abstract(monkeypatch):
    library = Library([_entry(), _entry("已有摘要的论文", abstract="已有摘要")])
    monkeypatch.setattr(
        abstract_enrich,
        "candidates_for",
        lambda entry, use_crossref=True: [_candidate()],
    )

    result = abstract_enrich.enrich_missing(library, limit=10)

    assert result["tried"] == 1
    assert result["enriched"] == 1
    assert result["errors"] == 0
    assert result["remaining"] == 0
    assert library.entries[0].abstract == "摘要正文"
    assert library.entries[1].abstract == "已有摘要"


def test_enrich_missing_respects_limit_and_reports_remaining(monkeypatch):
    library = Library([_entry(f"{TITLE}{i}") for i in range(3)])
    monkeypatch.setattr(
        abstract_enrich,
        "candidates_for",
        lambda entry, use_crossref=True: [_candidate()],
    )

    result = abstract_enrich.enrich_missing(library, limit=2)

    assert result["tried"] == 2
    assert result["enriched"] == 2
    assert result["remaining"] == 1
    assert result["total_missing"] == 3
    assert sum(1 for e in library.entries if e.abstract) == 2


def test_enrich_missing_rejects_loose_title_matches(monkeypatch):
    library = Library([_entry()])
    monkeypatch.setattr(
        abstract_enrich,
        "candidates_for",
        lambda entry, use_crossref=True: [_candidate(title="完全不相关的另一篇论文标题")],
    )

    result = abstract_enrich.enrich_missing(library, limit=5)

    assert result["enriched"] == 0
    assert result["missing"] == 1
    assert library.entries[0].abstract == ""


def test_enrich_missing_rejects_year_mismatch(monkeypatch):
    library = Library([_entry()])
    monkeypatch.setattr(
        abstract_enrich,
        "candidates_for",
        lambda entry, use_crossref=True: [_candidate(year=2001)],
    )

    assert abstract_enrich.enrich_missing(library, limit=5)["enriched"] == 0
    assert library.entries[0].abstract == ""


def test_enrich_missing_survives_one_network_error(monkeypatch):
    library = Library([_entry(), _entry("第二篇待补摘要")])

    def broken(entry, use_crossref=True):
        if entry.title == TITLE:
            raise RuntimeError("network down")
        return [_candidate(title=entry.title, year=entry.year)]

    monkeypatch.setattr(abstract_enrich, "candidates_for", broken)

    result = abstract_enrich.enrich_missing(library, limit=5)

    assert result["errors"] == 1
    assert result["enriched"] == 1
    assert any(d["status"] == "error" and "network down" in d["detail"] for d in result["details"])
    assert library.entries[1].abstract == "摘要正文"


def test_enrich_missing_empty_library_is_a_noop(monkeypatch):
    monkeypatch.setattr(
        abstract_enrich,
        "candidates_for",
        lambda entry, use_crossref=True: pytest.fail("must not be called"),
    )
    result = abstract_enrich.enrich_missing(Library(), limit=5)
    assert (result["tried"], result["enriched"], result["remaining"]) == (0, 0, 0)
