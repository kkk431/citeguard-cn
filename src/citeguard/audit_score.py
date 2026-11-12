"""Score a filled ClaimSupport-CN blind-audit sheet against its answer key.

The annotator only sees ``item_id`` and the claim/evidence text.  The gold
labels live in a separate key file (see ``scripts/build_audit_sheet.py``), so
scoring cannot silently "fix" the sheet.  This module is deliberately strict:
an empty sheet, unknown labels, duplicate ids or a low fill rate raise an
error instead of producing a meaningless number.

The labels are the four ClaimSupport-CN classes.  Gold labels in this project
come from construction rules, not from a second human annotator; the audit is
the first human check, and the report says so.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

LABELS = ("support", "partial", "contradict", "no_evidence")
REQUIRED_COLUMNS = ("item_id", "human_label")


class AuditError(ValueError):
    """Raised when the sheet or key cannot be scored honestly."""


def _normalise(label: str) -> str:
    return (label or "").strip().lower().replace("-", "_").replace(" ", "_")


def load_human_sheet(path: str | Path) -> dict[str, dict]:
    """Read a filled sheet; blanks are kept out, malformed labels raise."""
    path = Path(path)
    if not path.exists():
        raise AuditError(f"sheet not found: {path}")
    rows: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise AuditError(f"sheet is missing columns: {', '.join(missing)}")
        for line_no, row in enumerate(reader, start=2):
            item = (row.get("item_id") or "").strip()
            label = _normalise(row.get("human_label") or "")
            if not item:
                continue
            if item in rows:
                raise AuditError(f"duplicate item_id {item} on line {line_no}")
            if not label:
                continue
            if label not in LABELS:
                raise AuditError(
                    f"line {line_no}: unknown label {label!r}; expected {', '.join(LABELS)}"
                )
            conf_raw = (row.get("confidence_1_5") or "").strip()
            try:
                confidence = int(conf_raw) if conf_raw else None
            except ValueError:
                confidence = None
            if confidence is not None and not 1 <= confidence <= 5:
                raise AuditError(f"line {line_no}: confidence must be 1-5, got {conf_raw!r}")
            rows[item] = {
                "label": label,
                "confidence": confidence,
                "note": (row.get("note") or "").strip(),
                "line": line_no,
            }
    if not rows:
        raise AuditError("sheet has no filled human_label values")
    return rows


def load_key(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        raise AuditError(f"key not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    labels = raw.get("labels") if isinstance(raw, dict) else None
    if not isinstance(labels, dict) or not labels:
        raise AuditError("key has no 'labels' mapping")
    gold: dict[str, str] = {}
    for item, value in labels.items():
        label = _normalise(value.get("label") if isinstance(value, dict) else str(value))
        if label not in LABELS:
            raise AuditError(f"key item {item}: unknown gold label {label!r}")
        gold[str(item)] = label
    return gold


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    """Unweighted Cohen's kappa for two label sequences."""
    if not pairs:
        return 0.0
    n = len(pairs)
    observed = sum(1 for human, gold in pairs if human == gold) / n
    human_counts = {label: 0 for label in LABELS}
    gold_counts = {label: 0 for label in LABELS}
    for human, gold in pairs:
        human_counts[human] += 1
        gold_counts[gold] += 1
    expected = sum(human_counts[l] * gold_counts[l] for l in LABELS) / (n * n)
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _per_class(pairs: list[tuple[str, str]]) -> tuple[dict, list[list[int]]]:
    index = {label: i for i, label in enumerate(LABELS)}
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for human, gold in pairs:
        matrix[index[gold]][index[human]] += 1
    per: dict[str, dict] = {}
    for label in LABELS:
        i = index[label]
        tp = matrix[i][i]
        support_gold = sum(matrix[i])
        predicted = sum(row[i] for row in matrix)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support_gold if support_gold else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per[label] = {
            "support": support_gold,
            "predicted": predicted,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return per, matrix


def score(
    human: dict[str, dict],
    gold: dict[str, str],
    *,
    allow_partial: bool = False,
    min_coverage: float = 0.8,
) -> dict:
    """Score a filled sheet; partial coverage must be explicit."""
    if not gold:
        raise AuditError("gold key is empty")
    overlap = [item for item in gold if item in human]
    if not overlap:
        raise AuditError("no item_id in the sheet matches the answer key")
    coverage = len(overlap) / len(gold)
    if coverage < min_coverage and not allow_partial:
        raise AuditError(
            f"only {len(overlap)}/{len(gold)} key items are labeled "
            f"({coverage:.0%}); pass --allow-partial to score this anyway"
        )
    pairs = [(human[item]["label"], gold[item]) for item in overlap]
    correct = sum(1 for h, g in pairs if h == g)
    per, matrix = _per_class(pairs)
    macro_f1 = sum(v["f1"] for v in per.values()) / len(LABELS)
    confidences = [human[item]["confidence"] for item in overlap if human[item]["confidence"]]
    confidence_summary = None
    if confidences:
        confidence_summary = {
            "n": len(confidences),
            "mean": round(sum(confidences) / len(confidences), 2),
            "mean_correct": round(
                sum(human[item]["confidence"] for item in overlap
                    if human[item]["confidence"] and human[item]["label"] == gold[item])
                / max(1, sum(1 for item in overlap
                             if human[item]["confidence"] and human[item]["label"] == gold[item])),
                2,
            ),
        }
    return {
        "n_key": len(gold),
        "n_labeled": len(human),
        "n_scored": len(overlap),
        "coverage": round(coverage, 4),
        "missing": sorted(set(gold) - set(human)),
        "unknown_ids": sorted(set(human) - set(gold)),
        "accuracy": round(correct / len(pairs), 4),
        "macro_f1": round(macro_f1, 4),
        "kappa": round(cohen_kappa(pairs), 4),
        "per_label": per,
        "confusion": {"labels": list(LABELS), "matrix": matrix},
        "confidence": confidence_summary,
        "partial": coverage < 1.0,
    }


def compare_predictions(
    human: dict[str, dict],
    gold: dict[str, str],
    predictions: dict[str, str],
) -> dict:
    """Compare an automatic system with the human labels on the same items."""
    overlap = [item for item in gold if item in human and item in predictions]
    if not overlap:
        raise AuditError("no item has both a human label and a prediction")
    agree = sum(1 for item in overlap if human[item]["label"] == predictions[item])
    system_ok = sum(1 for item in overlap if predictions[item] == gold[item])
    human_ok = sum(1 for item in overlap if human[item]["label"] == gold[item])
    return {
        "n": len(overlap),
        "human_vs_system_agreement": round(agree / len(overlap), 4),
        "human_accuracy_vs_gold": round(human_ok / len(overlap), 4),
        "system_accuracy_vs_gold": round(system_ok / len(overlap), 4),
    }


def load_predictions(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        raise AuditError(f"predictions not found: {path}")
    out: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "item_id" not in reader.fieldnames:
            raise AuditError("predictions need item_id and label columns")
        label_col = "label" if "label" in reader.fieldnames else "human_label"
        for row in reader:
            item = (row.get("item_id") or "").strip()
            label = _normalise(row.get(label_col) or "")
            if item and label:
                if label not in LABELS:
                    raise AuditError(f"prediction for {item}: unknown label {label!r}")
                out[item] = label
    if not out:
        raise AuditError("predictions file has no labels")
    return out
