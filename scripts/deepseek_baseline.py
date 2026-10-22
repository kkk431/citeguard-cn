"""DeepSeek zero-shot baseline for CiteBench-CN (used ONLY as a baseline).

The model is given the rendered GB/T-style reference string and must answer one
of Exact / Minor / Major. This baseline has no retrieval: it can only exploit
model knowledge, so it is a reference point, not a verifier.

Reads the API key from the ``DEEPSEEK_API_KEY`` environment variable at runtime.
The key is never written to any file; the on-disk response cache only stores the
prompt text and the model output.

Outputs:
    data/citebench_cn/deepseek_results.json  - metrics, confusion, per-item predictions
    data/citebench_cn/results.json           - baseline entry merged into `baselines`

Usage:
    export DEEPSEEK_API_KEY=...      # PowerShell: $env:DEEPSEEK_API_KEY="..."
    PYTHONPATH=src python3 scripts/deepseek_baseline.py [--limit N] [--workers 8]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "citebench_cn"
DEFAULT_DATASET = DATA_DIR / "citebench_cn.jsonl"
DEFAULT_OUT = DATA_DIR / "deepseek_results.json"
DEFAULT_CACHE = DATA_DIR / "deepseek_cache.json"
RESULTS_JSON = DATA_DIR / "results.json"

LABELS = ["Exact", "Minor", "Major"]
BASELINE_NAME = "DeepSeek (deepseek-chat, zero-shot)"

# ---------------------------------------------------------------------------
# Fixed zero-shot prompt -- FROZEN FOR REPRODUCIBILITY
#
# PROMPT_VERSION is part of the on-disk response cache key, and the prompt's
# sha256 is stored in deepseek_results.json / results.json.  Any wording change
# must bump PROMPT_VERSION (it is a new baseline, not a silent edit), otherwise
# old and new numbers would silently mix.
# ---------------------------------------------------------------------------
PROMPT_VERSION = 3

SYSTEM_PROMPT = (
    "你是中文文献编辑，正在校对参考文献表。给定一条 GB/T 7714 格式的参考文献，请判断它属于哪一类：\n"
    "- Exact：真实文献，且题名、作者、年份、来源、卷期页、DOI 均正确；\n"
    "- Minor：真实文献，但存在元数据偏差（年份、作者顺序、卷期页、DOI 大小写等）；\n"
    "- Major：文献本身不存在或严重错配（题名虚构、来源期刊不存在、DOI 指向不存在的记录等）。\n"
    "只输出一个 JSON 对象，格式为 {\"label\": \"Exact|Minor|Major\"}，不要输出任何其他内容。"
)
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_user_prompt(ref_string: str) -> str:
    return f"参考文献：{ref_string}\n请判断并只输出 JSON。"


def cache_key(model: str, ref_string: str) -> str:
    raw = f"prompt-v{PROMPT_VERSION}\n{model}\n{SYSTEM_PROMPT}\n{build_user_prompt(ref_string)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def call_deepseek(
    api_key: str,
    base_url: str,
    model: str,
    ref_string: str,
    timeout: float = 90.0,
) -> tuple[Optional[str], str]:
    """Return (content, error). Retries transient failures."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(ref_string)},
        ],
        "temperature": 0,
        "max_tokens": 32,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_error = ""
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 401:
                return None, f"HTTP 401 unauthorized (check DEEPSEEK_API_KEY): {resp.text[:200]}"
            if resp.status_code == 200:
                data = resp.json()
                content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                if content:
                    return content.strip(), ""
                last_error = f"empty content: {json.dumps(data, ensure_ascii=False)[:200]}"
            elif resp.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            else:
                return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1.5 * (attempt + 1))
    return None, last_error


_LABEL_RE = re.compile(r"\b(Exact|Minor|Major)\b", re.IGNORECASE)
_LABEL_ALIASES = [
    ("exact", "Exact"), ("真实", "Exact"), ("一致", "Exact"),
    ("minor", "Minor"), ("偏差", "Minor"), ("元数据", "Minor"),
    ("major", "Major"), ("虚构", "Major"), ("错配", "Major"), ("不存在", "Major"),
]


def parse_label(content: str) -> str:
    """Extract a label from the model output (JSON first, then tolerant matching)."""
    if not content:
        return ""
    try:
        obj = json.loads(content)
        if isinstance(obj, dict):
            for key in ("label", "Label", "LABEL", "prediction", "category"):
                value = obj.get(key)
                if isinstance(value, str):
                    found = _normalize_label(value)
                    if found:
                        return found
        elif isinstance(obj, str):
            found = _normalize_label(obj)
            if found:
                return found
    except Exception:
        pass
    match = _LABEL_RE.search(content)
    if match:
        return _normalize_label(match.group(1))
    return _normalize_label(content)


def _normalize_label(text: str) -> str:
    text = (text or "").strip()
    lowered = text.lower()
    if lowered in ("exact", "minor", "major"):
        return lowered.capitalize()
    for needle, label in _LABEL_ALIASES:
        if needle in lowered:
            return label
    return ""


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
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    argp = argparse.ArgumentParser(description="DeepSeek zero-shot baseline for CiteBench-CN.")
    argp.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    argp.add_argument("--out", type=Path, default=DEFAULT_OUT)
    argp.add_argument("--results", type=Path, default=RESULTS_JSON, help="results.json to merge into")
    argp.add_argument("--limit", type=int, default=0, help="only classify the first N items")
    argp.add_argument("--workers", type=int, default=8)
    args = argp.parse_args(argv)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print(
            "[fatal] DEEPSEEK_API_KEY is not set. Export it for this command only, e.g.\n"
            "        PowerShell: $env:DEEPSEEK_API_KEY=\"...\"; python scripts/deepseek_baseline.py\n"
            "        The key must never be written to a file.",
            file=sys.stderr,
        )
        return 2

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

    if not args.dataset.exists():
        print(f"[fatal] dataset not found: {args.dataset} (run scripts/build_citebench.py first)",
              file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("[fatal] dataset is empty", file=sys.stderr)
        return 2
    dataset_sha = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    print(f"[info] dataset={args.dataset.name} sha256={dataset_sha[:12]} "
          f"model={model} base_url={base_url} n={len(rows)} workers={args.workers}")

    # --- response cache (prompt + output only; never the key) -------------
    cache: dict[str, Any] = {}
    if DEFAULT_CACHE.exists():
        try:
            cache = json.loads(DEFAULT_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    cache_lock = threading.Lock()

    def save_cache() -> None:
        with cache_lock:
            snapshot = dict(cache)
        tmp = DEFAULT_CACHE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(DEFAULT_CACHE)

    def classify(row: dict) -> dict:
        key = cache_key(model, row["ref_string"])
        with cache_lock:
            cached = cache.get(key)
        if cached and cached.get("label"):
            return {
                "id": row["id"],
                "label": row["label"],
                "pred": cached["label"],
                "raw": cached.get("content", ""),
                "cached": True,
                "error": "",
            }
        content, error = call_deepseek(api_key, base_url, model, row["ref_string"])
        pred = parse_label(content or "")
        if not pred:  # one extra retry for unparseable output
            content2, error2 = call_deepseek(api_key, base_url, model, row["ref_string"])
            if content2:
                content, error = content2, error2
                pred = parse_label(content2)
        if not pred:
            return {
                "id": row["id"],
                "label": row["label"],
                "pred": "",
                "raw": content or "",
                "cached": False,
                "error": error or "unparseable model output",
            }
        with cache_lock:
            cache[key] = {
                "content": content,
                "label": pred,
                "ts": _utc_now(),
            }
        return {
            "id": row["id"],
            "label": row["label"],
            "pred": pred,
            "raw": content or "",
            "cached": False,
            "error": "",
        }

    predictions: list[Optional[dict]] = [None] * len(rows)
    done = 0
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(classify, row): i for i, row in enumerate(rows)}
        for future in as_completed(futures):
            i = futures[future]
            try:
                predictions[i] = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                row = rows[i]
                predictions[i] = {
                    "id": row["id"], "label": row["label"], "pred": "",
                    "raw": "", "cached": False, "error": f"{type(exc).__name__}: {exc}",
                }
            done += 1
            if done % 10 == 0 or done == len(rows):
                save_cache()
                print(f"  classified {done}/{len(rows)} in {time.perf_counter() - started:.1f}s", flush=True)
    save_cache()

    final = [p for p in predictions if p is not None]
    failures = [p for p in final if not p.get("pred")]
    for item in failures:  # one consistent convention: a failure cannot be verified -> Major
        item["pred"] = "Major"
    true_labels = [item["label"] for item in final]
    pred_labels = [item["pred"] for item in final]
    matrix = confusion_matrix(true_labels, pred_labels)
    per_class_map = {
        item["label"]: {
            "precision": item["precision"],
            "recall": item["recall"],
            "f1": item["f1"],
            "support": item["support"],
        }
        for item in per_class(matrix)
    }
    result = {
        "dataset": "CiteBench-CN",
        "n": len(final),
        "dataset_sha256": dataset_sha,
        "model": model,
        "endpoint": base_url.rstrip("/") + "/chat/completions",
        "generated_at": _utc_now(),
        "metrics": {"macro_f1": macro_f1(matrix), "accuracy": accuracy(matrix)},
        "per_class": per_class_map,
        "confusion": {"labels": LABELS, "matrix": matrix},
        "failures": len(failures),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "note": f"zero-shot 3-way classification, no retrieval; temperature 0; prompt v{PROMPT_VERSION}",
        "predictions": final,
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- merge into results.json -----------------------------------------
    merged = False
    if args.results.exists():
        try:
            main_result = json.loads(args.results.read_text(encoding="utf-8"))
            results_sha = main_result.get("dataset_sha256")
            if results_sha != dataset_sha:
                print(f"[warn] {args.results} was produced on a different dataset "
                      f"({str(results_sha)[:12]} vs {dataset_sha[:12]}); not merging. "
                      f"Re-run scripts/evaluate_citebench.py first.", file=sys.stderr)
                raise RuntimeError("dataset mismatch")
            entries = [b for b in (main_result.get("baselines") or [])
                       if not str(b.get("name", "")).startswith("DeepSeek")]
            entries.append(
                {
                    "name": BASELINE_NAME,
                    "macro_f1": result["metrics"]["macro_f1"],
                    "accuracy": result["metrics"]["accuracy"],
                    "note": result["note"] + f"; n={result['n']}"
                    + (f"; {result['failures']} API failures mapped to Major" if result["failures"] else "")
                    + f"; prompt_sha256={PROMPT_SHA256[:12]}",
                    "per_class": per_class_map,
                }
            )
            main_result["baselines"] = entries
            args.results.write_text(json.dumps(main_result, ensure_ascii=False, indent=2), encoding="utf-8")
            merged = True
        except Exception as exc:
            print(f"[warn] could not merge into {args.results}: {exc}", file=sys.stderr)
    else:
        print(f"[info] {args.results} does not exist yet; run scripts/evaluate_citebench.py "
              f"to generate it, then re-run this script (or the evaluator will merge this file)")

    print("\n[confusion] rows=true, cols=pred " + str(LABELS))
    for label, matrix_row in zip(LABELS, matrix):
        print(f"  {label:6s} {matrix_row}")
    for item in per_class(matrix):
        print(f"  {item['label']:6s} P={item['precision']:.3f} R={item['recall']:.3f} F1={item['f1']:.3f}")
    print(f"\n[deepseek] macro_f1={result['metrics']['macro_f1']:.4f} "
          f"accuracy={result['metrics']['accuracy']:.4f} failures={result['failures']}")
    print(f"[done] {args.out}" + (f" (merged into {args.results})" if merged else ""))
    return 0 if result["failures"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
