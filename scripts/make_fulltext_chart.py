"""Render the strict atomic full-text verification result as evidence."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data" / "experiments" / "citemap_atomic_fulltext_summary.json"
OUT = ROOT / "docs" / "evidence" / "shots" / "final" / "charts" / "16-fulltext-atomic.png"

BG = "#07131f"
FG = "#e8f3ef"
MUTED = "#8aa6a0"
MINT = "#3ce6b4"
AMBER = "#ffb43a"
CYAN = "#6fe7ff"
RED = "#ff6b7a"


def font() -> str:
    for name in ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            return name
    return "DejaVu Sans"


def style(ax, title: str) -> None:
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color("#29404b")
    ax.tick_params(colors=MUTED, labelsize=11)
    ax.set_title(title, color=FG, fontsize=15, loc="left", pad=12)
    ax.grid(axis="y", color="#1c303b", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)


def main() -> int:
    data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    plt.rcParams["font.family"] = font()
    fig, axes = plt.subplots(2, 2, figsize=(16, 9), dpi=120, facecolor=BG)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.86, bottom=0.16, hspace=0.5, wspace=0.18)
    fig.text(0.07, 0.94, "全文逐句核验：高精度、低覆盖，比“凑证据”诚实", color=FG, fontsize=23, weight="bold")
    fig.text(
        0.07,
        0.905,
        "21 条原子断言 × 8 篇可获取全文的 OA 论文；只判 full/partial/none，引用必须逐字命中",
        color=MUTED,
        fontsize=12,
    )

    verdicts = data["verdicts"]
    ax = axes[0][0]
    style(ax, "87 个「断言 × 论文」组合的真实判定")
    labels = ["完整支持", "部分支持", "无证据"]
    values = [verdicts["full"], verdicts["partial"], verdicts["none"]]
    bars = ax.bar(labels, values, color=[MINT, AMBER, "#33505c"], width=0.55)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, str(value), ha="center", color=FG, fontsize=13)
    ax.set_ylim(0, max(values) * 1.2)
    ax.text(0.0, -0.36, "覆盖率 2.3%；其余是“没有证据”，不是隐藏", transform=ax.transAxes, color=MUTED, fontsize=11)

    ax = axes[0][1]
    style(ax, "人工 105 格中“有全文且判对”的证据格")
    audits = data["audited_positive_with_fulltext"]
    hits = sum(1 for item in audits if item["fulltext_hit"])
    bars = ax.bar(["命中", "漏掉"], [hits, len(audits) - hits], color=[MINT, RED], width=0.5)
    for bar, value in zip(bars, [hits, len(audits) - hits]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05, str(value), ha="center", color=FG, fontsize=14)
    ax.set_ylim(0, max(3, len(audits) + 1))
    ax.text(0.0, -0.36, f"小样本 {hits}/{len(audits)}；不是全量准确率", transform=ax.transAxes, color=MUTED, fontsize=11)

    ax = axes[1][0]
    style(ax, "按主题拆分：教育 60 组合，医学 27 组合")
    topics = list(data["by_topic"].items())
    names = {"ai_education": "AI 教育", "medical_imaging": "医学影像"}
    bottoms = [0, 0]
    for key, color, label in (("full", MINT, "完整"), ("partial", AMBER, "部分"), ("none", "#33505c", "无证据")):
        vals = [bucket.get(key, 0) for _, bucket in topics]
        ax.bar([names.get(name, name) for name, _ in topics], vals, bottom=bottoms, color=color, width=0.5, label=label)
        bottoms = [a + b for a, b in zip(bottoms, vals)]
    ax.legend(facecolor=BG, edgecolor="#29404b", labelcolor=FG, fontsize=10)
    ax.text(0.0, -0.36, "无证据是正常结果：论文可能没研究该断言", transform=ax.transAxes, color=MUTED, fontsize=11)

    ax = axes[1][1]
    style(ax, "方法边界（答辩时必须一起说）")
    ax.axis("off")
    lines = [
        ("有全文", "8 / 30 篇；其余出版社 403 或跳转失败"),
        ("完整支持", f"{verdicts['full']} / 87 组合（2.3%）"),
        ("人工正例", "2 / 2 命中（样本极小）"),
        ("引用校验", "逐字不命中 → 直接丢弃"),
        ("未人审", "机器 full 不等于人工金标"),
    ]
    for idx, (key, value) in enumerate(lines):
        y = 0.88 - idx * 0.18
        ax.text(0.02, y, key, color=MINT if idx < 3 else AMBER, fontsize=13, weight="bold", transform=ax.transAxes)
        ax.text(0.27, y, value, color=FG, fontsize=12, transform=ax.transAxes)
    fig.text(
        0.07,
        0.02,
        "来源：data/experiments/citemap_atomic_fulltext_summary.json · 复现：scripts/eval_citemap_atomic_fulltext.py + summarize_citemap_atomic_fulltext.py",
        color=MUTED,
        fontsize=9,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=BG, dpi=120)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
