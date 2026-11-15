from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"
TOPICS = ("ai_education", "medical_imaging")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("topic", TOPICS)
def test_every_static_paper_has_human_or_machine_evidence(topic: str) -> None:
    corpus = _load(DATA / "corpus" / f"{topic}.json")
    extraction = _load(DATA / "extractions" / f"{topic}.json")
    machine = _load(DATA / "extractions_machine" / f"{topic}.json")
    paper_ids = {p["paper_id"] for p in corpus["papers"]}
    covered = {e["paper_id"] for e in extraction["evidence"]} | {
        e["paper_id"] for e in machine["evidence"]
    }
    assert len(paper_ids) == 15
    assert paper_ids <= covered, sorted(paper_ids - covered)


@pytest.mark.parametrize("topic", TOPICS)
def test_machine_layer_is_separate_and_unverified(topic: str) -> None:
    extraction = _load(DATA / "extractions" / f"{topic}.json")
    machine = _load(DATA / "extractions_machine" / f"{topic}.json")
    assert len(machine["evidence"]) == 10
    assert len(extraction["evidence"]) == 5
    human_ids = {e["evidence_id"] for e in extraction["evidence"]}
    machine_ids = {e["evidence_id"] for e in machine["evidence"]}
    assert not human_ids & machine_ids
    for item in machine["evidence"]:
        assert item["extracted_by"] == "machine:abstract-finding"
        assert item["verified"] is False
        assert item["quote"]
    claim_ids = [c["claim_id"] for c in machine["claims"]]
    assert len(claim_ids) == len(set(claim_ids))
