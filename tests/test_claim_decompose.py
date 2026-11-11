"""多结论拆解测试。"""

from citeguard.claim_decompose import analyze_claim, decompose


def test_splits_contrast_into_two_parts():
    parts = decompose("A 组准确率 92%，比 B 组高 3 个百分点，但推理慢 2 倍。")
    assert len(parts) == 2
    assert parts[0].kind == "comparison"
    assert {n["value"] for n in parts[0].numbers} == {"92", "3"}
    assert parts[1].kind == "numeric"


def test_single_sentence_returns_one_statement():
    parts = decompose("该方法在三个数据集上均有效。")
    assert len(parts) == 1
    assert parts[0].kind == "statement"


def test_causal_kind():
    parts = decompose("由于采样偏差，结果被高估。")
    assert parts[0].kind == "causal"


def test_empty_claim():
    assert decompose("") == []
    assert analyze_claim("")["count"] == 0


def test_analyze_reports_note_only_for_multi_part():
    one = analyze_claim("准确率为 92%。")
    assert one["count"] == 1 and one["note"] == ""
    two = analyze_claim("准确率 92%，但速度慢 2 倍。")
    assert two["count"] == 2
    assert "不是独立的人工判定" in two["note"]
