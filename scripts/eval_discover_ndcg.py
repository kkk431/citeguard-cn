"""Offline-ish ranking check for 选题发现: nDCG@10 with transparent keyword labels.

Relevance is a *proxy*, not human judgement: each query is a set of keyword
groups; a result scores 2 when every group appears in title/abstract, 1 when all
but one group appears, else 0. This is reproducible and cannot be gamed by the
LLM judge, but it rewards keyword recall rather than semantic relevance — report
it as a retrieval sanity check, not as a substitute for human relevance labels.

Usage:
  PYTHONPATH=src python scripts/eval_discover_ndcg.py --out data/experiments/discover_ndcg.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard import discover  # noqa: E402

QUERIES = [
    (
        "人工智能 教育",
        [["人工智能", "artificial intelligence", "machine learning", "ai"],
         ["教育", "教学", "education", "learning", "student"]],
    ),
    (
        "社交媒体 青少年 心理健康",
        [["社交媒体", "social media"],
         ["青少年", "adolescen", "youth", "adolescent"],
         ["心理健康", "mental health", "depress", "well-being"]],
    ),
    (
        "碳中和 政策",
        [["碳中和", "carbon neutral", "carbon emission", "emission"],
         ["政策", "policy", "governance", "regulation"]],
    ),
    (
        "农村 电商",
        [["农村", "rural", "village"],
         ["电商", "e-commerce", "ecommerce", "online shopping"]],
    ),
    (
        "睡眠 认知",
        [["睡眠", "sleep"],
         ["认知", "cognitive", "memory", "attention"]],
    ),
    (
        "大语言模型 医疗",
        [["大语言模型", "large language model", "llm", "generative"],
         ["医疗", "医学", "clinical", "medical", "healthcare"]],
    ),
    (
        "城市 绿地 健康",
        [["绿地", "green space", "greenspace", "park"],
         ["健康", "health", "well-being", "wellbeing"]],
    ),
    (
        "数字经济 就业",
        [["数字经济", "digital economy", "digitalization", "digitalisation"],
         ["就业", "employment", "labor", "labour", "job"]],
    ),
]


def _haystack(item: dict) -> str:
    return ((item.get("title") or "") + " " + (item.get("abstract") or "")).lower()


def _relevance(item: dict, groups: list[list[str]]) -> int:
    text = _haystack(item)
    hits = sum(1 for group in groups if any(token.lower() in text for token in group))
    if hits == len(groups):
        return 2
    if hits >= len(groups) - 1 and hits > 0:
        return 1
    return 0


def _ndcg(rels: list[int], k: int = 10) -> float:
    def dcg(values: list[int]) -> float:
        return sum((2 ** rel - 1) / math.log2(idx + 2) for idx, rel in enumerate(values))

    got = dcg(rels[:k])
    ideal = dcg(sorted(rels, reverse=True)[:k])
    return round(got / ideal, 4) if ideal else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/experiments/discover_ndcg.json")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    rows = []
    for query, groups in QUERIES:
        for mode in ("auto", "off"):
            result = discover.search_papers(query, limit=args.limit, expand=mode)
            rels = [_relevance(item, groups) for item in result.get("results") or []]
            rows.append(
                {
                    "query": query,
                    "expand": mode,
                    "n": len(rels),
                    "relevant_2": rels.count(2),
                    "relevant_1": rels.count(1),
                    "ndcg@10": _ndcg(rels),
                    "titles": [
                        {"title": (item.get("title") or "")[:90], "rel": rel}
                        for item, rel in zip(result.get("results") or [], rels)
                    ],
                }
            )

    def mean(mode: str, key: str) -> float:
        vals = [row[key] for row in rows if row["expand"] == mode]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    payload = {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "method": "keyword-group proxy (2 = all groups, 1 = all-but-one group)",
        "queries": len(QUERIES),
        "summary": {
            mode: {
                "ndcg@10": mean(mode, "ndcg@10"),
                "relevant_2_per_query": mean(mode, "relevant_2"),
            }
            for mode in ("auto", "off")
        },
        "rows": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
