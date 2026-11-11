"""低置信标注测试。"""

from citeguard.support import is_low_confidence


def test_low_confidence_flag():
    assert is_low_confidence({"label": "support", "confidence": 0.80}) is True
    assert is_low_confidence({"label": "partial", "confidence": 0.89}) is True
    assert is_low_confidence({"label": "support", "confidence": 0.95}) is False


def test_not_checked_never_flagged():
    assert is_low_confidence({"label": "not_checked", "confidence": 0.0}) is False
    assert is_low_confidence({"label": "no_evidence", "confidence": 0.1}) is False
    assert is_low_confidence(None) is False


def test_threshold_is_strict():
    item = {"label": "support", "confidence": 0.9}
    assert is_low_confidence(item, threshold=0.95) is True
    assert is_low_confidence(item, threshold=0.9) is False
