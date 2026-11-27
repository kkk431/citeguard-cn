import pytest

from citeguard.atomic_alignment import align_claim, align_subclaim, rank_sentences, split_sentences


def test_split_sentences_handles_chinese_and_english():
    text = "第一句。第二句！Third sentence. Fourth"
    parts = split_sentences(text)
    assert "第一句。" in parts[0]
    assert any("Third" in p for p in parts)


def test_rank_sentences_returns_candidates_but_not_support():
    text = "无关内容。本文提出注意力机制，在翻译任务上提升明显。"
    ranked = rank_sentences("注意力机制提升翻译", text)
    assert ranked
    assert "注意力机制" in ranked[0][2]


def test_without_judge_lexical_overlap_is_insufficient():
    out = align_subclaim("注意力机制提升翻译", "本文提出注意力机制，在翻译任务上提升明显。")
    assert out.label == "insufficient"
    assert out.evidence == ""
    assert "不能把字面重合当作支持" in out.reason


def test_judge_must_ground_quote_in_the_candidate_sentence():
    def bad_judge(claim, evidence):
        return {"label": "support", "confidence": 0.9, "quote": "这句话不在候选句里"}

    out = align_subclaim("注意力机制提升翻译", "本文提出注意力机制，在翻译任务上提升明显。", judge=bad_judge)
    assert out.label == "insufficient"
    assert out.confidence == 0.0


def test_judge_support_is_aggregated_for_compound_claim():
    evidence = "本文提出注意力机制。实验在翻译任务上提升明显。"

    def judge(claim, sent):
        return {"label": "support", "confidence": 0.9, "quote": sent, "reason": "直接陈述"}

    out = align_claim("本文提出注意力机制，并在翻译任务上提升明显。", evidence, judge=judge)
    assert out.label == "support"
    assert out.coverage == 1.0
    assert out.checked == len(out.subclaims)


def test_numeric_conflict_overrides_judge_support():
    def judge(claim, sent):
        return {"label": "support", "confidence": 0.95, "quote": sent}

    out = align_subclaim("准确率从 90% 提升到 80%", "准确率从 90% 下降到 80%。", judge=judge)
    assert out.label == "contradict"


def test_partial_when_one_subclaim_has_no_candidate():
    evidence = "本文只讨论注意力机制。"

    def judge(claim, sent):
        return {"label": "support", "confidence": 0.9, "quote": sent}

    out = align_claim("本文提出注意力机制。实验在翻译任务上提升明显。", evidence, judge=judge)
    assert out.label in {"partial", "insufficient"}
    assert out.coverage < 1.0
