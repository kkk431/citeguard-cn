import csv
import json

import pytest

from citeguard.audit_score import (
    AuditError,
    compare_predictions,
    load_human_sheet,
    load_key,
    score,
)

LABELS = ["support", "partial", "contradict", "no_evidence"]


def write_sheet(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["item_id", "claim", "evidence", "source_title",
                         "human_label", "confidence_1_5", "note"])
        for row in rows:
            writer.writerow(row)


def write_key(path, labels):
    path.write_text(json.dumps({"labels": {
        item: {"label": label, "set": "test"} for item, label in labels.items()
    }}, ensure_ascii=False), encoding="utf-8")


def test_perfect_sheet_scores_one(tmp_path):
    labels = {f"HS{i:03d}": LABELS[i % 4] for i in range(1, 9)}
    sheet = tmp_path / "s.csv"
    key = tmp_path / "k.json"
    write_sheet(sheet, [[item, "claim", "evidence", "title", label, 5, ""]
                        for item, label in labels.items()])
    write_key(key, labels)
    result = score(load_human_sheet(sheet), load_key(key))
    assert result["n_scored"] == 8
    assert result["accuracy"] == 1.0
    assert result["kappa"] == 1.0
    assert result["macro_f1"] == 1.0


def test_mixed_sheet_reports_confusion_and_kappa(tmp_path):
    gold = {f"HS{i:03d}": LABELS[(i - 1) % 4] for i in range(1, 9)}
    human = dict(gold)
    human["HS001"] = "partial"   # wrong
    human["HS002"] = "contradict"  # wrong
    sheet = tmp_path / "s.csv"
    key = tmp_path / "k.json"
    write_sheet(sheet, [[item, "c", "e", "t", human[item], 4, ""] for item in gold])
    write_key(key, gold)
    result = score(load_human_sheet(sheet), load_key(key))
    assert result["accuracy"] == 0.75
    assert 0.0 < result["kappa"] < 1.0
    assert result["confusion"]["matrix"][0][0] == 1  # HS001 gold support, human partial
    assert result["per_label"]["support"]["recall"] == 0.5


def test_empty_or_bad_sheet_is_rejected(tmp_path):
    sheet = tmp_path / "s.csv"
    key = tmp_path / "k.json"
    write_sheet(sheet, [["HS001", "c", "e", "t", "", "", ""]])
    write_key(key, {"HS001": "support"})
    with pytest.raises(AuditError, match="no filled"):
        score(load_human_sheet(sheet), load_key(key))

    write_sheet(sheet, [["HS001", "c", "e", "t", "maybe", "", ""]])
    with pytest.raises(AuditError, match="unknown label"):
        load_human_sheet(sheet)


def test_low_coverage_needs_explicit_partial(tmp_path):
    gold = {f"HS{i:03d}": LABELS[i % 4] for i in range(1, 11)}
    sheet = tmp_path / "s.csv"
    key = tmp_path / "k.json"
    write_sheet(sheet, [["HS001", "c", "e", "t", "support", 5, ""]])
    write_key(key, gold)
    human = load_human_sheet(sheet)
    with pytest.raises(AuditError, match="allow-partial"):
        score(human, load_key(key))
    result = score(human, load_key(key), allow_partial=True)
    assert result["partial"] is True
    assert result["n_scored"] == 1
    assert result["coverage"] == 0.1


def test_predictions_compare_agreement_and_accuracy():
    gold = {"HS001": "support", "HS002": "contradict", "HS003": "partial"}
    human = {
        "HS001": {"label": "support"},
        "HS002": {"label": "partial"},
        "HS003": {"label": "partial"},
    }
    preds = {"HS001": "support", "HS002": "partial", "HS003": "support"}
    result = compare_predictions(human, gold, preds)
    assert result["n"] == 3
    assert result["human_vs_system_agreement"] == 0.6667
    assert result["human_accuracy_vs_gold"] == 0.6667
    assert result["system_accuracy_vs_gold"] == 0.3333
