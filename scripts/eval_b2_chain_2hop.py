"""Evaluate the bounded two-hop chain on a small, fixed DOI sample.

This is a smoke/coverage probe, not a representative benchmark: OpenAlex
coverage varies by publisher and the sample is intentionally small.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from citeguard.retraction import check_chain

DOIS = [
    "10.1038/nature14539",
    "10.1080/14653240600855905",
    "10.48550/arXiv.1810.04805",
    "10.48550/arXiv.2205.14135",
    "10.48550/arXiv.2312.00752",
    "10.1145/3292500.3330701",
    "10.1109/CVPR.2016.90",
    "10.18653/v1/P19-1424",
]

OUT = Path("data/experiments/opt_b2_1_chain_2hop_real_2026-11-27.json")


def main() -> int:
    rows = []
    for doi in DOIS:
        started = time.time()
        result = check_chain(doi, max_refs=8, max_hops=2, hop2_limit=2)
        rows.append({
            "doi": doi,
            "status": result.get("status"),
            "sampled": result.get("sampled"),
            "checked": result.get("checked"),
            "coverage": result.get("coverage"),
            "second_sampled": result.get("second_sampled"),
            "second_degree": result.get("second_degree") or [],
            "direct_retracted": result.get("retracted") or [],
            "detail": result.get("detail"),
            "elapsed_s": round(time.time() - started, 2),
        })
        print(doi, rows[-1]["status"], rows[-1]["coverage"], rows[-1]["second_sampled"])
        time.sleep(0.4)

    data = {
        "date": "2026-11-27",
        "method": "check_chain(max_refs=8, max_hops=2, hop2_limit=2)",
        "sample_size": len(rows),
        "rows": rows,
        "note": "Fixed small DOI sample; not a representative benchmark. A clean row is a sample result, not a clean whole chain.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
