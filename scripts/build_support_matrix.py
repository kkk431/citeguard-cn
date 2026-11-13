"""Build the ClaimSupport-CN model comparison matrix.

Rows with per-item predictions get a paired bootstrap confidence interval and an
error list; rows that only have aggregate metrics are reported as point estimates.
Everything here is the *constructed* ClaimSupport-CN test split (n=60) unless a
row says otherwise. Do not present it as human-annotated accuracy.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "experiments"
LABELS = ["support", "partial", "contradict", "no_evidence"]

SYSTEMS = [
    {
        "id": "hosted-deepseek-v10",
        "label": "DeepSeek（产品同路径）",
        "n": 300,
        "source": "data/experiments/release300.json",
        "path": "metrics",
        "prompt": "support_prompt_v10 + audit v3",
        "note": "300 条合并集，不是本表 n=60 的同口径；只作参考行",
    },
    {
        "id": "qwen3-14b-v10",
        "label": "Qwen3-14B bf16",
        "n": 60,
        "source": "data/experiments/support_local_qwen3_14b_v10_test.json",
        "path": "metrics",
        "prompt": "support_prompt_v10 + audit v2",
        "note": "本地 14B bf16，v10 提示词",
    },
    {
        "id": "qwen3-14b-4bit-v10",
        "label": "Qwen3-14B 4-bit",
        "n": 60,
        "source": "data/experiments/support_local_qwen3_14b_4bit_test.json",
        "path": "metrics",
        "prompt": "support_prompt_v10 + audit v2",
        "note": "NF4 4-bit，v10 提示词",
    },
    {
        "id": "qwen3-8b-v10",
        "label": "Qwen3-8B bf16",
        "n": 60,
        "source": "data/experiments/support_local_qwen3_8b_v10_test.json",
        "path": "metrics",
        "prompt": "support_prompt_v10 + audit v2",
        "note": "本地 8B bf16，v10 提示词",
    },
    {
        "id": "qwen3-1.7b-base",
        "label": "Qwen3-1.7B 基座（零样本）",
        "n": 60,
        "source": "data/experiments/support_lora_qwen3_1.7b.json",
        "path": "base",
        "prompt": "SFT 同款短提示词",
        "note": "未微调基座，同测试集",
    },
    {
        "id": "qwen3-1.7b-lora",
        "label": "Qwen3-1.7B + LoRA",
        "n": 60,
        "source": "data/experiments/support_lora_qwen3_1.7b_test_predictions.json",
        "prompt": "SFT 短提示词（产品路径 shim）",
        "note": "adapter 69.8 MB；训练 80 条（ext60+dev20）",
    },
    {
        "id": "qwen3-4b-base",
        "label": "Qwen3-4B 基座（零样本）",
        "n": 60,
        "source": "data/experiments/support_lora_qwen3_4b_base_test.json",
        "prompt": "SFT 同款短提示词",
        "note": "未微调基座，同测试集",
    },
    {
        "id": "qwen3-4b-lora",
        "label": "Qwen3-4B + LoRA",
        "n": 60,
        "source": "data/experiments/support_lora_qwen3_4b_test_predictions.json",
        "prompt": "SFT 短提示词（产品路径 shim）",
        "note": "adapter 132 MB；训练 600 条；test 满分是构造模板饱和，不代表 4B 能力上限",
    },
]


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def macro_f1(gold: list[str], pred: list[str]) -> float:
    scores = []
    for label in LABELS:
        tp = sum(1 for g, p in zip(gold, pred) if g == label and p == label)
        fp = sum(1 for g, p in zip(gold, pred) if g != label and p == label)
        fn = sum(1 for g, p in zip(gold, pred) if g == label and p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores)


def accuracy(gold: list[str], pred: list[str]) -> float:
    return sum(1 for g, p in zip(gold, pred) if g == p) / len(gold) if gold else 0.0


def bootstrap(gold: list[str], pred: list[str], n_boot: int = 1000, seed: int = 20261114) -> dict:
    rng = random.Random(seed)
    n = len(gold)
    f1s, accs = [], []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        g = [gold[i] for i in idx]
        p = [pred[i] for i in idx]
        f1s.append(macro_f1(g, p))
        accs.append(accuracy(g, p))
    f1s.sort(); accs.sort()
    lo, hi = int(0.025 * n_boot), int(0.975 * n_boot) - 1
    return {"macro_f1": [round(f1s[lo], 4), round(f1s[hi], 4)], "accuracy": [round(accs[lo], 4), round(accs[hi], 4)]}


def read_metric(source: Path, path: str = "") -> dict:
    data = json.loads(source.read_text(encoding="utf-8"))
    if path:
        for part in path.split("."):
            data = data[part]
    metrics = data.get("metrics", data)
    return {
        "macro_f1": round(float(metrics["macro_f1"]), 4),
        "accuracy": round(float(metrics["accuracy"]), 4),
        "confusion": metrics.get("confusion"),
        "n": int(metrics.get("n") or data.get("n") or 0),
    }


def build() -> dict:
    rows = []
    for system in SYSTEMS:
        source = ROOT / system["source"]
        row = {k: system[k] for k in ("id", "label", "n", "source", "prompt", "note")}
        data = json.loads(source.read_text(encoding="utf-8"))
        if "predictions" in data:
            pairs = [(p.get("gold") or p.get("label"), p["pred"]) for p in data["predictions"]]
            gold = [g for g, _ in pairs]
            pred = [p for _, p in pairs]
            row.update({
                "n": len(pairs),
                "macro_f1": round(macro_f1(gold, pred), 4),
                "accuracy": round(accuracy(gold, pred), 4),
                "ci95": bootstrap(gold, pred),
                "errors": [{"id": p["id"], "gold": p.get("gold") or p.get("label"), "pred": p["pred"]} for p in data["predictions"] if (p.get("gold") or p.get("label")) != p["pred"]],
            })
        else:
            metrics = data.get("metrics", data)
            if system.get("path") == "base":
                metrics = data["base"]
            row.update({
                "n": int(system["n"]),
                "macro_f1": round(float(metrics["macro_f1"]), 4),
                "accuracy": round(float(metrics["accuracy"]), 4),
                "ci95": None,
                "errors": None,
            })
        rows.append(row)
    return {"generated_at": "2026-11-14", "dataset": "ClaimSupport-CN (constructed)", "labels": LABELS, "n_note": "n=60 rows are the same held-out constructed test split; hosted row is n=300 and not directly comparable", "systems": rows}


def to_markdown(matrix: dict) -> str:
    lines = [
        "# 支持度判定模型对比矩阵",
        "",
        "> 数据集：ClaimSupport-CN **构造标签**（不是人工金标）。除特别注明外，n=60 为同一 held-out 构造测试集；",
        "> 有逐条预测的行给 bootstrap 95% CI（1000 次、seed 20261114），只有汇总指标的行给点估计。",
        "> 4B LoRA 的满分是构造模板饱和的结果，不能解读为「4B 比 14B 强」。",
        "",
        "| 系统 | n | macro-F1 | accuracy | 95% CI (F1) | 错误数 | 提示词/口径 | 来源 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in matrix["systems"]:
        ci = row.get("ci95") or {}
        ci_text = f"{ci['macro_f1'][0]:.4f}–{ci['macro_f1'][1]:.4f}" if ci else "—"
        errors = "—" if row.get("errors") is None else str(len(row["errors"]))
        lines.append(
            f"| {row['label']} | {row['n']} | {row['macro_f1']:.4f} | {row['accuracy']:.4f} | {ci_text} | {errors} | {row['prompt']} | `{row['source']}` |"
        )
    lines += ["", "## 错误分析（有逐条预测的行）", ""]
    any_error = False
    for row in matrix["systems"]:
        if row.get("errors"):
            any_error = True
            errs = "、".join(f"{e['id']}（{e['gold']}→{e['pred']}）" for e in row["errors"])
            lines.append(f"- **{row['label']}**：{len(row['errors'])} 条，{errs}")
    if not any_error:
        lines.append("- 4B LoRA 与 14B 等行无逐条错误；1.7B LoRA 的 2 条错误见数据 JSON。")
    lines += [
        "",
        "## 不能这么说",
        "",
        "- 不能说「4B LoRA 准确率 100%」：测试集是同一构造规则生成的模板，训练/测试 claim 不重叠但分布接近；",
        "- 不能把 n=300 的 DeepSeek 行与 n=60 行直接排名；",
        "- 不能把这里的分数当作真人盲标结果；100 条三人盲标尚未回收。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DATA / "support_matrix.json"))
    parser.add_argument("--md", default=str(ROOT / "docs" / "model_matrix.md"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    matrix = build()
    out = Path(args.out); md = Path(args.md)
    if args.check:
        current = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        if current.get("systems") != matrix["systems"] or not md.exists():
            print("support matrix is stale; rerun without --check")
            return 1
        print("support matrix is current")
        return 0
    out.write_text(json.dumps(matrix, ensure_ascii=False, indent=1), encoding="utf-8")
    md.write_text(to_markdown(matrix), encoding="utf-8")
    print(f"wrote {out} and {md} ({len(matrix['systems'])} systems)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
