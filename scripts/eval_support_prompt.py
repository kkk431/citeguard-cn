"""Evaluate ClaimSupport-CN against an OpenAI-compatible judge with prompt variants.

Designed for open-source judges served locally (Qwen2.5/Qwen3), but works with
any `/chat/completions` endpoint. Reports macro-F1, accuracy, per-class P/R/F1,
a 4x4 confusion matrix, latency and raw failure cases.

Split protocol: tune on the fixed dev split, report the untouched test split
(`split_seed20261024.json`); `--split all` keeps comparability with the earlier
100-case numbers.

Usage:
    CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8098/v1 \
    CITEGUARD_JUDGE_MODEL=qwen3-8b \
    PYTHONPATH=src python3 scripts/eval_support_prompt.py \
        --prompt v6 --split test --tag qwen3-8b-v6
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard import support as support_mod  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LABELS = ["support", "partial", "contradict", "no_evidence"]
DATA_DIR = ROOT / "data" / "claimsupport_cn"
DEFAULT_DATASET = DATA_DIR / "claimsupport_cn.jsonl"
DEFAULT_SPLIT = DATA_DIR / "split_seed20261024.json"
DEFAULT_OUT_DIR = DATA_DIR / "prompt_runs"
V6_PROMPT = ROOT / "scripts" / "support_prompt_v6.txt"
V7_PROMPT = ROOT / "scripts" / "support_prompt_v7.txt"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def metrics(y_true: list[str], y_pred: list[str]) -> dict:
    index = {label: i for i, label in enumerate(LABELS)}
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for true, pred in zip(y_true, y_pred):
        matrix[index[true]][index[pred]] += 1
    per_class = {}
    for i, label in enumerate(LABELS):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(LABELS))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(matrix[i]),
            "predicted": sum(matrix[r][i] for r in range(len(LABELS))),
        }
    macro_f1 = round(sum(v["f1"] for v in per_class.values()) / len(LABELS), 4)
    total = sum(sum(row) for row in matrix) or 1
    accuracy = round(sum(matrix[i][i] for i in range(len(LABELS))) / total, 4)
    return {
        "macro_f1": macro_f1,
        "accuracy": accuracy,
        "per_class": per_class,
        "confusion": matrix,
    }


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def post_chat(base: str, model: str, key: str, system: str, user: str,
              temperature: float, max_tokens: int) -> tuple[str, float, float]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    started = time.perf_counter()
    resp = requests.post(base.rstrip("/") + "/chat/completions", headers=headers, json=payload, timeout=180)
    elapsed = time.perf_counter() - started
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    upstream = float(data.get("elapsed_s", 0.0) or 0.0)
    return content, elapsed, upstream


def majority(labels: list[str]) -> str:
    counts = Counter(labels)
    best = max(counts.values())
    tied = [label for label, count in counts.items() if count == best]
    if len(tied) == 1:
        return tied[0]
    for preferred in ("contradict", "no_evidence", "partial", "support"):
        if preferred in tied:
            return preferred
    return tied[0]


def audit_verdict(base: str, model: str, key: str, claim: str, evidence: str,
                  style: str = "v1") -> Optional[bool]:
    system = "你是严谨的学术引文核验员。"
    prompt = support_mod.AUDIT_PROMPTS.get(style, support_mod.AUDIT_PROMPT)
    user = prompt + f"\n\n【引用句】{claim}\n【证据片段】{evidence[:1800]}"
    try:
        content, _elapsed, _upstream = post_chat(base, model, key, system, user, 0.0, 500)
    except Exception:
        return None
    obj = parse_json(content)
    value = obj.get("fully_covered")
    if value is None:
        verdict = obj.get("verdict")
        if verdict in ("yes", "partial", "no"):
            value = verdict == "yes"
    return value if isinstance(value, bool) else None


def judge_item(row: dict, args: argparse.Namespace, prompt_text: str) -> dict:
    claim, evidence = row["claim"], row["evidence"]
    user = f"【引用句】{claim}\n【证据片段】{evidence[:1800]}"
    started = time.perf_counter()
    labels: list[str] = []
    raws: list[str] = []
    errors: list[str] = []
    runs = args.votes if args.votes > 1 else 1
    temperature = args.temperature if runs > 1 else 0.0
    for _ in range(runs):
        try:
            content, _elapsed, _upstream = post_chat(
                args.base, args.model, args.api_key,
                "你是严谨的学术引文核验员。", prompt_text + "\n\n" + user,
                temperature, args.max_tokens,
            )
            obj = parse_json(content)
            label = obj.get("label")
            if label not in LABELS:
                label = "no_evidence"
                errors.append("invalid_label")
            labels.append(label)
            raws.append(content[:600])
        except Exception as exc:  # pragma: no cover - network/server failures
            labels.append("no_evidence")
            raws.append("")
            errors.append(f"{type(exc).__name__}: {exc}"[:200])
    label = majority(labels)
    audited = None
    if label == "support" and args.audit:
        audited = audit_verdict(args.base, args.model, args.api_key, claim, evidence,
                                getattr(args, "audit_style", "v1"))
        if audited is False:
            label = "partial"
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "id": row["id"],
        "label": row["label"],
        "pred": label,
        "votes": labels,
        "audit_fully_covered": audited,
        "raw": raws[0] if raws else "",
        "error": "; ".join(errors),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def load_rows(split: str, split_path: Path, dataset: Path) -> list[dict]:
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if split == "all":
        return rows
    payload = json.loads(split_path.read_text(encoding="utf-8"))
    wanted = set(payload[split])
    picked = [row for row in rows if row["id"] in wanted]
    if len(picked) != len(wanted):
        raise RuntimeError(f"split {split}: expected {len(wanted)} rows, found {len(picked)}")
    return picked


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a judge prompt on ClaimSupport-CN.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--split", choices=["dev", "test", "all"], default="test")
    parser.add_argument("--split-file", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--prompt", choices=["v4", "v6", "v7"], default="v6")
    parser.add_argument("--prompt-file", type=Path, default=None)
    parser.add_argument("--votes", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--audit", action="store_true", default=True)
    parser.add_argument("--no-audit", dest="audit", action="store_false")
    parser.add_argument("--audit-style", choices=["v1", "v2", "v3"], default="v1")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=420)
    parser.add_argument("--tag", default="")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    import os
    args.base = (os.environ.get("CITEGUARD_JUDGE_BASE_URL") or "").rstrip("/")
    args.model = os.environ.get("CITEGUARD_JUDGE_MODEL") or ""
    args.api_key = os.environ.get("CITEGUARD_JUDGE_API_KEY") or ""
    if not args.base:
        args.base, args.model, args.api_key = support_mod.judge_endpoint()
    if not args.base:
        print("[fatal] set CITEGUARD_JUDGE_BASE_URL (and _MODEL) to a local server", file=sys.stderr)
        return 2

    if args.prompt == "v4":
        prompt_text = support_mod.PROMPT
        prompt_tag = "v4"
    elif args.prompt == "v7":
        path = args.prompt_file or V7_PROMPT
        prompt_text = path.read_text(encoding="utf-8")
        prompt_tag = "v7" if path == V7_PROMPT else path.stem
    else:
        path = args.prompt_file or V6_PROMPT
        prompt_text = path.read_text(encoding="utf-8")
        prompt_tag = "v6" if path == V6_PROMPT else path.stem

    rows = load_rows(args.split, args.split_file, args.dataset)
    if args.limit:
        rows = rows[: args.limit]
    tag = args.tag or f"{args.model or 'judge'}-{prompt_tag}-{args.split}"

    print(f"[run] judge={args.model} base={args.base} prompt={prompt_tag} split={args.split} "
          f"n={len(rows)} votes={args.votes} audit={args.audit} audit_style={args.audit_style}")
    started = time.perf_counter()
    results = []
    for i, row in enumerate(rows, 1):
        item = judge_item(row, args, prompt_text)
        results.append(item)
        print(f"  [{i:3d}/{len(rows)}] {item['id']} true={item['label']:<12} pred={item['pred']:<12} "
              f"{item['elapsed_ms'] / 1000:.2f}s")
    total_s = time.perf_counter() - started

    y_true = [r["label"] for r in results]
    y_pred = [r["pred"] for r in results]
    scores = metrics(y_true, y_pred)
    payload = {
        "dataset": "ClaimSupport-CN",
        "split": args.split,
        "n": len(results),
        "tag": tag,
        "generated_at": utc_now(),
        "judge": {"base": args.base, "model": args.model},
        "prompt": {
            "tag": prompt_tag,
            "sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            "votes": args.votes,
            "temperature": args.temperature if args.votes > 1 else 0.0,
            "audit": args.audit,
            "audit_style": args.audit_style if args.audit else None,
        },
        "metrics": scores,
        "latency": {
            "total_s": round(total_s, 1),
            "mean_ms": round(sum(r["elapsed_ms"] for r in results) / len(results), 1),
            "p50_ms": round(sorted(r["elapsed_ms"] for r in results)[len(results) // 2], 1),
        },
        "errors": sum(1 for r in results if r["error"]),
        "predictions": results,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{tag}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pred_csv = args.out_dir / f"{tag}.csv"
    with pred_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id", "label", "pred", "votes", "audit_fully_covered", "error", "elapsed_ms"])
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in writer.fieldnames})
    print(f"[done] macro_f1={scores['macro_f1']} acc={scores['accuracy']} "
          f"mean={payload['latency']['mean_ms']}ms errors={payload['errors']}")
    print(f"[out] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
