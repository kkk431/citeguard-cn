"""B2 result-cache benchmark harness (not collected by pytest).

Run from the repository root::

    $env:PYTHONIOENCODING='utf-8'; $env:PYTHONPATH='src'
    python tests/b2_cache_bench.py --json data/experiments/opt_b2_cache_2026-11-26.json

It measures, on real local corpus PDFs and fully offline (no judge, no network):
1. a cold batch (empty result cache) — every file is parsed + verified;
2. a hot batch (same bytes/options/versions) — reports come from cache;
3. a rerun after one injected transient failure — only that item runs again.

Timings are wall-clock on the developer machine and must not be compared to a
different machine.  The hot batch is *cache reuse*, not a cold-start speedup.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from citeguard import jobs, pipeline  # noqa: E402

WORK = Path(os.environ.get("B2_BENCH_WORK", r"D:\Temp\citeguard_e3\b2_bench"))
OPTIONS = {"support_max": 0, "online": False, "figures": False, "max_refs": 40}
CORPUS = ROOT / "data" / "real_corpus"


def _reset(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pick_files(count: int = 3) -> list[Path]:
    files = sorted(CORPUS.glob("*.pdf"))
    if len(files) < count:
        raise SystemExit(f"need at least {count} PDFs in {CORPUS}, found {len(files)}")
    return files[:count]


def _summary(report: dict) -> dict:
    citations = report.get("citations") or {}
    support = report.get("support") or {}
    return {
        "references": len(report.get("references") or []),
        "citations": len(citations.get("items") or []) if isinstance(citations, dict) else 0,
        "support_counts": (support.get("counts") if isinstance(support, dict) else None),
    }


def run() -> dict:
    work = _reset(WORK)
    cache_dir = _reset(work / "result_cache")
    text_dir = _reset(work / "text_cache")
    batch_dir = work / "batches"
    _reset(batch_dir)
    os.environ["CITEGUARD_RESULT_CACHE_DIR"] = str(cache_dir)
    os.environ["CITEGUARD_TEXT_CACHE_DIR"] = str(text_dir)
    os.environ["CITEGUARD_BATCH_DIR"] = str(batch_dir)

    files = _pick_files(3)
    cache = jobs.ResultCache(cache_dir)
    versions = pipeline.analysis_cache_versions()
    runner = jobs.BatchRunner(cache=cache, root=batch_dir, options=OPTIONS, versions=versions)

    def process(path: str, options: dict) -> dict:
        return pipeline.analyze_file_cached(path, options=options)

    # --- cold -------------------------------------------------------------
    cold_batch = runner.create(files)
    started = time.perf_counter()
    cold_batch = runner.run(cold_batch["id"], process)
    cold_wall = (time.perf_counter() - started) * 1000
    cold_reports = {
        it["name"]: _summary(runner.report(cold_batch["id"], it["id"]) or {}) for it in cold_batch["items"]
    }
    cold_hashes = {
        it["name"]: (runner.report(cold_batch["id"], it["id"]) or {}).get("cache", {}).get("status")
        for it in cold_batch["items"]
    }
    after_cold = cache.stats()

    # --- hot --------------------------------------------------------------
    hot_batch = runner.create(files)
    started = time.perf_counter()
    hot_batch = runner.run(hot_batch["id"], process)
    hot_wall = (time.perf_counter() - started) * 1000
    after_hot = cache.stats()
    same = all(
        _summary(runner.report(hot_batch["id"], it["id"]) or {}) == cold_reports[it["name"]]
        for it in hot_batch["items"]
    )

    # --- retry only failed ------------------------------------------------
    retry_cache = _reset(work / "retry_cache")
    retry_runner = jobs.BatchRunner(
        cache=jobs.ResultCache(retry_cache), root=batch_dir, options=OPTIONS, versions=versions
    )
    attempts: dict[str, int] = {}
    calls: list[str] = []
    target = files[1].name

    def flaky(path: str, options: dict) -> dict:
        calls.append(Path(path).name)
        attempts[Path(path).name] = attempts.get(Path(path).name, 0) + 1
        if Path(path).name == target and attempts[Path(path).name] == 1:
            raise TimeoutError("injected transient timeout (simulates a network hiccup)")
        return pipeline.analyze_file_cached(path, options=options)

    retry_batch = retry_runner.create(files)
    started = time.perf_counter()
    retry_batch = retry_runner.run(retry_batch["id"], flaky)
    first_wall = (time.perf_counter() - started) * 1000
    failed_ids = [it["id"] for it in retry_batch["items"] if it["status"] == "error"]
    calls_before_retry = list(calls)
    started = time.perf_counter()
    retried = retry_runner.retry_failed(retry_batch["id"], flaky)
    retry_wall = (time.perf_counter() - started) * 1000
    retry_calls = calls[len(calls_before_retry) :]

    # --- single-item retry on an explicit row action ----------------------
    single_cache = _reset(work / "single_cache")
    single_runner = jobs.BatchRunner(
        cache=jobs.ResultCache(single_cache), root=batch_dir, options=OPTIONS, versions=versions
    )
    single_calls: list[str] = []
    single_target = files[2].name
    single_attempts: dict[str, int] = {}

    def single_flaky(path: str, options: dict) -> dict:
        name = Path(path).name
        single_calls.append(name)
        single_attempts[name] = single_attempts.get(name, 0) + 1
        if name == single_target and single_attempts[name] == 1:
            raise ConnectionError("injected single-item failure")
        return pipeline.analyze_file_cached(path, options=options)

    single_batch = single_runner.create(files)
    single_batch = single_runner.run(single_batch["id"], single_flaky)
    single_first_statuses = {it["name"]: it["status"] for it in single_batch["items"]}
    before_single = list(single_calls)
    single_batch = single_runner.retry_item(single_batch["id"], "item-03", single_flaky)
    single_retry_calls = single_calls[len(before_single) :]

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "task": "B2 result cache + rerun only failed",
        "machine": sys.platform,
        "offline": True,
        "judge": "disabled (support_max=0, online=False)",
        "dataset": {
            "corpus": "data/real_corpus (local open-access PDFs)",
            "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": jobs.sha256_file(p)} for p in files],
            "options": OPTIONS,
            "versions": versions,
        },
        "cold": {
            "label": "cold: empty result cache and empty text cache",
            "n": len(cold_batch["items"]),
            "wall_ms": round(cold_wall, 1),
            "per_item_ms": {it["name"]: it["elapsed_ms"] for it in cold_batch["items"]},
            "statuses": {it["name"]: it["status"] for it in cold_batch["items"]},
            "sources": {it["name"]: it["source"] for it in cold_batch["items"]},
            "reports": cold_reports,
            "cache_status": cold_hashes,
            "cache": after_cold,
            "stats": cold_batch["stats"],
        },
        "hot": {
            "label": "hot: same bytes/options/versions, result cache warm",
            "n": len(hot_batch["items"]),
            "wall_ms": round(hot_wall, 1),
            "per_item_ms": {it["name"]: it["elapsed_ms"] for it in hot_batch["items"]},
            "sources": {it["name"]: it["source"] for it in hot_batch["items"]},
            "stats": hot_batch["stats"],
            "cache": after_hot,
            "hit_rate_this_run": hot_batch["stats"]["cache_hits"] / max(len(hot_batch["items"]), 1),
            "speedup_vs_cold": round(cold_wall / hot_wall, 2) if hot_wall else None,
            "same_report_summaries": same,
            "note": "cache reuse, NOT a cold-start speedup",
        },
        "retry": {
            "label": "one injected transient failure, then retry_failed()",
            "first_run": {
                "wall_ms": round(first_wall, 1),
                "statuses": {it["name"]: it["status"] for it in retry_batch["items"]},
                "failed_ids": failed_ids,
                "calls": calls_before_retry,
            },
            "retry_run": {
                "wall_ms": round(retry_wall, 1),
                "statuses": {it["name"]: it["status"] for it in retried["items"]},
                "calls": retry_calls,
                "only_failed": len(retry_calls) == 1 and bool(failed_ids),
                "attempts": attempts,
            },
            "final_stats": retried["stats"],
        },
        "single_retry": {
            "label": "one row action retries exactly one item",
            "target": single_target,
            "first_statuses": single_first_statuses,
            "calls_before": before_single,
            "calls_after": single_retry_calls,
            "only_target": single_retry_calls == [single_target],
            "attempts": single_attempts,
            "final_statuses": {it["name"]: it["status"] for it in single_batch["items"]},
        },
        "boundaries": [
            "cold/hot timing is machine-specific and only for this machine (CPU, no GPU)",
            "offline analysis: no online verification and no support judge; parse+rule verdicts only",
            "the retry failure is injected once to test recovery, not a real network incident",
            "hot numbers must not be reported as cold-start performance",
        ],
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=str(ROOT / "data" / "experiments" / "opt_b2_cache_2026-11-26.json"))
    args = parser.parse_args()
    payload = run()
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["cold"], ensure_ascii=False, indent=2))
    print(json.dumps(payload["hot"], ensure_ascii=False, indent=2))
    print(json.dumps(payload["retry"], ensure_ascii=False, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
