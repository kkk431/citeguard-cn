"""Consistency check for the CiteBench-CN artifacts (no network required except --api-base).

Verifies that the delivered dataset, results, baselines, per-item predictions and
the live `/api/benchmark` contract all agree with each other.  Useful as a
one-command acceptance check before submissions / demos.

Usage:
    python3 scripts/verify_artifacts.py                 # no live API check
    python3 scripts/verify_artifacts.py --api-base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "citebench_cn"
LABELS = ["Exact", "Minor", "Major"]


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes = 0

    def check(self, ok: bool, message: str) -> bool:
        if ok:
            self.passes += 1
            print(f"  PASS  {message}")
        else:
            self.failures.append(message)
            print(f"  FAIL  {message}")
        return ok

    def summary(self) -> int:
        total = self.passes + len(self.failures)
        if self.failures:
            print(f"\n[FAIL] {len(self.failures)}/{total} checks failed:")
            for message in self.failures:
                print(f"  - {message}")
            return 1
        print(f"\n[OK] all {total} checks passed")
        return 0


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _f1_from_confusion(matrix: list[list[int]]) -> tuple[float, float]:
    scores: list[float] = []
    for i in range(len(LABELS)):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(LABELS))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    total = sum(sum(row) for row in matrix)
    accuracy = sum(matrix[i][i] for i in range(len(LABELS))) / total if total else 0.0
    return round(sum(scores) / len(scores), 4), round(accuracy, 4)


def _http_json(url: str) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 - local demo endpoint
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  (api error: {type(exc).__name__}: {exc})")
        return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify CiteBench-CN artifacts.")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--api-base", default="", help="e.g. http://127.0.0.1:8000 (checks /api/benchmark)")
    args = parser.parse_args(argv)

    c = Checker()
    data_dir = args.data_dir
    print(f"[verify] artifacts in {data_dir}")

    # --- dataset ----------------------------------------------------------
    jsonl_path = data_dir / "citebench_cn.jsonl"
    c.check(jsonl_path.exists(), f"{jsonl_path.name} exists")
    if not jsonl_path.exists():
        return c.summary()
    raw = jsonl_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    c.check(len(rows) == 250, f"dataset has 250 rows (got {len(rows)})")
    counts = {label: sum(1 for r in rows if r["label"] == label) for label in LABELS}
    c.check(counts == {"Exact": 100, "Minor": 75, "Major": 75}, f"label counts 100/75/75 (got {counts})")
    no_doi = [r for r in rows if "DOI:" not in r["ref_string"]]
    c.check(len(no_doi) == 75, f"75 rows carry no DOI (got {len(no_doi)})")
    no_doi_label = {label: sum(1 for r in no_doi if r["label"] == label) for label in LABELS}
    c.check(no_doi_label == {"Exact": 30, "Minor": 22, "Major": 23},
            f"no-DOI split 30/22/23 (got {no_doi_label})")
    required = {"id", "ref_string", "label", "corruption", "gold", "source"}
    c.check(all(required.issubset(r) for r in rows), "every row has the six required fields")
    c.check(len({r["id"] for r in rows}) == 250, "ids are unique")
    major_kinds = {r["corruption"].split(":", 1)[1].replace(" (no DOI)", "").strip()
                   for r in rows if r["label"] == "Major"}
    c.check(major_kinds == {"fake_title", "fake_doi"},
            f"Major only contains fake_title/fake_doi (got {sorted(major_kinds)})")
    c.check(not any("minor:doi_" in r["corruption"] for r in rows),
            "no DOI case/suffix perturbations are labelled Minor")

    # --- meta -------------------------------------------------------------
    meta = _load_json(data_dir / "citebench_cn.meta.json") or {}
    c.check(meta.get("n") == 250 and meta.get("counts") == counts, "meta n/counts match the dataset")
    c.check(meta.get("no_doi", {}).get("total") == 75, "meta records 75 no-DOI rows")
    c.check(meta.get("fabricated_doi_check", {}).get("all_missing") is True,
            "fabricated DOIs are all verified 404 (meta)")

    # --- results ----------------------------------------------------------
    results = _load_json(data_dir / "results.json") or {}
    c.check(bool(results), "results.json readable")
    c.check(results.get("n") == 250, f"results.n == 250 (got {results.get('n')})")
    c.check(results.get("dataset_sha256") == sha, "results.dataset_sha256 matches the dataset file")
    confusion = results.get("confusion") or {}
    matrix = confusion.get("matrix") or []
    c.check(confusion.get("labels") == LABELS, "confusion labels are Exact/Minor/Major")
    c.check(sum(sum(row) for row in matrix) == 250, "confusion matrix sums to 250")
    calc_f1, calc_acc = _f1_from_confusion(matrix)
    metrics = results.get("metrics") or {}
    c.check(abs((metrics.get("macro_f1") or 0) - calc_f1) < 1e-3,
            f"stored macro_f1 matches confusion matrix ({calc_f1})")
    c.check(abs((metrics.get("accuracy") or 0) - calc_acc) < 1e-3,
            f"stored accuracy matches confusion matrix ({calc_acc})")
    per_class = results.get("per_class") or {}
    c.check(set(per_class) == set(LABELS), "results.per_class covers all three labels")
    baseline_names = [b.get("name", "") for b in results.get("baselines") or []]
    c.check(any(n.startswith("ours") for n in baseline_names), "results.baselines contains ours")
    c.check(any(n.startswith("DeepSeek") for n in baseline_names), "results.baselines contains DeepSeek")
    ablation = results.get("ablation") or []
    c.check(len(ablation) == 3 and ablation[0].get("name") == "full",
            "results.ablation has full + two ablations")

    # --- per-item CSV -----------------------------------------------------
    pred_path = data_dir / "eval_predictions.csv"
    c.check(pred_path.exists(), f"{pred_path.name} exists")
    if pred_path.exists():
        with pred_path.open(encoding="utf-8", newline="") as fh:
            preds = list(csv.DictReader(fh))
        c.check(len(preds) == 250, f"eval_predictions.csv has 250 rows (got {len(preds)})")
        by_id = {r["id"]: r["label"] for r in rows}
        c.check(all(by_id.get(p["id"]) == p["label"] for p in preds),
                "CSV labels match the dataset labels")

    # --- DeepSeek baseline ------------------------------------------------
    ds = _load_json(data_dir / "deepseek_results.json") or {}
    c.check(bool(ds), "deepseek_results.json readable")
    c.check(ds.get("dataset_sha256") == sha, "DeepSeek baseline was run on this dataset sha256")
    c.check(ds.get("n") == 250 and len(ds.get("predictions") or []) == 250,
            "DeepSeek baseline covers 250 rows")
    c.check(ds.get("failures") == 0, "DeepSeek baseline has 0 API failures")
    c.check(bool(ds.get("prompt_sha256")), "DeepSeek prompt sha256 is recorded (reproducible prompt)")
    ds_baseline = next((b for b in results.get("baselines") or [] if str(b.get("name", "")).startswith("DeepSeek")), None)
    if ds_baseline:
        c.check(ds_baseline.get("macro_f1") == ds.get("metrics", {}).get("macro_f1"),
                "results.json DeepSeek macro_f1 matches deepseek_results.json")

    # --- live API ---------------------------------------------------------
    if args.api_base:
        api = _http_json(args.api_base.rstrip("/") + "/api/benchmark") or {}
        c.check(api.get("available") is True, f"{args.api_base}/api/benchmark available == true")
        c.check(api.get("n") == 250, "/api/benchmark n == 250")
        c.check(api.get("dataset_sha256") == sha, "/api/benchmark serves the current dataset sha256")
        c.check(api.get("metrics", {}).get("macro_f1") == metrics.get("macro_f1"),
                "/api/benchmark macro_f1 matches results.json")
        c.check(set(api.get("per_class") or {}) == set(LABELS), "/api/benchmark exposes per_class for all labels")

    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
