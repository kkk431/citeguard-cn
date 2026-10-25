"""Zero-shot ChartCheck evaluation for the figure-claim checker.

ChartCheck (Akhtar et al., 2024) ships claims over Wikimedia Commons charts with
TRUE/FALSE labels and an S3-hosted image per row. We sample a stratified subset,
send each (image, caption, claim) to a Qwen2.5-VL server, and report accuracy /
macro-F1 with the model's own three-way verdict kept visible (insufficient is
scored as an error for both classes).

Usage:
    python scripts/eval_chartcheck.py --sample 60 --out data/experiments/chartcheck_val60.json
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import random
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "out" / "chartcheck"
IMAGE_DIR = DATA_DIR / "images"

VL_ENDPOINT = os.environ.get("CITEGUARD_VL_ENDPOINT", "http://222.20.126.148:8099/v1")
VL_MODEL = os.environ.get("CITEGUARD_VL_MODEL", "qwen2.5-vl-7b")
PROMPT_VERSION = os.environ.get("CHARTCHECK_PROMPT", "v1")

PROMPTS = {
    "v1": """You are a strict fact-checking assistant. You see a chart and its caption, plus a claim.
Decide whether the chart itself supports or contradicts the claim.
- supported: the chart's data clearly entails the claim.
- contradicted: the chart's data clearly contradicts the claim.
- insufficient: the chart does not contain enough information to decide.
Return ONLY JSON: {"verdict": "supported|contradicted|insufficient", "reason": "<short reason quoting chart values>"}""",
    "v2": """You are a careful chart fact-checker. Given a chart image, its caption, and a claim, decide whether the chart supports the claim.
- supported: the chart (read together with its caption) entails the claim.
- contradicted: the chart (with caption) contradicts the claim.
- insufficient: there is genuinely not enough information.
Judge the chart's data, not prior knowledge. Prefer supported or contradicted when the chart clearly entails or contradicts; use insufficient only when the chart truly lacks the needed information.
Return ONLY JSON: {"verdict": "supported|contradicted|insufficient", "reason": "<short reason>"}""",
}

LABEL_MAP = {"TRUE": "supported", "FALSE": "contradicted"}


def _download(url: str) -> Path:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", url.rsplit("/", 1)[-1])[:60]
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    path = IMAGE_DIR / f"{digest}_{name}"
    if path.exists() and path.stat().st_size > 500:
        return path
    req = urllib.request.Request(url, headers={"User-Agent": "citeguard-chartcheck/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = r.read(15 * 1024 * 1024)
    path.write_bytes(blob)
    return path


def _ask(image: Path, caption: str, claim: str) -> tuple[str, str, float]:
    mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(image.read_bytes()).decode("ascii")
    body = {
        "model": VL_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPTS[PROMPT_VERSION] + f"\n\nCaption: {caption}\nClaim: {claim}"},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 160,
    }
    req = urllib.request.Request(
        VL_ENDPOINT.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.loads(r.read())
    content = payload["choices"][0]["message"].get("content") or ""
    elapsed = time.time() - started
    match = re.search(r"\{.*\}", content, re.S)
    verdict, reason = "insufficient", ""
    if match:
        try:
            parsed = json.loads(match.group(0))
            verdict = str(parsed.get("verdict", "")).strip().lower()
            reason = str(parsed.get("reason", "")).strip()[:200]
        except json.JSONDecodeError:
            pass
    if verdict not in {"supported", "contradicted", "insufficient"}:
        low = content.lower()
        verdict = next((v for v in ("supported", "contradicted", "insufficient") if v in low), "insufficient")
    return verdict, reason, elapsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--out", default="data/experiments/chartcheck_val60.json")
    args = parser.parse_args()

    rows = list(csv.DictReader((DATA_DIR / "val.csv").open(encoding="utf-8", newline="")))
    by_label: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("label") in LABEL_MAP and row.get("claim") and row.get("chart_img"):
            by_label.setdefault(row["label"], []).append(row)
    rng = random.Random(args.seed)
    half = args.sample // 2
    sample: list[dict] = []
    for label, items in sorted(by_label.items()):
        rng.shuffle(items)
        sample.extend(items[:half])
    rng.shuffle(sample)

    records, failures = [], 0
    confusion = {"supported": {"supported": 0, "contradicted": 0, "insufficient": 0},
                 "contradicted": {"supported": 0, "contradicted": 0, "insufficient": 0}}
    latencies = []
    for i, row in enumerate(sample, 1):
        gold = LABEL_MAP[row["label"]]
        try:
            image = _download(row["chart_img"])
            verdict, reason, elapsed = _ask(image, row.get("caption", ""), row["claim"])
        except Exception as exc:  # noqa: BLE001
            failures += 1
            verdict, reason, elapsed = "insufficient", f"error: {exc}", 0.0
        confusion[gold][verdict] = confusion[gold].get(verdict, 0) + 1
        latencies.append(elapsed)
        records.append({
            "chart_img": row["chart_img"], "caption": row.get("caption", "")[:200],
            "claim": row["claim"], "label": row["label"], "gold": gold,
            "pred": verdict, "reason": reason,
        })
        if i % 10 == 0:
            print(f"{i}/{len(sample)} done", flush=True)

    total = len(records)
    correct = sum(1 for r in records if r["pred"] == r["gold"])
    accuracy = correct / total if total else 0.0
    f1s = []
    for cls in ("supported", "contradicted"):
        tp = confusion[cls][cls]
        fp = sum(confusion[g][cls] for g in confusion if g != cls)
        fn = sum(confusion[cls][v] for v in confusion[cls] if v != cls)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    # ChartCheck's FALSE covers "not supported" (chart may simply not show it),
    # so the fair binary mapping is supported -> positive, contradicted/insufficient -> negative.
    binary = {"supported": {"supported": 0, "not_supported": 0},
              "contradicted": {"supported": 0, "not_supported": 0}}
    for r in records:
        binary[r["gold"]]["supported" if r["pred"] == "supported" else "not_supported"] += 1
    btp = binary["supported"]["supported"]
    bfp = binary["contradicted"]["supported"]
    bfn = binary["supported"]["not_supported"]
    btn = binary["contradicted"]["not_supported"]
    bp = btp / (btp + bfp) if btp + bfp else 0.0
    br = btp / (btp + bfn) if btp + bfn else 0.0
    bf1_p = 2 * bp * br / (bp + br) if bp + br else 0.0
    bnp = btn / (btn + bfn) if btn + bfn else 0.0
    bnr = btn / (btn + bfp) if btn + bfp else 0.0
    bf1_n = 2 * bnp * bnr / (bnp + bnr) if bnp + bnr else 0.0
    result = {
        "experiment": "chartcheck_val_zero_shot",
        "dataset": "ChartCheck (Akhtar et al. 2024), val split stratified sample",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": VL_MODEL,
        "endpoint": VL_ENDPOINT,
        "sample": total,
        "seed": args.seed,
        "accuracy": round(accuracy, 4),
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "binary_supported_macro_f1": round((bf1_p + bf1_n) / 2, 4),
        "binary_accuracy": round((btp + btn) / total, 4) if total else 0.0,
        "binary_confusion": binary,
        "confusion": confusion,
        "failures": failures,
        "latency_ms_mean": round(1000 * sum(latencies) / len(latencies), 1) if latencies else None,
        "records": records,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("sample", "accuracy", "macro_f1", "confusion", "failures", "latency_ms_mean")}, ensure_ascii=False))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
