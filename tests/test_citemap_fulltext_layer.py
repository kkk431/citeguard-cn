"""The full-text evidence layer must stay machine-only and traceable."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "data" / "evidence_map" / "extractions_fulltext"


def test_fulltext_layer_is_machine_only_and_quoted() -> None:
    total = 0
    ids = set()
    for topic in ("ai_education", "medical_imaging"):
        data = json.loads((LAYER / f"{topic}.json").read_text(encoding="utf-8"))
        for item in data["evidence"]:
            total += 1
            ids.add(item["evidence_id"])
            assert item["extracted_by"] == "fulltext:atomic-v2"
            assert item["verified"] is False
            assert item["fulltext_verdict"] in {"full", "partial"}
            assert item["quote"].strip()
            assert item["locator"]
            assert item["paper_id"]
            assert item["atomic_id"]
    assert total == 24
    assert len(ids) == total
    ai = json.loads((LAYER / "ai_education.json").read_text(encoding="utf-8"))
    med = json.loads((LAYER / "medical_imaging.json").read_text(encoding="utf-8"))
    assert len(ai["evidence"]) == 13
    assert len(med["evidence"]) == 11
