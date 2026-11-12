"""Five-dimension health profile: weights, availability and fix ordering."""
from __future__ import annotations

from citeguard.health import compute_health


def _report(**overrides):
    base = {
        "stats": {
            "total": 10,
            "Exact": 10,
            "Minor": 0,
            "Unverified": 0,
            "Unknown": 0,
            "Major": 0,
            "avg_compliance": 95.0,
            "support": {"support": 10, "partial": 0, "contradict": 0, "no_evidence": 0, "not_checked": 0},
        },
        "references": [{"index": i, "cited_in": [{"sentence": "x"}], "compliance": {"issues": []}} for i in range(1, 11)],
        "citations": {
            "summary": {"total": 12},
            "coverage": {"refs": 10, "cited": 10, "uncited": [], "ratio": 1.0},
        },
        "citation_consistency": {
            "numeric_style": True,
            "distinct_numbers": 10,
            "missing_numbers": [],
            "uncited_numbers": [],
            "order_inversions": 0,
        },
    }
    base.update(overrides)
    return base


def test_all_dimensions_available_scores_high():
    health = compute_health(_report())
    assert health["confidence"] == 1.0
    assert abs(health["overall"] - 99.25) < 0.1  # 95 compliance pulls the 100s down slightly
    assert health["grade"] == "A"
    assert [d["key"] for d in health["dimensions"]] == [
        "authenticity",
        "support",
        "relevance",
        "coverage",
        "compliance",
    ]
    assert health["top_fixes"][0]["title"] == "没有发现需要优先处理的问题"


def test_unavailable_support_is_excluded_not_zero():
    stats = _report()["stats"]
    stats["support"] = {"not_checked": 10}
    health = compute_health(_report(stats=stats))
    assert health["confidence"] == 0.75
    support = [d for d in health["dimensions"] if d["key"] == "support"][0]
    assert support["available"] is False and support["score"] is None
    assert abs(health["overall"] - 99.0) < 0.1  # the remaining dimensions renormalise to 75% weight


def test_major_and_missing_numbers_rank_as_high_fixes():
    stats = _report()["stats"]
    stats["Exact"], stats["Major"] = 8, 2
    consistency = _report()["citation_consistency"]
    consistency["missing_numbers"] = [7, 8]
    health = compute_health(_report(stats=stats, citation_consistency=consistency))
    titles = [f["title"] for f in health["top_fixes"]]
    assert any("疑似错配或虚构" in t for t in titles)
    assert any("正文编号" in t for t in titles)
    assert all(f["severity"] == "high" for f in health["top_fixes"][:2])
    assert 85 <= health["overall"] < 95
    assert health["grade"] == "B"


def test_unknown_and_unverified_are_caution_not_fabrication():
    stats = _report()["stats"]
    stats.update({"Exact": 0, "Unverified": 6, "Unknown": 4})
    health = compute_health(_report(stats=stats))
    auth = [d for d in health["dimensions"] if d["key"] == "authenticity"][0]
    assert auth["score"] == 35.0
    assert "不等于文献造假" in auth["note"]
