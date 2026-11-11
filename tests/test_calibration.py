"""置信度校准（Phase 1）。"""

import pytest

from citeguard import calibration as cal


def test_single_bucket_accuracy_and_ece():
    assert cal.bucket_stats([(0.9, True)] * 10)[0].accuracy == 1.0
    assert cal.expected_calibration_error([(0.9, True)] * 10) == pytest.approx(0.1)


def test_bucket_boundaries_and_last_bucket():
    rows = [(0.5, True), (0.7, False), (1.0, True)]
    ranges = [b.to_dict()["range"] for b in cal.bucket_stats(rows)]
    assert ranges == ["[0.50,0.60)", "[0.70,0.80)", "[0.90,1.00)"]
    assert cal.bucket_stats(rows)[-1].n == 1  # 1.0 归入最后一桶


def test_abstain_curve_coverage():
    pairs = [(0.95, True)] * 5 + [(0.55, False)] * 5
    curve = cal.abstain_curve(pairs, thresholds=(0.5, 0.9))
    assert curve[0]["coverage"] == 1.0
    assert curve[1]["coverage"] == 0.5
    assert curve[1]["accuracy"] == 1.0


def test_summarize_shape():
    s = cal.summarize([(0.8, True), (0.6, False)])
    assert s["n"] == 2
    assert s["accuracy"] == 0.5
    assert "ece" in s and "buckets" in s and "abstain" in s


def test_empty():
    assert cal.summarize([]) == {"n": 0}
