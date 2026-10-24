"""Measure the multi-paper comparison on real corpus PDFs.

Runs the same code path as the web app (``citeguard.compare``) against text-based
PDFs in ``data/real_corpus`` and writes the evidence JSON consumed by the docs.
The judge endpoint is the usual OpenAI-compatible one: set ``DEEPSEEK_API_KEY``
(or ``CITEGUARD_JUDGE_BASE_URL`` / ``_MODEL`` / ``_API_KEY`` for a local model).

Example (from the citeguard/ directory)::

    PYTHONPATH=src python scripts/eval_compare_real.py
    PYTHONPATH=src python scripts/eval_compare_real.py --papers hanspub_152678.pdf hanspub_152699.pdf
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from citeguard import compare, config
from citeguard.pdf_extract import extract_text

DEFAULT_PAPERS = [
    "hanspub_152678.pdf",
    "hanspub_152699.pdf",
    "hanspub_152703.pdf",
    "hanspub_152704.pdf",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", nargs="*", default=None, help="PDF file names")
    parser.add_argument("--corpus", default=str(config.DATA_DIR / "real_corpus"))
    parser.add_argument("--out", default=str(config.DATA_DIR / "experiments" / "compare_real.json"))
    args = parser.parse_args()

    names = args.papers or DEFAULT_PAPERS
    if not compare.available():
        print("judge endpoint is not configured; set DEEPSEEK_API_KEY or CITEGUARD_JUDGE_*")
        return 2
    pairs: list[tuple[str, str]] = []
    for name in names:
        path = Path(args.corpus) / name
        text = extract_text(path)
        pairs.append((path.stem, text))
        print(f"loaded {name}: {len(text)} chars", flush=True)

    started = time.perf_counter()
    result = compare.compare_texts(
        pairs, on_progress=lambda i, total, name: print(f"[{i}/{total}] {name}", flush=True)
    )
    result["elapsed_s"] = round(time.perf_counter() - started, 1)
    result["source"] = f"data/real_corpus ({len(pairs)} text-based hanspub PDFs)"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for paper in result["papers"] if not paper["error"])
    print(f"\n{ok}/{len(result['papers'])} papers extracted, {result['elapsed_s']}s total")
    for paper in result["papers"]:
        filled = sum(1 for value in paper["fields"].values() if value)
        print(f"- {paper['name']}: fields {filled}/6, error={paper['error'] or 'none'}")
    print(f"evidence -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
