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
    assert verdicts["full"] == 7
    assert verdicts["partial"] == 13
    assert verdicts["none"] == 193
    assert verdicts["error"] == 0
    assert verdicts["full_rate"] == 0.0329
    assert verdicts["any_support_rate"] == 0.0939
    assert "21/30" in data["boundary"]


def test_audited_positive_cross_check() -> None:
    data = load()
    audits = data["audited_positive_with_fulltext"]
    assert len(audits) == 7
    full_hits = [item for item in audits if item["fulltext_hit"]]
    support_hits = [item for item in audits if item["support_hit"]]
    assert len(full_hits) == 5
    assert len(support_hits) == 6
    assert all(item["quote"] for item in full_hits)
    assert data["audited_positive_n"] == 7
    assert data["audited_positive_full_recall"] == 0.7143
    assert data["audited_positive_support_recall"] == 0.8571
    # All seven full verdicts map back to one of the seven audited-positive
    # cells (some cells have multiple atomic claims). This is a tiny,
    # descriptive cross-check, not a population precision estimate.
    assert data["full_verdict_precision_on_audited"] == 1.0


def test_chart_exists() -> None:
    assert (ROOT / "docs" / "evidence" / "shots" / "final" / "charts" / "16-fulltext-atomic.png").is_file()
