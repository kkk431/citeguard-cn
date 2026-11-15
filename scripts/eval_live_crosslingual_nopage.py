"""Cross-lingual Live retrieval without page context.

The original ``claims.jsonl`` bundle was built for a page-context experiment:
each Chinese sentence is paired with an unrelated public page, so page-reference
candidates cannot contain the cited source.  This script removes the page
context and measures the keyword-search path instead: Chinese claim in, English
source DOI out (hit@1 / hit@3 over the existing 30 claims).

It runs the same claims twice: once with the product's Chinese-query translation
enabled, and once with it disabled, so the incremental effect (or lack of one)
is explicit.  This is a retrieval diagnostic, not a stance benchmark.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_live  # noqa: E402
from citeguard import live_check, support  # noqa: E402


def _run(claims: list[dict], *, translated: bool, mode: str, k: int) -> dict:
    original = support.translate_query
    if not translated:
        support.translate_query = lambda text, timeout=8: ""  # type: ignore[assignment]
    records = []
    try:
        for claim in claims:
            started = time.perf_counter()
            try:
                result = live_check.check_claim(
                    str(claim["sentence"]), page_url="", page_title="", mode=mode
                )
                error = None
            except Exception as exc:  # noqa: BLE001 - report per item
                result = {}
                error = f"{type(exc).__name__}: {exc}"
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            candidates = result.get("candidates") or []
            rank = eval_live.first_hit_rank(
                str(claim.get("source_title") or ""),
                str(claim.get("source_doi") or ""),
                candidates,
            )
            records.append(
                {
                    "id": claim.get("id"),
                    "label": result.get("label"),
                    "n_candidates": len(candidates),
                    "hit@1": rank == 1,
                    "hit@3": bool(rank and rank <= k),
                    "first_hit_rank": rank,
                    "latency_ms": elapsed,
                    "error": error,
                }
            )
    finally:
        support.translate_query = original  # type: ignore[assignment]
    n = len(records)
    hit1 = sum(1 for r in records if r["hit@1"])
    hit3 = sum(1 for r in records if r["hit@3"])
    latencies = [r["latency_ms"] for r in records if r["error"] is None]
    return {
        "translated": translated,
        "n": n,
        "hit@1": round(hit1 / n, 4) if n else None,
        "hit@3": round(hit3 / n, 4) if n else None,
        "p50_ms": eval_live.percentile(latencies, 0.50),
        "p95_ms": eval_live.percentile(latencies, 0.95),
        "errors": sum(1 for r in records if r["error"]),
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claims", default=str(ROOT / "data/live_eval/claims.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "data/live_eval/live_eval_crosslingual_nopage.json"))
    parser.add_argument("--mode", default="fast", choices=["fast", "full"])
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(argv)

    claims = eval_live.load_claims(Path(args.claims))[: args.limit]
    result = {
        "generated_at": eval_live._now(),
        "dataset": "claims.jsonl (30 Chinese sentences, no page context)",
        "k": args.k,
        "mode": args.mode,
        "note": "Machine translation is enabled/disabled; this is retrieval only, not stance accuracy.",
        "with_translation": _run(claims, translated=True, mode=args.mode, k=args.k),
        "without_translation": _run(claims, translated=False, mode=args.mode, k=args.k),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for key in ("with_translation", "without_translation"):
        part = result[key]
        print(
            f"{key}: hit@1={part['hit@1']} hit@3={part['hit@3']} "
            f"P50={part['p50_ms']} ms errors={part['errors']}"
        )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
