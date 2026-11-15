"""The CiteMap evidence gate must stay reproducible and honest.

These are small assertions on the committed experiment outputs, not a
replacement for re-running the judge.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    return json.loads((ROOT / "data" / "experiments" / name).read_text(encoding="utf-8"))


def test_gate_reports_no_full_claim_support() -> None:
    data = load("citemap_gate_v3.json")
    summary = data["summary"]
    assert summary["evidence_cells"] == 31
    assert summary["human_correct"] == 8
    assert summary["kept"] == 0
    assert summary["dropped_human_correct"] == 8
    assert data["cells"] and all("verdict" in cell for cell in data["cells"])


def test_loose_gate_precision_and_recall() -> None:
    summary = load("citemap_gate_v2.json")["summary"]
    assert summary["kept"] == 11
    assert summary["kept_correct"] == 7
    assert summary["precision_kept"] == 0.6364
    assert summary["recall_kept"] == 0.875
