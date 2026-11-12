"""Evaluate CiteBench-CN v2 with the product's own reference verifier.

Two tracks, deliberately separated:

1. Metadata problem detection on 453 items (v1 250 + 203 constructed mutations):
   "problem" is any label other than Exact (Minor/Major/author_swap/...). Product
   flags a problem when its status is Minor or Major; Unknown is reported
   separately and counted as a miss (it means "could not verify", not "clean").
2. Special checks: 17 retracted works via the F3 retraction checker; 30
   predatory-looking citations, for which the product has no detector (only a
   venue-mismatch flag), reported as a known gap rather than a score.

Usage:
    PYTHONPATH=src python scripts/eval_citebench_v2.py [--workers 6] [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import citeguard.config as config  # noqa: E402
from citeguard import retraction  # noqa: E402
from evaluate_citebench import verify_one  # noqa: E402

DATA_DIR = ROOT / "data" / "citebench_cn"
DATASET = DATA_DIR / "citebench_cn_v2.jsonl"
CACHE = DATA_DIR / "cache"
RESULTS = DATA_DIR / "v2_results.json"
CSV_PATH = DATA_DIR / "v2_predictions.csv"
SPECIAL = {"retracted", "predatory"}
PROBLEM_LABELS = {
    "Minor", "Major", "author_swap", "year_shift", "venue_swap",
    "doi_swap", "paraphrase", "fabricated",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pct(value: float) -> float:
    return round(value * 100, 2)


def evaluate_metadata(items: list[dict], workers: int) -> tuple[list[dict], dict]:
    predictions = []

    def work(item: dict) -> dict:
        result = verify_one(item["ref_string"], "full")
        status = result["status"]
        pred_problem = status in ("Minor", "Major")
        return {
            "id": item["id"],
            "label": item["label"],
            "expected_problem": item["label"] in PROBLEM_LABELS,
            "pred_problem": pred_problem,
            "status": status,
            "unknown": status == "Unknown",
            "title_sim": result["title_sim"],
            "year_match": result["year_match"],
            "author_match": result["author_match"],
        }

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, item) for item in items]
        for future in as_completed(futures):
            predictions.append(future.result())
    elapsed = time.perf_counter() - started
    predictions.sort(key=lambda r: r["id"])

    tp = sum(1 for r in predictions if r["expected_problem"] and r["pred_problem"])
    fn = sum(1 for r in predictions if r["expected_problem"] and not r["pred_problem"])
    fp = sum(1 for r in predictions if not r["expected_problem"] and r["pred_problem"])
    tn = sum(1 for r in predictions if not r["expected_problem"] and not r["pred_problem"])
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    unknown_count = sum(1 for r in predictions if r["unknown"])
    decided = len(predictions) - unknown_count
    decided_positive = (tp + fn) - unknown_count

    per_class: dict[str, dict] = {}
    for label in sorted({r["label"] for r in predictions}):
        rows = [r for r in predictions if r["label"] == label]
        flagged = sum(1 for r in rows if r["pred_problem"])
        unknown = sum(1 for r in rows if r["unknown"])
        per_class[label] = {
            "n": len(rows),
            "flagged": flagged,
            "exact": sum(1 for r in rows if r["status"] == "Exact"),
            "unknown": unknown,
            "detection_rate": round(flagged / len(rows), 4) if rows else 0.0,
        }

    summary = {
        "n": len(predictions),
        "positive": tp + fn,
        "negative": tn + fp,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round((tp + tn) / len(predictions), 4) if predictions else 0.0,
        "unknown": sum(1 for r in predictions if r["unknown"]),
        "unknown_rate": round(sum(1 for r in predictions if r["unknown"]) / len(predictions), 4) if predictions else 0.0,
        "decided": decided,
        "decision_coverage": round(decided / len(predictions), 4) if predictions else 0.0,
        "recall_decided": round(tp / decided_positive, 4) if decided_positive else 0.0,
        "accuracy_decided": round((tp + tn) / decided, 4) if decided else 0.0,
        "elapsed_s": round(elapsed, 1),
        "per_class": per_class,
    }
    return predictions, summary


def evaluate_special(items: list[dict]) -> dict:
    retracted = [i for i in items if i["label"] == "retracted"]
    predatory = [i for i in items if i["label"] == "predatory"]

    retracted_rows = []
    for item in retracted:
        doi = (item.get("gold") or {}).get("doi") or ""
        result = retraction.check_doi(doi) if doi else {"status": "error", "detail": "no doi"}
        retracted_rows.append({
            "id": item["id"],
            "doi": doi,
            "status": result.get("status"),
            "detected": result.get("status") == "retracted",
        })
    detected = sum(1 for r in retracted_rows if r["detected"])

    # Product has no predatory-journal detector. Venue mismatch may be flagged
    # as a metadata drift, which is NOT the same thing; keep them separate.
    predatory_flagged = []
    for item in predatory:
        result = verify_one(item["ref_string"], "full")
        predatory_flagged.append({
            "id": item["id"],
            "status": result["status"],
            "metadata_flagged": result["status"] in ("Minor", "Major"),
        })

    return {
        "retracted": {
            "n": len(retracted_rows),
            "detected": detected,
            "recall": round(detected / len(retracted_rows), 4) if retracted_rows else None,
            "note": "OpenAlex 中文撤稿记录有限（17 条可用），这是外部真值，不是构造标签。",
        },
        "predatory": {
            "n": len(predatory_flagged),
            "metadata_flagged": sum(1 for r in predatory_flagged if r["metadata_flagged"]),
            "specific_detector": None,
            "note": "产品没有 predatory 期刊检测器；venue 不一致会被当作元数据偏差，不能算作 predatory 识别率。",
        },
        "rows": {"retracted": retracted_rows, "predatory": predatory_flagged},
    }


def main(argv=None) -> int:
    argp = argparse.ArgumentParser()
    argp.add_argument("--workers", type=int, default=6)
    argp.add_argument("--limit", type=int, default=0, help="debug: only first N metadata items")
    args = argp.parse_args(argv)

    CACHE.mkdir(parents=True, exist_ok=True)
    config.CACHE_DIR = CACHE
    items = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    metadata = [i for i in items if i["label"] not in SPECIAL]
    if args.limit:
        metadata = metadata[: args.limit]
    print(f"[info] {len(metadata)} metadata items, cache={CACHE}", flush=True)

    predictions, summary = evaluate_metadata(metadata, args.workers)
    special = evaluate_special(items)
    result = {
        "dataset": "CiteBench-CN v2",
        "evaluated_at": _utc_now(),
        "metadata": summary,
        "special": {k: v for k, v in special.items() if k != "rows"},
        "special_rows": special["rows"],
        "predictions": predictions,
        "definitions": {
            "problem": "label != Exact; product flags when status is Minor/Major",
            "unknown": "counted as a miss (could not verify, not clean)",
            "retracted": "F3 retraction checker against OpenAlex",
            "predatory": "no detector; venue mismatch is not counted as detection",
        },
    }
    RESULTS.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "label", "expected_problem", "status", "pred_problem", "title_sim"])
        for row in predictions:
            writer.writerow([row["id"], row["label"], row["expected_problem"], row["status"], row["pred_problem"], row["title_sim"]])

    print(json.dumps({"metadata": summary, "special": result["special"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
