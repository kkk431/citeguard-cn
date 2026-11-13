"""Human audit kit helpers: read blind sheets, majority vote, Cohen/Fleiss kappa.

The kit deliberately keeps the constructed answer key separate from the sheets
handed to annotators.  Human majority labels become the adjudicated gold set;
the constructed key is only a reference and must never be called ground truth.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping

LABELS = ("support", "partial", "contradict", "no_evidence")
REQUIRED_COLUMNS = ("item_id", "claim", "evidence", "human_label", "confidence_1_5")


class AuditKitError(ValueError):
    """A sheet or key violates the audit-kit contract."""


def read_sheet(path: str | Path) -> dict[str, dict[str, str]]:
    """Read one annotator sheet and return ``{item_id: row}``.

    An empty ``human_label`` is allowed while the sheet is in progress; scoring
    treats those items as missing and reports coverage.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise AuditKitError(f"{path.name}: missing columns {missing}")
        rows: dict[str, dict[str, str]] = {}
        for line_no, row in enumerate(reader, start=2):
            item_id = (row.get("item_id") or "").strip()
            if not item_id:
                raise AuditKitError(f"{path.name}:{line_no}: empty item_id")
            if item_id in rows:
                raise AuditKitError(f"{path.name}:{line_no}: duplicate item_id {item_id}")
            label = (row.get("human_label") or "").strip()
            if label and label not in LABELS:
                raise AuditKitError(
                    f"{path.name}:{line_no}: invalid human_label {label!r}; "
                    f"expected one of {LABELS}"
                )
            row["human_label"] = label
            rows[item_id] = row
    return rows


def read_key(path: str | Path) -> dict[str, str]:
    """Read the constructed audit key (``{item_id: label}`` or wrapped labels)."""
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    labels = data.get("labels", data) if isinstance(data, dict) else data
    if not isinstance(labels, dict):
        raise AuditKitError(f"{Path(path).name}: expected an object of item_id -> label")
    out: dict[str, str] = {}
    for item_id, value in labels.items():
        label = value.get("label") if isinstance(value, dict) else value
        if label not in LABELS:
            raise AuditKitError(f"{Path(path).name}: invalid key label for {item_id}: {label!r}")
        out[str(item_id)] = str(label)
    return out


def majority(labels: Iterable[str]) -> tuple[str | None, int]:
    """Return the majority label and its vote count; ``None`` when tied."""
    values = [label for label in labels if label]
    if not values:
        return None, 0
    counts = Counter(values)
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None, ranked[0][1]
    return ranked[0][0], ranked[0][1]


def cohen_kappa(a: Iterable[str], b: Iterable[str]) -> float:
    """Unweighted Cohen's kappa for two raters over the same items."""
    left = list(a)
    right = list(b)
    if len(left) != len(right):
        raise AuditKitError("cohen_kappa needs two equally long label sequences")
    n = len(left)
    if n == 0:
        raise AuditKitError("cohen_kappa needs at least one item")
    observed = sum(1 for x, y in zip(left, right) if x == y) / n
    pa = Counter(left)
    pb = Counter(right)
    expected = sum((pa[label] / n) * (pb[label] / n) for label in set(pa) | set(pb))
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def fleiss_kappa(rows: Iterable[Iterable[str]]) -> float:
    """Fleiss' kappa for ``N`` items and a fixed number of raters per item."""
    matrix = [list(row) for row in rows]
    if not matrix:
        raise AuditKitError("fleiss_kappa needs at least one item")
    n = len(matrix[0])
    if n < 2:
        raise AuditKitError("fleiss_kappa needs at least two raters")
    if any(len(row) != n for row in matrix):
        raise AuditKitError("fleiss_kappa needs the same number of raters for every item")
    big_n = len(matrix)
    p_items = []
    for row in matrix:
        counts = Counter(row)
        p_items.append((sum(c * c for c in counts.values()) - n) / (n * (n - 1)))
    p_bar = sum(p_items) / big_n
    totals = Counter()
    for row in matrix:
        totals.update(row)
    p_e = sum((totals[label] / (big_n * n)) ** 2 for label in LABELS)
    if p_e >= 1.0:
        return 1.0 if p_bar >= 1.0 else 0.0
    return (p_bar - p_e) / (1.0 - p_e)


def pair_kappas(sheets: Mapping[str, Mapping[str, Mapping[str, str]]]) -> dict[str, float]:
    """Pairwise Cohen's kappa over the item ids shared by both sheets."""
    names = sorted(sheets)
    out: dict[str, float] = {}
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            common = sorted(set(sheets[left]) & set(sheets[right]))
            if not common:
                continue
            a = [sheets[left][item]["human_label"] for item in common]
            b = [sheets[right][item]["human_label"] for item in common]
            out[f"{left}|{right}"] = round(cohen_kappa(a, b), 6)
    return out


def score(
    sheets: Mapping[str, Mapping[str, Mapping[str, str]]],
    *,
    key: Mapping[str, str] | None = None,
    min_coverage: float = 0.9,
) -> dict:
    """Score human sheets.

    Returns a JSON-ready dict with coverage, pairwise/Fleiss kappa, human gold
    rows (majority), disagreements, and optional agreement with the constructed
    key.  Items with a tie are marked ``needs_adjudication=True`` and get no
    final label.
    """
    names = sorted(sheets)
    if not names:
        raise AuditKitError("no annotator sheets")
    all_ids: set[str] = set()
    for rows in sheets.values():
        all_ids |= set(rows)
    if not all_ids:
        raise AuditKitError("annotator sheets contain no items")

    coverage: dict[str, float] = {}
    for name in names:
        labeled = sum(1 for row in sheets[name].values() if row.get("human_label"))
        coverage[name] = round(labeled / len(all_ids), 4)
    low = [name for name, value in coverage.items() if value < min_coverage]
    if low:
        raise AuditKitError(
            f"coverage below {min_coverage:.0%}: " + ", ".join(f"{n}={coverage[n]:.1%}" for n in low)
        )

    complete_ids = [
        item
        for item in sorted(all_ids)
        if all(item in sheets[name] and sheets[name][item].get("human_label") for name in names)
    ]
    if not complete_ids:
        raise AuditKitError("no item has a label from every annotator")

    gold = []
    disagreements = []
    for item in complete_ids:
        labels = [sheets[name][item]["human_label"] for name in names]
        label, votes = majority(labels)
        confidences = []
        for name in names:
            raw = (sheets[name][item].get("confidence_1_5") or "").strip()
            if raw:
                try:
                    confidences.append(float(raw))
                except ValueError:
                    pass
        row = {
            "item_id": item,
            "claim": sheets[names[0]][item].get("claim", ""),
            "evidence": sheets[names[0]][item].get("evidence", ""),
            "final_label": label or "",
            "votes": votes,
            "n_labels": len(labels),
            "needs_adjudication": label is None,
            "mean_confidence": round(sum(confidences) / len(confidences), 2) if confidences else "",
            "labels": " | ".join(f"{name}={value}" for name, value in zip(names, labels)),
        }
        gold.append(row)
        if len(set(labels)) > 1:
            disagreements.append(
                {
                    **row,
                    "notes": " | ".join(
                        f"{name}: {(sheets[name][item].get('note') or '').strip()}"
                        for name in names
                    ),
                }
            )

    n = len(complete_ids)
    matrix = [[sheets[name][item]["human_label"] for name in names] for item in complete_ids]
    if len(names) >= 2:
        fleiss = round(fleiss_kappa(matrix), 6)
        pairs = pair_kappas({name: {item: sheets[name][item] for item in complete_ids} for name in names})
    else:
        fleiss = None
        pairs = {}

    key_comparison = None
    if key:
        compared = [row for row in gold if row["final_label"] and row["item_id"] in key]
        if compared:
            correct = sum(1 for row in compared if row["final_label"] == key[row["item_id"]])
            key_comparison = {
                "compared": len(compared),
                "agreement": round(correct / len(compared), 4),
                "note": "constructed key is a reference, not human ground truth",
            }

    return {
        "annotators": names,
        "items_total": len(all_ids),
        "items_complete": n,
        "coverage": coverage,
        "fleiss_kappa": fleiss,
        "pairwise_cohen_kappa": pairs,
        "mean_pairwise_kappa": round(sum(pairs.values()) / len(pairs), 6) if pairs else None,
        "majority_counts": dict(Counter(row["final_label"] or "tie" for row in gold)),
        "ties": sum(1 for row in gold if row["needs_adjudication"]),
        "disagreements": len(disagreements),
        "constructed_key_comparison": key_comparison,
        "items": gold,
        "disagreement_items": disagreements,
    }
