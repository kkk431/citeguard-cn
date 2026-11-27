"""Confidence gate for CiteMap machine evidence.

The gate is intentionally simple and auditable: machine evidence above a
confidence threshold may be shown as "high-confidence candidate", while the
rest stays in the review queue.  It does not turn the machine layer into a
human-accepted evidence layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

DEFAULT_THRESHOLD = 0.9
HIGH = "high_confidence"
REVIEW = "needs_review"


def gate(confidence: float | None, threshold: float = DEFAULT_THRESHOLD) -> str:
    try:
        value = float(confidence or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return HIGH if value >= threshold else REVIEW


def apply(items: Iterable[Mapping], threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    out = []
    for item in items:
        row = dict(item)
        decision = gate(row.get("confidence"), threshold)
        row["gate"] = decision
        row["gate_threshold"] = threshold
        out.append(row)
    return out


def summarize(items: Iterable[Mapping], threshold: float = DEFAULT_THRESHOLD) -> dict:
    high = review = 0
    for item in items:
        if gate(item.get("confidence"), threshold) == HIGH:
            high += 1
        else:
            review += 1
    total = high + review
    return {
        "threshold": threshold,
        "total": total,
        "high_confidence": high,
        "needs_review": review,
        "high_ratio": round(high / total, 4) if total else 0.0,
    }


@dataclass
class GateMetrics:
    threshold: float
    shown: int
    correct: int
    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict:
        return {
            "threshold": self.threshold,
            "shown": self.shown,
            "correct": self.correct,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def evaluate(rows: Iterable[Mapping], *, threshold: float = DEFAULT_THRESHOLD) -> GateMetrics:
    """Evaluate against human ``majority`` labels (``correct`` = positive)."""
    rows = list(rows)
    positives = sum(1 for r in rows if r.get("majority") == "correct")
    shown = [r for r in rows if gate(r.get("confidence"), threshold) == HIGH]
    correct = sum(1 for r in shown if r.get("majority") == "correct")
    precision = correct / len(shown) if shown else 0.0
    recall = correct / positives if positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return GateMetrics(threshold=threshold, shown=len(shown), correct=correct, precision=precision, recall=recall, f1=f1)
