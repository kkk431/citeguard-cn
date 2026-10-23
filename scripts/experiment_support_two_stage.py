"""Two-stage support judge: v3 verdict, then a coverage audit that can downgrade support -> partial.

Stage 1 uses the production prompt (v3, evidence-first). Stage 2 only runs for
items classified as ``support``: an "audit" prompt checks whether every claim
factor (object / condition / causal chain / magnitude) is covered by the evidence;
if not, the verdict is downgraded to ``partial``.

This targets the dominant error in the confusion matrix (partial -> support).

Usage:
    DEEPSEEK_API_KEY=... PYTHONPATH=src python scripts/experiment_support_two_stage.py \
        --out data/experiments/support_two_stage_results.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
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


def _cache_file(tag: str, prompt: str, claim: str, evidence: str, model: str) -> Path:
    raw = f"{tag}||{prompt}||{claim}||{evidence}||{model}"
    return CACHE / (hashlib.md5(raw.encode("utf-8")).hexdigest() + ".json")


def call(prompt: str, claim: str, evidence: str, model: str, tag: str) -> dict:
    cached = _cache_file(tag, prompt, claim, evidence, model)
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
            "max_tokens": 500,
        },
        timeout=60,
    )
    out: dict = {"label": "no_evidence"}
    if resp.status_code == 200:
        content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        m = re.search(r"\{.*\}", content, re.S)
        if m:
            try:
                out = json.loads(m.group(0))
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
    f1s, per = [], {}
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
    return {
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "accuracy": round(sum(matrix[i][i] for i in range(len(LABELS))) / total, 4),
        "confusion": matrix,
        "per_class": per,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage1", default=str(ROOT / "scripts" / "support_prompt_v3.txt"))
    ap.add_argument("--audit", default=str(ROOT / "scripts" / "support_prompt_audit.txt"))
    ap.add_argument("--out", default=str(ROOT / "data" / "experiments" / "support_two_stage_results.json"))
    ap.add_argument("--model", default=config.DEEPSEEK_MODEL)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if not config.DEEPSEEK_API_KEY:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2

    stage1 = Path(args.stage1).read_text(encoding="utf-8")
    audit = Path(args.audit).read_text(encoding="utf-8")
    rows = load(DATASET)
    preds: list[str] = [""] * len(rows)
    details: list[dict] = [{} for _ in rows]

    def work(i: int) -> None:
        r = rows[i]
        first = call(stage1, r["claim"], r["evidence"], args.model, "stage1-v3")
        label = first.get("label", "no_evidence")
        if label not in LABELS:
            label = "no_evidence"
        downgraded = False
        covered = None
        if label == "support":
            audit_out = call(audit, r["claim"], r["evidence"], args.model, "audit-v1")
            covered = audit_out.get("fully_covered")
            if covered is False:
                label = "partial"
                downgraded = True
        with LOCK:
            preds[i] = label
            details[i] = {"stage1": first.get("label"), "fully_covered": covered, "downgraded": downgraded}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, range(len(rows))))

    result = metrics(rows, preds)
    result.update(
        {
            "n": len(rows),
            "model": args.model,
            "stage1_prompt_sha256": hashlib.sha256(stage1.encode("utf-8")).hexdigest()[:16],
            "audit_prompt_sha256": hashlib.sha256(audit.encode("utf-8")).hexdigest()[:16],
            "downgraded": sum(1 for d in details if d.get("downgraded")),
            "two_stage": True,
        }
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
