"""Tests for the optional claim-support judge and its key-free degradation."""
from __future__ import annotations

import json

import pytest

from citeguard import config
from citeguard import support as sp
from citeguard.reference_parser import InTextCitation, Reference, parse_intext_citations

from helpers import FakeResponse, deepseek_support_response, install_fake_post


def _ref(index: int, authors: list[str], year: int) -> Reference:
    return Reference(raw=f"[{index}] x", index=index, authors=authors, year=year)


def test_judge_without_api_key_returns_none():
    assert sp.judge_support("引用句", "摘要内容") is None


def test_judge_without_abstract_returns_not_checked():
    out = sp.judge_support("引用句", "")
    assert out is not None and out["label"] == "not_checked"


def test_judge_without_claim_returns_none():
    assert sp.judge_support("", "摘要") is None


def test_extract_claim_strips_numeric_citation():
    body = "第一句话[1]。第二句话[2]。"
    claim = sp.extract_claim(body, body.index("[1]"))
    assert "第一句话" in claim
    assert "[1]" not in claim


def test_build_claims_maps_numeric_citations():
    body = "研究发现[1]。另见[2]。"
    intext = [
        InTextCitation(raw="[1]", kind="numeric", numbers=[1], position=body.index("[1]")),
        InTextCitation(raw="[2]", kind="numeric", numbers=[2], position=body.index("[2]")),
    ]
    refs = [_ref(1, ["张三"], 2020), _ref(2, ["李四"], 2021)]
    claims = sp.build_claims(body, intext, refs)
    assert claims[1].startswith("研究发现")
    assert claims[2].startswith("另见")


def test_build_claims_matches_author_year_citation():
    body = "（张三, 2020）表明该方法有效。"
    intext = parse_intext_citations(body)
    refs = [_ref(1, ["张三"], 2020)]
    claims = sp.build_claims(body, intext, refs)
    assert 1 in claims


def test_judge_with_key_and_mocked_api(monkeypatch, isolated_cache):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    calls = install_fake_post(monkeypatch, sp, lambda url, body: deepseek_support_response("support"))

    out = sp.judge_support("引用句", "摘要内容", title="题名", doi="10.1/x")

    assert out is not None
    assert out["label"] == "support"
    assert out["confidence"] == pytest.approx(0.9)
    # stage 1 verdict + stage 2 coverage audit (only for "support" verdicts)
    assert len(calls) == 2
    assert calls[0]["url"].endswith("/chat/completions")
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test"
    assert calls[0]["json"]["temperature"] == 0


def _support_then_audit(audit_payload: dict):
    seen = {"n": 0}

    def handler(url, body):
        seen["n"] += 1
        if seen["n"] == 1:
            return deepseek_support_response("support")
        content = json.dumps(audit_payload, ensure_ascii=False)
        return FakeResponse(200, {"choices": [{"message": {"content": content}}]})

    return handler


def test_coverage_audit_downgrades_incomplete_support(monkeypatch, isolated_cache):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    install_fake_post(
        monkeypatch,
        sp,
        _support_then_audit({"fully_covered": False, "missing": ["量级/显著性"]}),
    )

    out = sp.judge_support("干预显著改善症状", "干预组症状有所下降")

    assert out is not None
    assert out["label"] == "partial"
    assert out["audit"]["fully_covered"] is False
    assert "覆盖审计" in out["reason"]


def test_coverage_audit_keeps_fully_covered_support(monkeypatch, isolated_cache):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    install_fake_post(
        monkeypatch,
        sp,
        _support_then_audit({"fully_covered": True, "missing": []}),
    )

    out = sp.judge_support("引用句", "摘要")

    assert out is not None
    assert out["label"] == "support"
    assert out["audit"]["fully_covered"] is True


def test_coverage_audit_can_be_disabled(monkeypatch, isolated_cache):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(config, "SUPPORT_AUDIT", False)
    calls = install_fake_post(monkeypatch, sp, lambda url, body: deepseek_support_response("support"))

    out = sp.judge_support("引用句", "摘要")

    assert out is not None and out["label"] == "support"
    assert len(calls) == 1


def test_judge_normalizes_unknown_label(monkeypatch, isolated_cache):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    install_fake_post(monkeypatch, sp, lambda url, body: deepseek_support_response("made_up"))

    out = sp.judge_support("引用句", "摘要内容")

    assert out is not None and out["label"] == "no_evidence"


def test_judge_returns_none_on_api_error(monkeypatch, isolated_cache):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    install_fake_post(monkeypatch, sp, lambda url, body: FakeResponse(401, {"error": "unauthorized"}))

    assert sp.judge_support("引用句", "摘要内容") is None


def test_judge_uses_cache_on_second_call(monkeypatch, isolated_cache):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    calls = install_fake_post(monkeypatch, sp, lambda url, body: deepseek_support_response("partial"))

    first = sp.judge_support("引用句", "摘要内容")
    second = sp.judge_support("引用句", "摘要内容")

    assert first == second
    assert len(calls) == 1
    # Cache is namespaced by prompt version so prompt changes never reuse old verdicts.
    assert list((isolated_cache / "support").glob(f"v{sp.PROMPT_VERSION}/*.json"))


def test_summarize_support_counts():
    counts = sp.summarize_support([None, {"label": "support"}, {"label": "contradict"}])
    assert counts["not_checked"] == 1
    assert counts["support"] == 1
    assert counts["contradict"] == 1
    assert counts["partial"] == 0
