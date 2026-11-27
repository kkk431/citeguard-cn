from __future__ import annotations

from citeguard.model_cascade import CascadeConfig, numeric_conflict, route_reason, run_cascade


def _r(label="support", confidence=0.9):
    return {"label": label, "confidence": confidence, "reason": "x"}


def test_confident_short_call_does_not_escalate():
    calls = []
    out = run_cascade("a claim", "short evidence", lambda c, e: _r(), lambda c, e: calls.append(1) or _r())
    assert out["stage"] == "primary"
    assert out["escalated"] is False
    assert calls == []


def test_low_confidence_escalates_and_uses_the_stronger_verdict():
    out = run_cascade("claim", "evidence",
                      lambda c, e: _r("partial", 0.55),
                      lambda c, e: _r("contradict", 0.93))
    assert out["stage"] == "escalated"
    assert out["route_reason"] == "low_confidence"
    assert out["result"]["label"] == "contradict"


def test_long_evidence_escalates_even_when_primary_is_confident():
    long_evidence = "word " * 400
    out = run_cascade("claim", long_evidence,
                      lambda c, e: _r("support", 0.99),
                      lambda c, e: _r("partial", 0.8))
    assert out["route_reason"] == "long_evidence"
    assert out["stage"] == "escalated"


def test_numeric_conflict_is_a_routing_hint_only():
    assert numeric_conflict("准确率 72.6%", "准确率 68.1%")
    assert not numeric_conflict("准确率 72.6%", "report says 72.6%")
    out = run_cascade("准确率 72.6%", "准确率 68.1%",
                      lambda c, e: _r("support", 0.95),
                      lambda c, e: _r("contradict", 0.9))
    assert out["route_reason"] == "numeric_conflict"


def test_escalation_failure_returns_primary_without_faking_a_verdict():
    out = run_cascade("claim", "evidence",
                      lambda c, e: _r("partial", 0.5),
                      lambda c, e: None)
    assert out["escalation_failed"] is True
    assert out["stage"] == "primary_fallback"
    assert out["result"]["label"] == "partial"


def test_threshold_is_configurable():
    cfg = CascadeConfig(confidence_threshold=0.95)
    assert route_reason("c", "e", _r(confidence=0.9), cfg) == "low_confidence"
    assert route_reason("c", "e", _r(confidence=0.96), cfg) == ""
