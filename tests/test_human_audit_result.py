"""Regression checks for the finished 100-item human blind audit."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "data" / "experiments" / "human_audit_100.json"


def _result():
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_three_annotators_are_consistent_and_cover_all_items():
    r = _result()
    assert r["n_items"] == 100
    assert r["annotators"] == ["A", "B", "C"]
    assert all(v == 1.0 for v in r["coverage"].values())
    assert r["fleiss_kappa"] > 0.95
    assert all(v > 0.95 for v in r["pairwise_cohen_kappa"].values())
    assert r["ties"] == 0
    assert len(r["disagreements"]) == 2


def test_product_agrees_with_human_majority_and_keeps_the_single_error():
    p = _result()["product"]
    assert p["mapped"] == 100
    assert p["accuracy"] == 0.99
    assert p["macro_f1"] > 0.98
    assert p["cohen_kappa"] > 0.98
    assert p["accuracy_wilson95"][0] < p["accuracy"] < p["accuracy_wilson95"][1]
    assert p["confusion"] == [[41, 0, 0, 0], [0, 26, 0, 0], [0, 1, 16, 0], [0, 0, 0, 16]]
    assert [m["item_id"] for m in p["mismatches"]] == ["HS032"]


def test_result_is_documented_and_uses_existing_predictions():
    r = _result()
    assert "release300" in r["product"]["predictions_source"]
    doc = (ROOT / "docs" / "human_audit_result.md").read_text(encoding="utf-8")
    assert "0.981" in doc
    assert "99/100" in doc
    assert "HS032" in doc
    chart = ROOT / "docs" / "evidence" / "shots" / "final" / "charts" / "15-human-audit.png"
    assert chart.exists() and chart.stat().st_size > 20_000
