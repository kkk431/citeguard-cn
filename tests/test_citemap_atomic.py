"""Atomic CiteMap layer: decomposition shape and extracted evidence contract."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"


def test_atomic_claims_keep_unique_ids_and_parents():
    atomic = json.loads((DATA / "claims_atomic.json").read_text(encoding="utf-8"))
    manual_ids = set()
    for topic in ("ai_education", "medical_imaging"):
        manual = json.loads((DATA / "extractions" / f"{topic}.json").read_text(encoding="utf-8"))
        manual_ids.update(claim["claim_id"] for claim in manual["claims"])
    seen = set()
    total = 0
    for topic in atomic["topics"].values():
        for claim in topic["claims"]:
            assert claim["atomic_id"] not in seen
            seen.add(claim["atomic_id"])
            assert claim["parent_claim_id"] in manual_ids
            assert len(claim["text"]) >= 8
            total += 1
    assert total == 21


def test_atomic_evidence_is_machine_only_and_quotes_are_nonempty():
    total = 0
    for topic in ("ai_education", "medical_imaging"):
        payload = json.loads(
            (DATA / "extractions_atomic" / f"{topic}.json").read_text(encoding="utf-8")
        )
        claims = json.loads((DATA / "claims_atomic.json").read_text(encoding="utf-8"))
        ids = {
            item["atomic_id"]
            for item in claims["topics"][topic]["claims"]
        }
        for item in payload["evidence"]:
            assert item["verified"] is False
            assert item["atomic_id"] in ids
            assert item["paper_id"]
            assert item["quote"].strip()
            assert item["parent_claim_id"] == item["atomic_id"].rsplit("-a", 1)[0]
            total += 1
    assert total == 9
