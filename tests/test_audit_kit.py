import csv
import json

import pytest

from citeguard.audit_kit import (
    AuditKitError,
    cohen_kappa,
    fleiss_kappa,
    majority,
    read_key,
    read_sheet,
    score,
)


def _sheet(tmp_path, name, rows):
    path = tmp_path / name
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["item_id", "claim", "evidence", "source_title", "human_label", "confidence_1_5", "note"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(item_id, label="", confidence="3"):
    return {
        "item_id": item_id,
        "claim": f"claim {item_id}",
        "evidence": f"evidence {item_id}",
        "source_title": "",
        "human_label": label,
        "confidence_1_5": confidence,
        "note": "",
    }


def test_read_sheet_rejects_unknown_label_and_duplicate(tmp_path):
    bad = _sheet(tmp_path, "bad.csv", [_row("A1", "yes")])
    with pytest.raises(AuditKitError, match="invalid human_label"):
        read_sheet(bad)

    dup = _sheet(tmp_path, "dup.csv", [_row("A1", "support"), _row("A1", "partial")])
    with pytest.raises(AuditKitError, match="duplicate item_id"):
        read_sheet(dup)


def test_majority_and_cohen_kappa():
    assert majority(["support", "support", "partial"]) == ("support", 2)
    tied, votes = majority(["support", "partial", "contradict"])
    assert tied is None and votes == 1

    assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0
    assert cohen_kappa(["a", "a"], ["b", "b"]) == 0.0


def test_fleiss_kappa_perfect_and_known_example():
    assert fleiss_kappa([["support", "support", "support"], ["partial", "partial", "partial"]]) == 1.0
    # Textbook-style small example: agreement beyond chance but not perfect.
    value = fleiss_kappa(
        [
            ["support", "support", "partial"],
            ["support", "partial", "partial"],
            ["contradict", "contradict", "contradict"],
        ]
    )
    assert 0.0 < value < 1.0


def test_score_majority_tie_and_optional_key():
    sheets = {
        "A": {
            "1": {**_row("1", "support"), "claim": "c1", "evidence": "e1"},
            "2": {**_row("2", "support")},
            "3": {**_row("3", "partial")},
        },
        "B": {
            "1": {**_row("1", "support")},
            "2": {**_row("2", "contradict")},
            "3": {**_row("3", "no_evidence")},
        },
        "C": {
            "1": {**_row("1", "partial")},
            "2": {**_row("2", "contradict")},
            "3": {**_row("3", "support")},
        },
    }
    result = score(sheets, key={"1": "support", "2": "support"}, min_coverage=0.9)
    by_id = {row["item_id"]: row for row in result["items"]}
    assert by_id["1"]["final_label"] == "support" and by_id["1"]["votes"] == 2
    assert by_id["2"]["final_label"] == "contradict" and by_id["2"]["votes"] == 2
    assert by_id["3"]["final_label"] == "" and by_id["3"]["needs_adjudication"] is True
    assert result["ties"] == 1
    assert result["disagreements"] == 3
    assert result["constructed_key_comparison"]["compared"] == 2


def test_score_rejects_low_coverage():
    sheets = {
        "A": {"1": {**_row("1", "support")}},
        "B": {"1": {**_row("1", "")}},
    }
    with pytest.raises(AuditKitError, match="coverage below"):
        score(sheets, min_coverage=0.9)
