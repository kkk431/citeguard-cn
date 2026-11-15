"""Guard the honest atomic full-text evidence numbers."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data" / "experiments" / "citemap_atomic_fulltext_summary.json"


def load() -> dict:
    return json.loads(SUMMARY.read_text(encoding="utf-8"))


def test_fulltext_evaluation_is_not_overclaimed() -> None:
    data = load()
    assert data["pairs"] == 213
    verdicts = data["verdicts"]
    assert verdicts["full"] == 5
    assert verdicts["partial"] == 8
    assert verdicts["none"] == 200
    assert verdicts["error"] == 0
    assert verdicts["full_rate"] == 0.0235
    assert "21/30" in data["boundary"]


def test_audited_positive_cross_check() -> None:
    data = load()
    audits = data["audited_positive_with_fulltext"]
    assert len(audits) == 7
    hits = [item for item in audits if item["fulltext_hit"]]
    assert len(hits) == 3
    assert all(item["quote"] for item in hits)
    assert data["audited_positive_with_fulltext_recall"] == 0.4286
    # The denominator is tiny; the precision field is a sanity check, not a
    # population estimate. Two of the five full verdicts have no human label.
    assert data["full_verdict_precision_on_audited"] == 0.6


def test_chart_exists() -> None:
    assert (ROOT / "docs" / "evidence" / "shots" / "final" / "charts" / "16-fulltext-atomic.png").is_file()
