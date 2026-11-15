"""Unit tests for the generic sentence-level CiteMap verifier."""
from __future__ import annotations

from citeguard import citemap_verify


TEXT = (
    "This study finds that generative AI tools are widely accepted by Chinese university "
    "students in a large survey of 373 learners across multiple universities."
)


def test_split_caps_pdf_blobs_and_drops_table_debris() -> None:
    long = "x" * 2000
    table = "0.837 4.68 1.398 “A” “B” 0.891 4.79 1.325 “C” 0.679 4.85 1.393"
    sentences = citemap_verify.split_sentences(f"{TEXT}\n{table}\n{long}")
    assert sentences
    assert all(len(s) <= citemap_verify.MAX_SENTENCE_CHARS for s in sentences)
    assert not any("0.837" in s for s in sentences)


def test_rank_prefers_overlap() -> None:
    sentences = [TEXT, "Unrelated background about quantum chromodynamics and lattice gauge theory."]
    ranked = citemap_verify.rank_sentences("generative AI acceptance among Chinese students", sentences)
    assert ranked[0] == TEXT


def test_verbatim_quote_is_kept(monkeypatch) -> None:
    import citeguard.support as support

    monkeypatch.setattr(support, "translate_query", lambda *_a, **_k: "")
    monkeypatch.setattr(
        support,
        "_chat_json",
        lambda *_a, **_k: {"verdict": "full", "evidence": TEXT, "reason": "direct result"},
    )
    result = citemap_verify.verify_claim_in_text("生成式 AI 在中国高校学生中被广泛接受。", TEXT)
    assert result["verdict"] == "full"
    assert result["evidence"] == TEXT


def test_hallucinated_quote_is_downgraded(monkeypatch) -> None:
    import citeguard.support as support

    monkeypatch.setattr(support, "translate_query", lambda *_a, **_k: "")
    monkeypatch.setattr(
        support,
        "_chat_json",
        lambda *_a, **_k: {"verdict": "full", "evidence": "a quote that is not in the source", "reason": "made up"},
    )
    result = citemap_verify.verify_claim_in_text("生成式 AI 在中国高校学生中被广泛接受。", TEXT)
    assert result["verdict"] == "partial"
    assert result["evidence"] == ""
    assert "未在候选句" in result["reason"]


def test_summary_counts_errors_separately() -> None:
    summary = citemap_verify.summarize(
        [
            {"verdict": "full"},
            {"verdict": "partial"},
            {"verdict": "none"},
            {"verdict": "error"},
        ]
    )
    assert summary == {
        "claims": 4,
        "full": 1,
        "partial": 1,
        "none": 1,
        "error": 1,
        "full_rate": 0.25,
        "any_support_rate": 0.5,
    }
