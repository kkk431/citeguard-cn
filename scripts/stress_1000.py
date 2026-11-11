"""1000-reference stress test: parse, full offline analysis, cold/warm, 2-way concurrency.

Run:  CITEGUARD_OFFLINE=1 PYTHONPATH=src python scripts/stress_1000.py --refs 1000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("CITEGUARD_OFFLINE", "1")

from citeguard import config  # noqa: E402
from citeguard.pdf_extract import split_references  # noqa: E402
from citeguard.pipeline import analyze_text  # noqa: E402
from citeguard.reference_parser import parse_reference_list  # noqa: E402

config.OFFLINE = True

FAMILIES = [
    "张三, 李四. 深度学习在医学影像分析中的应用综述[J]. 中国图象图形学报, 2023, 28(6): 1234-1245.",
    "WANG L, CHEN H, ZHAO Y. A survey of retrieval-augmented generation[J]. Journal of Systems, 2024, 11(2): 100-118.",
    "刘洋. 面向中文文献的引文核验方法研究[D]. 武汉: 华中科技大学, 2022.",
    "SMITH J, BROWN K. Evaluating citation claims at scale[C]//Proceedings of ACL. 2023: 1-12.",
    "国家标准化管理委员会. 信息与文献 参考文献著录规则: GB/T 7714-2025[S]. 北京: 中国标准出版社, 2025.",
    "李雷, 韩梅梅. 大语言模型辅助学术写作的风险与治理[J]. 图书情报知识, 2024, 41(3): 55-66.",
    "OpenAlex. OpenAlex API documentation[EB/OL]. https://docs.openalex.org, 2024-05-01.",
    "陈晨, 王芳, 赵磊. 基于开源模型的中文引用支持度判定[J]. 数据分析与知识发现, 2025, 9(1): 77-89.",
]


def build_text(n: int) -> str:
    refs = [f"[{i}] " + FAMILIES[(i - 1) % len(FAMILIES)] for i in range(1, n + 1)]
    body = []
    for i in range(1, n + 1, 10):
        keys = ", ".join(str(k) for k in range(i, min(i + 10, n + 1)))
        body.append(f"已有研究讨论了该问题[{keys}]，但证据并不总是支持文中的结论。")
    return (
        "# 一千条引用的压力测试\n\n## 摘要\n本文用于压测解析、格式校验与报告生成链路。\n\n"
        + "\n\n".join(body)
        + "\n\n## 参考文献\n\n"
        + "\n".join(refs)
        + "\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", type=int, default=1000)
    ap.add_argument("--out", default="data/experiments/stress_1000.json")
    args = ap.parse_args()

    text = build_text(args.refs)
    started = time.perf_counter()
    blocks = split_references(text)
    parsed = parse_reference_list(text)
    parse_s = time.perf_counter() - started

    tracemalloc.start()
    t0 = time.perf_counter()
    report = analyze_text(
        text, source_name=f"stress_{args.refs}.txt", support_max=0, online=False, max_refs=args.refs
    )
    cold_s = time.perf_counter() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    t0 = time.perf_counter()
    analyze_text(text, source_name=f"stress_{args.refs}.txt", support_max=0, online=False, max_refs=args.refs)
    warm_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda _: analyze_text(
                    text, source_name=f"stress_{args.refs}.txt", support_max=0, online=False, max_refs=args.refs
                ),
                range(2),
            )
        )
    concurrent_s = time.perf_counter() - t0

    payload = {
        "refs_requested": args.refs,
        "chars": len(text),
        "parsed_references": len(parsed),
        "blocks": len(blocks),
        "parse_s": round(parse_s, 3),
        "cold_full_s": round(cold_s, 3),
        "warm_full_s": round(warm_s, 3),
        "two_concurrent_s": round(concurrent_s, 3),
        "peak_mb": round(peak / 1024 / 1024, 1),
        "report_refs": len(report.get("references") or []),
        "status_counts": dict(
            Counter(
                (r.get("verify") or {}).get("status") or "Unknown"
                for r in (report.get("references") or [])
            )
        ),
        "offline": True,
        "python": sys.version.split()[0],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
