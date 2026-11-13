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


# ------------------------- 公开页集（句子与页面真实对应） -------------------------


PUBLIC_TITLES = [
    "Zebra Migration Patterns in Semi-Arid Grasslands",
    "Lattice Renormalization for Quantum Chromodynamics",
    "Medieval Icelandic Saga Composition and Orality",
    "Coral Bleaching Recovery in Shallow Reefs",
    "Sparse Matrix Solvers on Heterogeneous Clusters",
    "Volcanic Ash Dispersion Forecasting Models",
    "Tonal Phonology of Southern Min Dialects",
    "Protein Folding Kinetics under Crowding",
    "Urban Heat Islands and Canopy Cover",
    "Byzantine Coinage and Trade Networks",
    "Glacial Lake Outburst Flood Risk Mapping",
    "Reinforcement Learning for Traffic Signal Control",
    "Soil Carbon Sequestration in Paddy Fields",
    "Gravitational Lensing by Galaxy Clusters",
    "Bacterial Quorum Sensing and Biofilms",
    "Textile Dyeing in Early Modern Europe",
    "Seismic Retrofitting of Masonry Buildings",
    "Speech Prosody in Second Language Learners",
    "Photosynthetic Efficiency under Drought Stress",
    "Distributed Consensus with Byzantine Faults",
    "Ocean Acidification and Pteropod Shells",
    "Graph Neural Networks for Molecule Property Prediction",
    "Agricultural Irrigation Scheduling with Remote Sensing",
    "Musical Improvisation and Working Memory",
    "Permafrost Thaw and Methane Emissions",
    "Handwritten Text Recognition for Historical Archives",
    "Wind Turbine Blade Fatigue Analysis",
    "Sleep Architecture in Shift Workers",
    "Cache Coherence in Many-Core Processors",
    "Wetland Restoration and Avian Biodiversity",
]


def make_public_page(index=0, **overrides):
    page = {
        "id": f"arxiv-public-{index}",
        "url": f"https://arxiv.org/html/2611.0000{index}",
        "title": f"Public Benchmark Paper {index}",
        "fetched_at": "2026-11-14T02:15:00+08:00",
        "license": "CC BY 4.0",
        "source": "arXiv HTML (LaTeXML)",
        "references": 40 + index,
    }
    page.update(overrides)
    return page


def make_public_claim(page, index, **overrides):
    claim = {
        "id": f"pub-{index:03d}",
        "sentence": (
            f"Prior work on this topic reports a clear improvement over strong baselines "
            f"across all evaluated settings [{index}], which motivates our design."
        ),
        "source_title": PUBLIC_TITLES[index - 1],
        "source_doi": f"10.1234/public.{index}",
        "page_url": page["url"],
        "page_title": page["title"],
        "reference_index": index,
    }
    claim.update(overrides)
    return claim


def make_public_dataset():
    pages = [make_public_page(i) for i in range(5)]
    claims = []
    n = 1
    for page in pages:
        for _ in range(6):
            claims.append(make_public_claim(page, n))
            n += 1
    return pages, claims


def test_dataset_profile_detects_public_and_crosslingual():
    pages, claims = make_public_dataset()
    assert eval_live.dataset_profile(claims) == "public"
    assert eval_live.dataset_profile([make_claim()]) == "crosslingual"
    assert eval_live.dataset_profile([]) == "unknown"


def test_public_dataset_validates_with_page_url_lookup():
    pages, claims = make_public_dataset()
    assert eval_live.validate(pages, claims) == []
    candidate = {"title": PUBLIC_TITLES[6], "doi": "10.1234/public.7", "url": ""}
    result = eval_live.run(claims, pages, fake_checker([candidate]))
    assert result["n"] == 30
    assert result["dataset"] == "public"
    assert result["hit@3"] == pytest.approx(1 / 30, abs=1e-4)
    assert result["records"][6]["first_hit_rank"] == 1
    assert result["records"][6]["reference_index"] == 7


def test_public_dataset_rejects_short_sentence_and_missing_marker():
    pages, claims = make_public_dataset()
    claims[0] = make_public_claim(pages[0], 1, sentence="Too short [1].")
    claims[1] = make_public_claim(pages[0], 2, sentence="This sentence is long enough but it has no explicit citation marker at all.")
    errors = eval_live.validate(pages, claims)
    assert any("长度" in error for error in errors)
    assert any("引用标记" in error for error in errors)


def test_public_dataset_rejects_mismatched_reference_index_and_page_title():
    pages, claims = make_public_dataset()
    claims[2] = make_public_claim(pages[0], 3, reference_index=999)
    claims[3] = make_public_claim(pages[1], 4, page_title="Wrong Title")
    errors = eval_live.validate(pages, claims)
    assert any("reference_index 999" in error for error in errors)
    assert any("page_title" in error for error in errors)


def test_public_dataset_rejects_wrong_per_page_count_and_cjk():
    pages, claims = make_public_dataset()
    claims[0] = make_public_claim(pages[0], 1, sentence="中文句子不应出现在公开页英文字段里，但仍带有引用标记 [1]。")
    errors = eval_live.validate(pages, claims[:-1])
    assert any("应有 6 条" in error for error in errors)
    assert any("英文" in error for error in errors)


def test_validate_accepts_public_repo_dataset():
    pages = eval_live.load_pages(ROOT / "data" / "live_eval" / "pages_public.json")
    claims = eval_live.load_claims(ROOT / "data" / "live_eval" / "claims_public.jsonl")
    assert eval_live.validate(pages, claims) == []
    assert eval_live.dataset_profile(claims) == "public"
