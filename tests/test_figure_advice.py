from citeguard.figure_advice import advise, annotate_items


def test_contradicted_advice_is_high():
    out = advise("contradicted")
    assert out and out["level"] == "high"
    assert "不一致" in out["text"]


def test_insufficient_advice_mentions_unit():
    out = advise("insufficient")
    assert out and out["level"] == "medium"
    assert "单位" in out["text"]


def test_supported_has_no_advice():
    assert advise("supported") is None


def test_annotate_items_skips_supported():
    items = [{"verdict": "supported", "claim": "a"}, {"verdict": "contradicted", "claim": "b"}]
    out = annotate_items(items)
    assert out[0]["advice"] is None
    assert out[1]["advice"]["level"] == "high"
