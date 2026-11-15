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
    assert data["pairs"] == 87
    verdicts = data["verdicts"]
    assert verdicts["full"] == 2
    assert verdicts["partial"] == 5
    assert verdicts["none"] == 80
    assert verdicts["error"] == 0
    assert verdicts["full_rate"] == 0.023
    assert "8/30" in data["boundary"]


def test_audited_positive_cross_check() -> None:
    data = load()
    audits = data["audited_positive_with_fulltext"]
    assert len(audits) == 2
    assert all(item["audited_positive"] and item["fulltext_hit"] for item in audits)
    assert data["audited_positive_with_fulltext_recall"] == 1.0
    # The denominator is tiny; the precision field is a sanity check, not a
    # population estimate.
    assert data["full_verdict_precision_on_audited"] == 1.0
    assert all(item["quote"] for item in audits)


def test_chart_exists() -> None:
    assert (ROOT / "docs" / "evidence" / "shots" / "final" / "charts" / "16-fulltext-atomic.png").is_file()
