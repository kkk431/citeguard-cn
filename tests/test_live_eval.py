"""CiteGuard Live 评测脚本的单元测试（不依赖网络与 live_check 实现）。

覆盖：hit@3 排序命中、未命中、空候选、检查器异常、真实数据集校验、
字段/来源缺失的拒绝。check_claim 用假检查器注入，避免联网。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import eval_live  # noqa: E402


def make_page(**overrides):
    page = {
        "id": "arxiv-test",
        "url": "https://arxiv.org/abs/1706.03762",
        "title": "Attention Is All You Need",
        "fetched_at": "2026-11-14T01:50:33+08:00",
        "license": "arXiv 非独占分发许可",
    }
    page.update(overrides)
    return page


def make_claim(**overrides):
    claim = {
        "id": "live-001",
        "sentence": "该研究通过随机实验发现语言拟人化线索能显著提升用户遵从[2]。",
        "source_title": "AI-Based Chatbots in Customer Service and Their Effects on User Compliance",
        "source_doi": "10.1007/s12525-020-00414-7",
        "page_id": "arxiv-test",
    }
    claim.update(overrides)
    return claim


def make_result(label="support", candidates=None, confidence=0.9):
    return {"label": label, "confidence": confidence, "reason": "", "evidence": None, "candidates": candidates or []}


def fake_checker(candidates=None, label="support"):
    def _check(claim, page_url="", page_title=""):
        return make_result(label=label, candidates=candidates or [])

    return _check


def test_hit_at_3_counts_rank_two_and_not_hit_at_1():
    candidates = [
        {"title": "Unrelated paper about chatbots", "doi": "10.9999/unrelated", "url": ""},
        {"title": "AI-Based Chatbots in Customer Service and Their Effects on User Compliance", "doi": "10.1007/s12525-020-00414-7", "url": ""},
        {"title": "Another paper", "doi": "10.9999/other", "url": ""},
    ]
    result = eval_live.run([make_claim()], [make_page()], fake_checker(candidates))
    assert result["n"] == 1
    assert result["hit@1"] == 0.0
    assert result["hit@3"] == 1.0
    assert result["records"][0]["first_hit_rank"] == 2


def test_wrong_candidates_are_miss():
    candidates = [
        {"title": "人工智能研究综述", "doi": "10.63887/jerp.2025.1.8.51", "url": ""},
        {"title": "另一篇不相关论文", "doi": "10.1234/other", "url": ""},
    ]
    result = eval_live.run([make_claim()], [make_page()], fake_checker(candidates, label="no_evidence"))
    assert result["hit@3"] == 0.0
    assert result["label_counts"]["no_evidence"] == 1
    assert result["records"][0]["first_hit_rank"] is None


def test_empty_candidates_are_counted_but_not_a_failure():
    result = eval_live.run([make_claim()], [make_page()], fake_checker([], label="no_evidence"))
    assert result["hit@3"] == 0.0
    assert result["n_no_candidates"] == 1
    assert result["n_failures"] == 0


def test_checker_exception_is_recorded_as_failure():
    def boom(claim, page_url="", page_title=""):
        raise RuntimeError("network down")

    result = eval_live.run([make_claim()], [make_page()], boom)
    assert result["n_failures"] == 1
    assert "network down" in result["failures"][0]["error"]
    assert result["hit@3"] == 0.0


def test_validate_accepts_repo_dataset():
    pages = eval_live.load_pages(ROOT / "data" / "live_eval" / "pages.json")
    claims = eval_live.load_claims(ROOT / "data" / "live_eval" / "claims.jsonl")
    assert eval_live.validate(pages, claims) == []


def test_validate_rejects_missing_page_and_extra_field():
    pages = [make_page() for _ in range(5)]
    claims = [make_claim() for _ in range(30)]
    claims[0] = make_claim(page_id="missing-page")
    claims[1] = dict(make_claim(id="live-002"), extra="x")
    errors = eval_live.validate(pages, claims)
    assert any("page_id" in error for error in errors)
    assert any("字段" in error for error in errors)


def test_validate_rejects_empty_dataset():
    errors = eval_live.validate([], [])
    assert any("pages 应为" in error for error in errors)
    assert any("claims 应为" in error for error in errors)
