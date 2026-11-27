"""Cost-aware support-judge cascade.

Policy, not a new model: a cheap judge answers first; only ambiguous cases are
escalated to the stronger/expensive judge.  The threshold is deliberately
configurable because a local 1.7B adapter is not the same cost profile as a
hosted API.

This module is pure: callers pass two callables, which makes the policy
testable without a GPU or an API key.  The callables must return a mapping with
``label``, ``confidence``, ``reason`` and optionally ``evidence``/``audit``.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable

LABELS = ("support", "partial", "contradict", "no_evidence")
_NUM = re.compile(r"-?\d+(?:\.\d+)?\s*(?:%|％|倍|万|亿|篇|条|年|月|天|小时|分钟|秒|GB|MB|ms|s)?")


@dataclass(frozen=True)
class CascadeConfig:
    confidence_threshold: float = 0.80
    max_primary_evidence_chars: int = 1200
    escalate_on_numeric: bool = True
    escalate_on_low_confidence: bool = True


def _conf(result: dict | None) -> float:
    try:
        return max(0.0, min(1.0, float((result or {}).get("confidence") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def numeric_conflict(claim: str, evidence: str) -> bool:
    """True when the claim and evidence contain obviously different numbers.

    This is a routing hint only; it never changes the verdict by itself.  A
    richer numeric checker (unit/order-aware) lives in ``numeric_check``.
    """
    def values(text: str) -> set[str]:
        return {m.group(0).replace(" ", "").replace("％", "%") for m in _NUM.finditer(text or "")}

    c, e = values(claim), values(evidence)
    if not c or not e:
        return False
    # A number in the claim absent from the evidence is worth a second opinion;
    # identical sets are not a conflict even if the wording differs.
    return bool(c - e)


def route_reason(claim: str, evidence: str, primary: dict | None, config: CascadeConfig) -> str:
    if not primary:
        return "primary_unavailable"
    if _conf(primary) < config.confidence_threshold and config.escalate_on_low_confidence:
        return "low_confidence"
    if len(evidence or "") > config.max_primary_evidence_chars:
        return "long_evidence"
    if config.escalate_on_numeric and numeric_conflict(claim, evidence):
        return "numeric_conflict"
    if str(primary.get("label") or "") not in LABELS:
        return "invalid_label"
    return ""


def run_cascade(
    claim: str,
    evidence: str,
    primary: Callable[[str, str], dict | None],
    escalate: Callable[[str, str], dict | None],
    config: CascadeConfig | None = None,
) -> dict[str, Any]:
    """Run primary, escalate only when the policy says so.

    If escalation fails, the primary verdict is returned with
    ``escalation_failed`` so callers never turn a transport failure into a
    fabricated "better" answer.
    """
    cfg = config or CascadeConfig()
    started = time.perf_counter()
    primary_result = primary(claim, evidence)
    reason = route_reason(claim, evidence, primary_result, cfg)
    if not reason:
        return {
            "result": primary_result,
            "stage": "primary",
            "escalated": False,
            "route_reason": "",
            "primary": primary_result,
            "escalation": None,
            "escalation_failed": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    if primary_result is None and not cfg.escalate_on_low_confidence:
        reason = "primary_unavailable"
    escalated = escalate(claim, evidence)
    final = escalated or primary_result
    return {
        "result": final,
        "stage": "escalated" if escalated else "primary_fallback",
        "escalated": bool(escalated),
        "route_reason": reason,
        "primary": primary_result,
        "escalation": escalated,
        "escalation_failed": escalated is None,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }
