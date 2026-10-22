"""Evaluate ClaimSupport-CN with the product's claim-support judge.

Judge: ``citeguard.support.judge_support`` (DeepSeek API, optional dependency).
Set ``DEEPSEEK_API_KEY`` in the environment for this command; the key is never
written to any file.  Judge responses are cached under
``data/claimsupport_cn/cache/support`` so re-runs are reproducible.

Metrics: macro-F1 / accuracy / 4x4 confusion matrix / per-class P-R-F1.

Outputs (under data/claimsupport_cn/):
    results.json     - metrics + per-item predictions
    predictions.csv  - one row per item

Usage:
    DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/evaluate_support.py
    DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/evaluate_support.py --limit 10 --workers 4
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import citeguard.config as config  # noqa: E402
from citeguard import support as support_mod  # noqa: E402
from citeguard.support import judge_support  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_DIR = ROOT / "data" / "claimsupport_cn"
DEFAULT_DATASET = DATA_DIR / "claimsupport_cn.jsonl"
DEFAULT_OUT = DATA_DIR / "results.json"
DEFAULT_PRED_CSV = DATA_DIR / "predictions.csv"
DEFAULT_CACHE = DATA_DIR / "cache"

LABELS = ["support", "partial", "contradict", "no_evidence"]
FAILURE_PRED = "no_evidence"  # a judge failure cannot confirm evidence: conservative fallback


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def confusion_matrix(true_labels: list[str], pred_labels: list[str]) -> list[list[int]]:
    index = {label: i for i, label in enumerate(LABELS)}
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for true, pred in zip(true_labels, pred_labels):
        matrix[index[true]][index[pred]] += 1
    return matrix


def per_class(matrix: list[list[int]]) -> dict:
    out: dict = {}
    for i, label in enumerate(LABELS):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(LABELS))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(matrix[i]),
            "predicted": sum(matrix[r][i] for r in range(len(LABELS))),
        }
    return out


def macro_f1(matrix: list[list[int]]) -> float:
    scores = [item["f1"] for item in per_class(matrix).values()]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def accuracy(matrix: list[list[int]]) -> float:
    total = sum(sum(row) for row in matrix)
    if not total:
        return 0.0
    return round(sum(matrix[i][i] for i in range(len(LABELS))) / total, 4)


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------

def judge_one(row: dict) -> dict:
    started = time.perf_counter()
    source = row.get("evidence_source") or {}
    verdict: Optional[dict] = None
    error = ""
    for attempt in range(3):
        try:
            verdict = judge_support(
                row["claim"],
                row["evidence"],
                title=source.get("title", ""),
                doi=source.get("doi", ""),
            )
        except Exception as exc:  # pragma: no cover - defensive
            error = f"{type(exc).__name__}: {exc}"
            verdict = None
        if verdict is not None and verdict.get("label") in LABELS:
            break
        error = error or "judge returned no verdict (API key missing or request failed)"
        time.sleep(0.8 * (attempt + 1))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    pred = verdict.get("label") if verdict else ""
    return {
        "id": row["id"],
        "label": row["label"],
        "pred": pred if pred in LABELS else "",
        "confidence": float(verdict.get("confidence", 0.0)) if verdict else 0.0,
        "reason": (verdict or {}).get("reason", ""),
        "error": error,
        "elapsed_ms": round(elapsed_ms, 1),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    argp = argparse.ArgumentParser(description="Evaluate ClaimSupport-CN with judge_support.")
    argp.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    argp.add_argument("--out", type=Path, default=DEFAULT_OUT)
    argp.add_argument("--predictions", type=Path, default=DEFAULT_PRED_CSV)
    argp.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    argp.add_argument("--limit", type=int, default=0)
    argp.add_argument("--workers", type=int, default=6)
    argp.add_argument("--seed", type=int, default=20261022, help="recorded seed (judging is temperature 0)")
    args = argp.parse_args(argv)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("[fatal] DEEPSEEK_API_KEY is not set; the claim-support judge requires it. "
              "Export it for this command only (never write it to a file).", file=sys.stderr)
        return 2
    config.DEEPSEEK_API_KEY = api_key  # make sure the module sees it even if imported early

    if not args.dataset.exists():
        print(f"[fatal] dataset not found: {args.dataset} "
              f"(run scripts/build_claimsupport.py first)", file=sys.stderr)
        return 2

    args.cache.mkdir(parents=True, exist_ok=True)
    config.CACHE_DIR = args.cache  # judge cache stays inside data/claimsupport_cn/
    print(f"[info] judge cache: {args.cache / 'support'}")

    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("[fatal] dataset is empty", file=sys.stderr)
        return 2
    dataset_sha = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    print(f"[info] dataset={args.dataset.name} n={len(rows)} sha256={dataset_sha[:12]} "
          f"model={config.DEEPSEEK_MODEL} workers={args.workers}")

    results: list[Optional[dict]] = [None] * len(rows)
    done = 0
    lock = threading.Lock()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(judge_one, row): i for i, row in enumerate(rows)}
        for future in as_completed(futures):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                row = rows[i]
                results[i] = {"id": row["id"], "label": row["label"], "pred": "",
                              "confidence": 0.0, "reason": "",
                              "error": f"{type(exc).__name__}: {exc}", "elapsed_ms": 0.0}
            with lock:
                done += 1
                if done % 10 == 0 or done == len(rows):
                    print(f"  judged {done}/{len(rows)} in {time.perf_counter() - started:.1f}s", flush=True)
    final = [r for r in results if r is not None]

    failures = [r for r in final if not r["pred"]]
    for item in failures:  # conservative fallback, reported separately
        item["pred"] = FAILURE_PRED
    true_labels = [item["label"] for item in final]
    pred_labels = [item["pred"] for item in final]
    matrix = confusion_matrix(true_labels, pred_labels)
    pc = per_class(matrix)

    result = {
        "dataset": "ClaimSupport-CN",
        "n": len(final),
        "dataset_sha256": dataset_sha,
        "generated_at": _utc_now(),
        "judge": {
            "module": "citeguard.support.judge_support",
            "model": config.DEEPSEEK_MODEL,
            "endpoint": config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
            "temperature": 0,
            "prompt_sha256": hashlib.sha256(support_mod.PROMPT.encode("utf-8")).hexdigest(),
        },
        "metrics": {"macro_f1": macro_f1(matrix), "accuracy": accuracy(matrix)},
        "per_class": pc,
        "confusion": {"labels": LABELS, "matrix": matrix},
        "failures": len(failures),
        "note": "Labels are fixed by construction (no human double annotation, no kappa); "
                "the judge is a zero-shot DeepSeek 4-way classifier. "
                f"Failures are mapped to '{FAILURE_PRED}' and counted.",
        "predictions": final,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    by_id = {row["id"]: row for row in rows}
    with args.predictions.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "label", "pred", "confidence", "reason", "claim", "evidence", "error"])
        for item in final:
            row = by_id[item["id"]]
            writer.writerow([item["id"], item["label"], item["pred"], item["confidence"],
                             item["reason"], row["claim"], row["evidence"], item["error"]])

    print("\n[confusion] rows=true, cols=pred " + str(LABELS))
    for label, matrix_row in zip(LABELS, matrix):
        print(f"  {label:12s} {matrix_row}")
    print("\n[per-class]")
    for label in LABELS:
        item = pc[label]
        print(f"  {label:12s} P={item['precision']:.3f} R={item['recall']:.3f} "
              f"F1={item['f1']:.3f} support={item['support']} predicted={item['predicted']}")
    print(f"\n[support] macro_f1={result['metrics']['macro_f1']:.4f} "
          f"accuracy={result['metrics']['accuracy']:.4f} failures={len(failures)}")
    print(f"[done] {args.out}")
    print(f"[done] {args.predictions}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
