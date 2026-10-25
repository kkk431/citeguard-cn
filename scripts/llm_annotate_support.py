#!/usr/bin/env python
"""LLM-assisted annotation of ClaimSupport-CN (sensitivity check, not human gold).

The dataset labels are programmatically constructed. This script asks one or two
*independent* LLM annotators to read claim + evidence under a fixed rubric and
reports (a) agreement with the constructed labels, (b) Cohen's kappa between
annotators. It is explicitly NOT a human-labeled subset.

Usage:
  python scripts/llm_annotate_support.py --tag deepseek --model deepseek-chat \
      --base-url https://api.deepseek.com --api-key $env:DEEPSEEK_API_KEY
  python scripts/llm_annotate_support.py --tag qwen3-14b --model qwen3-14b \
      --base-url http://127.0.0.1:8097/v1 --api-key local
  python scripts/llm_annotate_support.py --report  # compare saved runs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "claimsupport_cn"
DATASET = DATA / "claimsupport_cn.jsonl"
LABELS = ["support", "partial", "contradict", "no_evidence"]

RUBRIC = """你是独立的文献评审员。给你一条 claim（论文中的结论性陈述）和一条 evidence（另一段文字）。
请只根据 evidence 判断它对 claim 的支持关系，四选一：
- support：evidence 明确支持 claim 的核心意思（可以有同义改写，但不能多出 claim 没有的条件）。
- partial：evidence 只支持 claim 的一部分，或 claim 加了 evidence 没有的条件/更大结论。
- contradict：evidence 与 claim 冲突（方向相反、数值不符、范围矛盾）。
- no_evidence：evidence 没有涉及 claim 的内容。

只输出 JSON：{"label": "support|partial|contradict|no_evidence", "why": "一句话理由"}
不要输出其他内容。"""


def _split_ids(split: str) -> set[str] | None:
    if split == "all":
        return None
    path = DATA / "split_seed20261024.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if "dev" not in data or "test" not in data:
        raise SystemExit(f"unexpected split file format: {path}")
    ids = data[split]
    return set(ids)


def _read_items(limit: int | None, split: str = "all") -> list[dict]:
    wanted = _split_ids(split)
    rows = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if wanted is None or row["id"] in wanted:
                rows.append(row)
    return rows[:limit] if limit else rows


def _chat(base_url: str, model: str, key: str, claim: str, evidence: str, max_tokens: int = 120) -> dict:
    user = f"claim：{claim}\n\nevidence：{evidence}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    text = body["choices"][0]["message"].get("content") or ""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no json in annotator output: {text[:200]}")
    data = json.loads(match.group(0))
    label = str(data.get("label", "")).strip().lower()
    if label not in LABELS:
        raise ValueError(f"bad label: {label!r}")
    return {"label": label, "why": str(data.get("why", ""))[:200]}


def _kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    if not n:
        return 0.0
    observed = sum(1 for a, b in pairs if a == b) / n
    counts_a: dict[str, int] = {}
    counts_b: dict[str, int] = {}
    for a, _ in pairs:
        counts_a[a] = counts_a.get(a, 0) + 1
    for _, b in pairs:
        counts_b[b] = counts_b.get(b, 0) + 1
    expected = sum((counts_a.get(lab, 0) / n) * (counts_b.get(lab, 0) / n) for lab in LABELS)
    if expected >= 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def run(args: argparse.Namespace) -> None:
    items = _read_items(args.limit, args.split)
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    out_path = DATA / f"llm_annotation_{args.tag}.json"
    if args.resume and out_path.exists():
        prior = json.loads(out_path.read_text(encoding="utf-8"))
        results = {p["id"]: {"label": p["pred"], "why": p.get("why", "")} for p in prior.get("predictions", [])}
        errors = dict(prior.get("errors", {}))
        items = [it for it in items if it["id"] not in results]
        print(f"resume: {len(results)} done, {len(items)} remaining", file=sys.stderr)

    def work(item: dict) -> tuple[str, dict | None, str | None]:
        try:
            return item["id"], _chat(args.base_url, args.model, args.api_key,
                                     item["claim"], item["evidence"], args.max_tokens), None
        except Exception as exc:  # noqa: BLE001 - annotate per item, keep going
            return item["id"], None, f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for item_id, pred, err in pool.map(work, items):
            if pred:
                results[item_id] = pred
            else:
                errors[item_id] = err or "unknown"

    gold = {it["id"]: it["label"] for it in _read_items(None, args.split)}
    pairs = [(gold[i], results[i]["label"]) for i in results]
    n = len(pairs)
    agreement = sum(1 for a, b in pairs if a == b) / n if n else 0.0
    confusion = {lab: {other: 0 for other in LABELS} for lab in LABELS}
    for a, b in pairs:
        confusion[a][b] += 1

    out = {
        "tag": args.tag,
        "model": args.model,
        "base_url": args.base_url,
        "n": n,
        "errors": errors,
        "agreement_with_constructed_labels": round(agreement, 4),
        "cohen_kappa_vs_constructed": round(_kappa(pairs), 4),
        "confusion_gold_pred": confusion,
        "predictions": [
            {"id": i, "gold": gold[i], "pred": results[i]["label"], "why": results[i]["why"]}
            for i in results
        ],
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("tag", "model", "n", "agreement_with_constructed_labels",
                                          "cohen_kappa_vs_constructed")}, ensure_ascii=False))


def report() -> None:
    paths = sorted(DATA.glob("llm_annotation_*.json"))
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    if len(runs) < 2:
        print("need at least two annotation runs to compare annotators")
    else:
        a, b = runs[0], runs[1]
        pa = {p["id"]: p["pred"] for p in a["predictions"]}
        pb = {p["id"]: p["pred"] for p in b["predictions"]}
        common = sorted(set(pa) & set(pb))
        pairs = [(pa[i], pb[i]) for i in common]
        kappa = _kappa(pairs)
        agreement = sum(1 for x, y in pairs if x == y) / len(pairs) if pairs else 0.0
        print(json.dumps({
            "annotator_a": a["tag"], "annotator_b": b["tag"], "n_common": len(pairs),
            "agreement_between_annotators": round(agreement, 4),
            "cohen_kappa_between_annotators": round(kappa, 4),
        }, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    parser.add_argument("--model")
    parser.add_argument("--base-url", default=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    parser.add_argument("--api-key", default=os.environ.get("DEEPSEEK_API_KEY", ""))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=120)
    args = parser.parse_args()
    if args.report:
        report()
        return
    if not args.tag or not args.model:
        parser.error("--tag and --model are required")
    run(args)


if __name__ == "__main__":
    main()
