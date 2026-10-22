"""Evaluate CiteBench-CN with CiteGuard-CN's own verifier, and write results.json.

Pipeline per reference (exactly the components used by the product):
    citeguard.reference_parser.parse_reference   -> structured Reference
    citeguard.metadata_verify.verify_reference   -> Exact / Minor / Major / Unknown

``Unknown`` (no candidate could be retrieved at all) is mapped to ``Major`` for
the 3-way benchmark; the raw status is kept in the per-item CSV.

Outputs (under data/citebench_cn/):
    results.json          - the file read by the /benchmark page
    eval_predictions.csv  - one row per reference (full-system prediction)
    cache/                - HTTP response cache used by metadata_verify (reproducible reruns)

Ablations (same code path, controlled mutations):
    full          - DOI anchor + title search (product behaviour)
    - DOI anchor  - DOI removed from the parsed reference; title search only
    - title search- OpenAlex/Crossref title search disabled; DOI resolution only

Usage:
    PYTHONPATH=src python3 scripts/evaluate_citebench.py [--limit N] [--cache DIR] [--workers 6]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import citeguard.config as config  # noqa: E402
from citeguard import metadata_verify as mv  # noqa: E402
from citeguard.reference_parser import parse_reference  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_DIR = ROOT / "data" / "citebench_cn"
DEFAULT_DATASET = DATA_DIR / "citebench_cn.jsonl"
DEFAULT_RESULTS = DATA_DIR / "results.json"
DEFAULT_PRED_CSV = DATA_DIR / "eval_predictions.csv"
DEFAULT_CACHE = DATA_DIR / "cache"
DEEPSEEK_RESULTS = DATA_DIR / "deepseek_results.json"

LABELS = ["Exact", "Minor", "Major"]
UNKNOWN_STATUS = "Unknown"


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


def per_class(matrix: list[list[int]]) -> list[dict]:
    out: list[dict] = []
    for i, label in enumerate(LABELS):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(LABELS))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out.append(
            {
                "label": label,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": sum(matrix[i]),
                "predicted": sum(matrix[r][i] for r in range(len(LABELS))),
            }
        )
    return out


def macro_f1(matrix: list[list[int]]) -> float:
    scores = [item["f1"] for item in per_class(matrix)]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def accuracy(matrix: list[list[int]]) -> float:
    total = sum(sum(row) for row in matrix)
    if not total:
        return 0.0
    return round(sum(matrix[i][i] for i in range(len(LABELS))) / total, 4)


# ---------------------------------------------------------------------------
# Verification passes
# ---------------------------------------------------------------------------

def _label_for_status(status: str) -> str:
    return status if status in LABELS else "Major"


def verify_one(ref_string: str, mode: str) -> dict:
    """Verify one reference; ``mode`` is full | no_doi | doi_only."""
    started = time.perf_counter()
    parsed = parse_reference(ref_string)
    error = ""
    result = None
    try:
        if mode == "no_doi":
            # Ablation: remove the DOI anchor, keep title search.
            parsed.doi = ""
            parsed.url = ""
        result = mv.verify_reference(parsed)
    except Exception as exc:  # pragma: no cover - defensive
        error = f"{type(exc).__name__}: {exc}"
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    status = result.status if result is not None else UNKNOWN_STATUS
    return {
        "parsed_title": parsed.title,
        "parsed_doi": parsed.doi,
        "status": status,
        "pred": _label_for_status(status),
        "title_sim": round(getattr(result, "title_sim", 0.0), 4) if result else 0.0,
        "year_match": bool(getattr(result, "year_match", False)) if result else False,
        "author_match": round(getattr(result, "author_match", 0.0), 4) if result else 0.0,
        "best_title": (result.best.title if result and result.best else ""),
        "best_doi": (result.best.doi if result and result.best else ""),
        "sources": ",".join(result.sources) if result else "",
        "notes": " | ".join(result.notes) if result else error,
        "error": error,
        "elapsed_ms": round(elapsed_ms, 1),
    }


class _NoTitleSearch:
    """Context manager that disables the OpenAlex/Crossref/arXiv title-search adapters."""

    def __enter__(self) -> "_NoTitleSearch":
        self._saved = (mv.search_openalex, mv.search_crossref, mv.search_arxiv)

        def _empty(*_args: Any, **_kwargs: Any) -> list:
            return []

        mv.search_openalex = _empty  # type: ignore[assignment]
        mv.search_crossref = _empty  # type: ignore[assignment]
        mv.search_arxiv = _empty  # type: ignore[assignment]
        return self

    def __exit__(self, *_exc: Any) -> None:
        mv.search_openalex, mv.search_crossref, mv.search_arxiv = self._saved


def run_pass(rows: list[dict], mode: str, workers: int) -> list[dict]:
    results: list[Optional[dict]] = [None] * len(rows)
    done = 0
    lock = threading.Lock()
    started = time.perf_counter()

    def work(i: int) -> tuple[int, dict]:
        return i, verify_one(rows[i]["ref_string"], mode)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(work, i) for i in range(len(rows))]
        for future in as_completed(futures):
            i, result = future.result()
            results[i] = result
            with lock:
                done += 1
                if done % 20 == 0 or done == len(rows):
                    print(f"  [{mode}] {done}/{len(rows)} in {time.perf_counter() - started:.1f}s", flush=True)
    assert all(r is not None for r in results)
    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# DeepSeek baseline (merged if scripts/deepseek_baseline.py has been run)
# ---------------------------------------------------------------------------

def load_deepseek_baseline(dataset_sha: str = "", expected_n: Optional[int] = None) -> Optional[dict]:
    if not DEEPSEEK_RESULTS.exists():
        return None
    try:
        payload = json.loads(DEEPSEEK_RESULTS.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[warn] could not read {DEEPSEEK_RESULTS.name}: {exc}")
        return None
    file_sha = payload.get("dataset_sha256")
    if not file_sha:
        print(f"[warn] {DEEPSEEK_RESULTS.name} has no dataset_sha256 (built before dataset v2); "
              f"re-run scripts/deepseek_baseline.py to refresh the baseline")
        return None
    if dataset_sha and file_sha != dataset_sha:
        print(f"[warn] {DEEPSEEK_RESULTS.name} was built on a different dataset "
              f"({file_sha[:12]} vs {dataset_sha[:12]}); re-run scripts/deepseek_baseline.py")
        return None
    if expected_n is not None and payload.get("n") != expected_n:
        print(f"[warn] {DEEPSEEK_RESULTS.name} covers n={payload.get('n')}, "
              f"evaluation covers n={expected_n}; re-run scripts/deepseek_baseline.py")
        return None
    metrics = payload.get("metrics") or {}
    if metrics.get("macro_f1") is None:
        print(f"[warn] {DEEPSEEK_RESULTS.name} has no metrics (baseline incomplete)")
        return None
    model = payload.get("model") or "deepseek-chat"
    note = payload.get("note") or "zero-shot 3-way classification via DeepSeek API"
    note = f"{note}; n={payload.get('n')}"
    if payload.get("prompt_sha256"):
        note += f"; prompt_sha256={str(payload['prompt_sha256'])[:12]}"
    if payload.get("failures"):
        note += f"; {payload['failures']} API failures mapped to Major"
    entry = {
        "name": f"DeepSeek ({model}, zero-shot)",
        "macro_f1": metrics.get("macro_f1"),
        "accuracy": metrics.get("accuracy"),
        "note": note,
    }
    if payload.get("per_class"):
        entry["per_class"] = payload["per_class"]
    return entry


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    argp = argparse.ArgumentParser(description="Evaluate CiteGuard-CN on CiteBench-CN.")
    argp.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="input JSONL")
    argp.add_argument("--out", type=Path, default=DEFAULT_RESULTS, help="output results.json")
    argp.add_argument("--predictions", type=Path, default=DEFAULT_PRED_CSV, help="per-item CSV")
    argp.add_argument("--limit", type=int, default=0, help="only evaluate the first N items (0 = all)")
    argp.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="HTTP cache directory")
    argp.add_argument("--workers", type=int, default=6, help="parallel verification workers")
    argp.add_argument("--seed", type=int, default=20261022, help="recorded seed (evaluation is deterministic)")
    args = argp.parse_args(argv)

    if not args.dataset.exists():
        print(f"[fatal] dataset not found: {args.dataset} (run scripts/build_citebench.py first)",
              file=sys.stderr)
        return 2

    args.cache.mkdir(parents=True, exist_ok=True)
    # metadata_verify._cache_path() reads config.CACHE_DIR at call time.
    config.CACHE_DIR = args.cache
    print(f"[info] cache dir: {args.cache}")

    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("[fatal] dataset is empty", file=sys.stderr)
        return 2
    print(f"[info] dataset={args.dataset.name} n={len(rows)} seed={args.seed} workers={args.workers}")

    # --- full system ------------------------------------------------------
    print("[1/3] verifying with the full pipeline (DOI anchor + title search) ...")
    full = run_pass(rows, "full", args.workers)
    true_labels = [row["label"] for row in rows]
    full_matrix = confusion_matrix(true_labels, [item["pred"] for item in full])
    full_f1 = macro_f1(full_matrix)
    full_acc = accuracy(full_matrix)
    print(f"  full: macro_f1={full_f1:.4f} accuracy={full_acc:.4f}")

    # --- ablation: no DOI anchor -----------------------------------------
    print("[2/3] ablation: - DOI anchor (title search only) ...")
    no_doi = run_pass(rows, "no_doi", args.workers)
    no_doi_matrix = confusion_matrix(true_labels, [item["pred"] for item in no_doi])
    no_doi_f1 = macro_f1(no_doi_matrix)
    no_doi_acc = accuracy(no_doi_matrix)
    print(f"  - DOI anchor: macro_f1={no_doi_f1:.4f} accuracy={no_doi_acc:.4f}")

    # --- ablation: no title search ---------------------------------------
    print("[3/3] ablation: - title search (DOI resolution only) ...")
    with _NoTitleSearch():
        doi_only = run_pass(rows, "doi_only", args.workers)
    doi_only_matrix = confusion_matrix(true_labels, [item["pred"] for item in doi_only])
    doi_only_f1 = macro_f1(doi_only_matrix)
    doi_only_acc = accuracy(doi_only_matrix)
    print(f"  - title search: macro_f1={doi_only_f1:.4f} accuracy={doi_only_acc:.4f}")

    # --- results.json -----------------------------------------------------
    per_class_full = per_class(full_matrix)
    per_class_map = {
        item["label"]: {
            "precision": item["precision"],
            "recall": item["recall"],
            "f1": item["f1"],
            "support": item["support"],
            "predicted": item["predicted"],
        }
        for item in per_class_full
    }
    dataset_sha = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    baselines = [
        {
            "name": "ours (rule+multi-source)",
            "macro_f1": full_f1,
            "accuracy": full_acc,
            "note": "v1.1: DOI resolution + title search + field checks "
                    "(year/author order/venue/volume/pages); DOI 404 -> Major; Unknown -> Major",
            "per_class": per_class_map,
        }
    ]
    deepseek = load_deepseek_baseline(dataset_sha, expected_n=len(rows))
    if deepseek is not None:
        baselines.append(deepseek)
    else:
        print(f"[info] {DEEPSEEK_RESULTS.name} not found (or built on a different dataset); "
              f"run scripts/deepseek_baseline.py then re-run this script to merge it")

    result = {
        "dataset": "CiteBench-CN",
        "n": len(rows),
        "dataset_sha256": dataset_sha,
        "generated_at": _utc_now(),
        "metrics": {"macro_f1": full_f1, "accuracy": full_acc},
        "per_class": per_class_map,
        "confusion": {"labels": LABELS, "matrix": full_matrix},
        "baselines": baselines,
        "ablation": [
            {"name": "full", "macro_f1": full_f1, "delta": 0.0},
            {"name": "- DOI anchor", "macro_f1": no_doi_f1, "delta": round(no_doi_f1 - full_f1, 4)},
            {"name": "- title search", "macro_f1": doi_only_f1, "delta": round(doi_only_f1 - full_f1, 4)},
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- per-item CSV -----------------------------------------------------
    args.predictions.parent.mkdir(parents=True, exist_ok=True)
    with args.predictions.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "id", "label", "pred", "status", "title_sim", "year_match", "author_match",
                "parsed_doi", "best_doi", "best_title", "sources", "notes", "ref_string",
            ]
        )
        for row, item in zip(rows, full):
            writer.writerow(
                [
                    row["id"], row["label"], item["pred"], item["status"], item["title_sim"],
                    item["year_match"], item["author_match"], item["parsed_doi"], item["best_doi"],
                    item["best_title"], item["sources"], item["notes"], row["ref_string"],
                ]
            )

    # --- console summary --------------------------------------------------
    print("\n[confusion] rows=true, cols=pred " + str(LABELS))
    for label, matrix_row in zip(LABELS, full_matrix):
        print(f"  {label:6s} {matrix_row}")
    print("\n[per-class]")
    for item in per_class(full_matrix):
        print(f"  {item['label']:6s} P={item['precision']:.3f} R={item['recall']:.3f} "
              f"F1={item['f1']:.3f} support={item['support']} predicted={item['predicted']}")
    print(f"\n[done] {args.out}")
    print(f"[done] {args.predictions}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
