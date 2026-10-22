"""Prompt experiment for the claim-support judge on ClaimSupport-CN.

Usage:
    DEEPSEEK_API_KEY=... PYTHONPATH=src python scripts/experiment_support_prompt.py \
        --prompt-file scripts/support_prompt_v2.txt --out data/experiments/support_v2_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import citeguard.config as config  # noqa: E402

DATASET = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl"
LABELS = ["support", "partial", "contradict", "no_evidence"]
CACHE = ROOT / "data" / "experiments" / "support_prompt_cache"
LOCK = threading.Lock()


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def judge(prompt: str, claim: str, evidence: str, model: str) -> dict:
    key = str(abs(hash((prompt, claim, evidence))))
    cached = CACHE / f"{key}.json"
    if cached.exists():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            pass
    user = f"【引用句】{claim}\n【证据片段】{evidence}"
    resp = requests.post(
        config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "你是严谨的学术引文核验员。"},
                {"role": "user", "content": prompt + "\n\n" + user},
            ],
            "temperature": 0,
            "max_tokens": 400,
        },
        timeout=60,
    )
    out = {"label": "no_evidence", "reason": "request failed"}
    if resp.status_code == 200:
        content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        m = re.search(r"\{.*\}", content, re.S)
        if m:
            try:
                parsed = json.loads(m.group(0))
                label = parsed.get("label", "no_evidence")
                if label not in LABELS:
                    label = "no_evidence"
                out = {
                    "label": label,
                    "reason": parsed.get("reason", ""),
                    "evidence_quote": parsed.get("evidence_quote", ""),
                }
            except Exception:
                pass
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.05)
    return out


def metrics(rows: list[dict], preds: list[str]) -> dict:
    index = {label: i for i, label in enumerate(LABELS)}
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for r, p in zip(rows, preds):
        matrix[index[r["label"]]][index[p]] += 1
    per = {}
    f1s = []
    for i, label in enumerate(LABELS):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(LABELS))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1s.append(f1)
        per[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
    total = len(rows) or 1
    accuracy = sum(matrix[i][i] for i in range(len(LABELS))) / total
    return {
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "accuracy": round(accuracy, 4),
        "confusion": matrix,
        "per_class": per,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model", default=config.DEEPSEEK_MODEL)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not config.DEEPSEEK_API_KEY:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    rows = load(DATASET)
    if args.limit:
        rows = rows[: args.limit]

    preds: list[str] = [""] * len(rows)

    def work(i: int) -> None:
        r = rows[i]
        res = judge(prompt, r["claim"], r["evidence"], args.model)
        with LOCK:
            preds[i] = res["label"]

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, range(len(rows))))

    result = metrics(rows, preds)
    result.update({"prompt_file": args.prompt_file, "n": len(rows), "model": args.model})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
