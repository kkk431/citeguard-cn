from citeguard.citemap_gate import HIGH, REVIEW, evaluate, gate, summarize


def test_gate_threshold_is_inclusive():
    assert gate(0.9) == HIGH
    assert gate(0.899) == REVIEW
    assert gate(None) == REVIEW


def test_summarize_counts_high_and_review():
    out = summarize([{"confidence": 0.95}, {"confidence": 0.4}, {"confidence": 0.9}])
    assert out["total"] == 3
    assert out["high_confidence"] == 2
    assert out["needs_review"] == 1
    assert out["high_ratio"] == 0.6667


def test_evaluate_reports_precision_recall_f1():
    rows = [
        {"confidence": 0.95, "majority": "correct"},
        {"confidence": 0.92, "majority": "issue"},
        {"confidence": 0.4, "majority": "correct"},
        {"confidence": 0.2, "majority": "issue"},
    ]
    m = evaluate(rows, threshold=0.9)
    assert m.shown == 2
    assert m.correct == 1
    assert m.precision == 0.5
    assert m.recall == 0.5
    assert m.f1 == 0.5
