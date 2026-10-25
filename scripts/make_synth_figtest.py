"""Generate a controlled synthetic figure-claim set for VL feasibility testing.

Each chart has one supported claim (the true extremum) and one contradicted
claim (wrong value / wrong extremum), so a model can be scored objectively.

Usage: python scripts/make_synth_figtest.py [--n 20]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "figtest_synth"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _bar_chart(rng: random.Random, idx: int) -> dict:
    cats = [f"方法{i}" for i in range(1, 7)]
    vals = [rng.randint(20, 98) for _ in cats]
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=120)
    ax.bar(cats, vals, color="#4C78A8")
    ax.set_title(f"图 {idx} 不同方法的准确率")
    ax.set_ylabel("准确率（%）")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    path = OUT / "images" / f"synth_{idx:02d}.png"
    fig.savefig(path)
    plt.close(fig)
    best = max(range(len(vals)), key=lambda i: vals[i])
    worst = min(range(len(vals)), key=lambda i: vals[i])
    true_claim = f"图中 {cats[best]} 的准确率最高，约为 {vals[best]}%。"
    wrong_val = max(5, round(vals[best] * rng.choice([0.6, 0.65, 0.7])))
    false_claim = f"图中 {cats[best]} 的准确率最高，约为 {wrong_val}%。"
    return {
        "id": f"synth_{idx:02d}",
        "image": path.name,
        "chart_type": "bar",
        "title": f"不同方法的准确率（最高 {cats[best]} {vals[best]}%，最低 {cats[worst]} {vals[worst]}%）",
        "claim_supported": true_claim,
        "claim_contradicted": false_claim,
    }


def _line_chart(rng: random.Random, idx: int) -> dict:
    years = list(range(2016, 2026))
    vals = []
    base = rng.randint(30, 80)
    for _ in years:
        base = max(5, base + rng.randint(-12, 18))
        vals.append(base)
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=120)
    ax.plot(years, vals, marker="o", color="#E45756")
    ax.set_title(f"图 {idx} 年度发文量变化")
    ax.set_ylabel("发文量（篇）")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    path = OUT / "images" / f"synth_{idx:02d}.png"
    fig.savefig(path)
    plt.close(fig)
    best = max(range(len(vals)), key=lambda i: vals[i])
    true_claim = f"图中 {years[best]} 年的发文量最高，约为 {vals[best]} 篇。"
    wrong_year = years[max(0, best - 3)]
    false_claim = f"图中 {wrong_year} 年的发文量最高，约为 {vals[best]} 篇。"
    return {
        "id": f"synth_{idx:02d}",
        "image": path.name,
        "chart_type": "line",
        "title": f"年度发文量（峰值 {years[best]} 年 {vals[best]} 篇）",
        "claim_supported": true_claim,
        "claim_contradicted": false_claim,
    }


def main() -> None:
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)
    OUT = out
    (out / "images").mkdir(parents=True, exist_ok=True)
    for old in (out / "images").glob("*.png"):
        old.unlink()
    rng = random.Random(args.seed)
    items = []
    for i in range(1, args.n + 1):
        items.append(_bar_chart(rng, i) if i % 2 else _line_chart(rng, i))
    meta = {"source": f"synthetic matplotlib charts seed={args.seed}", "n": len(items), "items": items}
    (out / "figtest_synth.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"generated {len(items)} charts -> {out}")
    for item in items[:3]:
        print(item["image"], "|", item["claim_supported"], "|", item["claim_contradicted"])


if __name__ == "__main__":
    main()
