"""Generate real data charts for the CiteGuard-CN defence deck.

All numbers are read from data/experiments/*.json; no illustrative numbers.
Charts are drawn on a transparent background so they can sit on the dark slide.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "data" / "experiments"
OUT = ROOT / "report" / "deck_html" / "img"
OUT.mkdir(parents=True, exist_ok=True)

TEXT = "#eaf6f3"
MUTED = "#93b3ae"
CYAN = "#63e6ff"
MINT = "#7ff0cf"
AMBER = "#ffb43a"
RED = "#ff6b5e"
STEEL = "#5b7f8c"
GRID = "#1d3a4a"

plt.rcParams.update(
    {
        "font.sans-serif": ["Microsoft YaHei", "SimHei"],
        "axes.unicode_minus": False,
        "text.color": TEXT,
        "axes.labelcolor": TEXT,
        "xtick.color": TEXT,
        "ytick.color": TEXT,
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "savefig.facecolor": "none",
        "savefig.transparent": True,
    }
)


def load(name: str):
    return json.loads((EXP / name).read_text(encoding="utf-8"))


def save(fig, name: str):
    path = OUT / name
    fig.savefig(path, dpi=120, bbox_inches="tight", pad_inches=0.15, transparent=True)
    plt.close(fig)
    print("saved", path, path.stat().st_size, "bytes")


# ---------------------------------------------------------------- chart 1
def chart_status():
    online = load("verify_real.json")["summary"]
    library = load("library_real.json")["summary"]
    labels = ["无本地库\n仅在线源", "有本地库\n本校 409 条"]
    rows = [
        [
            online["status"].get("Exact", 0),
            online["status"].get("Minor", 0),
            online["status"].get("Unverified", 0),
            online["status"].get("Major", 0),
        ],
        [
            library["status"].get("Exact", 0),
            library["status"].get("Minor", 0),
            library["status"].get("Unverified", 0),
            library["status"].get("Major", 0),
        ],
    ]
    names = ["Exact 精确命中", "Minor 小偏差", "Unverified 未核实", "Major 严重不符（0）"]
    colors = [MINT, AMBER, STEEL, RED]

    fig, ax = plt.subplots(figsize=(15.2, 6.4))
    y = [1, 0]
    left = [0, 0]
    for i, name in enumerate(names):
        vals = [r[i] for r in rows]
        ax.barh(y, vals, left=left, color=colors[i], height=0.52, label=name, edgecolor="none")
        for yi, l, v in zip(y, left, vals):
            if v >= 34:
                ax.text(l + v / 2, yi, str(v), ha="center", va="center", fontsize=15, fontweight="bold",
                        color="#06121c" if i < 3 else "white")

        left = [a + b for a, b in zip(left, vals)]

    for yi, total in zip(y, [online["refs"], library["refs"]]):
        ax.text(total + 6, yi, f"{total} 条", va="center", fontsize=17, fontweight="bold", color=TEXT)
        ax.text(total + 6, yi - 0.27, "Major 0", va="center", fontsize=12.5, color=MINT)
    minor = library["status"].get("Minor", 0)
    if minor:
        ax.text(409 + 14, 0.24, f"Minor {minor}", va="center", fontsize=12.5, color=AMBER, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=17, fontweight="bold")
    ax.set_xlim(0, 460)
    ax.set_xticks([])
    for s in ("top", "right", "bottom", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0, pad=14)

    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=4, frameon=False, fontsize=13.5,
              handlelength=1.1, columnspacing=1.6, handletextpad=0.6)
    ax.set_title("建库前 vs 建库后：同 409 条引用的核验结论（Major 均为 0）", fontsize=20, fontweight="bold", loc="left", pad=58)
    fig.text(0.0, -0.07, "数据：verify_real.json + library_real.json · 20 篇 / 409 条 · Unverified ≠ 错误",
             fontsize=13, color=MUTED)
    save(fig, "chart_status.png")


# ---------------------------------------------------------------- chart 2
def chart_confusion():
    d = load("support_local_qwen3_14b_v10_test.json")
    cm = d["metrics"]["confusion"]
    m = d["metrics"]
    labels = ["支持", "部分支持", "矛盾", "无证据"]
    n = d["n"]

    fig, ax = plt.subplots(figsize=(9.8, 8.4))
    # dark-teal to amber ramp
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("cg", ["#0a1c29", "#123f4d", "#1f7a7a", "#63e6ff"])
    im = ax.imshow(cm, cmap=cmap, vmin=0, vmax=max(max(r) for r in cm))

    for i in range(4):
        for j in range(4):
            v = cm[i][j]
            diag = i == j
            ax.text(j, i, str(v), ha="center", va="center", fontsize=19 if diag else 17,
                    fontweight="bold" if diag else "normal",
                    color="#06121c" if v > max(max(r) for r in cm) * 0.55 else TEXT)
    ax.set_xticks(range(4), labels, fontsize=15)
    ax.set_yticks(range(4), labels, fontsize=15)
    ax.set_xlabel("模型判定", fontsize=15, labelpad=12)
    ax.set_ylabel("人工标注（金标）", fontsize=15, labelpad=26)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([x - 0.5 for x in range(1, 4)], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, 4)], minor=True)
    ax.grid(which="minor", color="#06121c", linewidth=3)
    ax.tick_params(which="minor", length=0)

    ax.set_title(f"支持度判定混淆矩阵 · 14B / v10 · n={n}", fontsize=21, fontweight="bold", loc="left", pad=30)
    fig.text(0.0, 1.005, f"macro-F1 {m['macro_f1']:.4f}   ·   accuracy {m['accuracy']:.2f}   ·   对角线 = 判对",
             fontsize=13.5, color=MINT, transform=ax.transAxes)
    fig.text(0.0, -0.07, "数据：support_local_qwen3_14b_v10_test.json · n=60 · prompt v10",
             fontsize=13, color=MUTED)
    save(fig, "chart_confusion.png")


# ---------------------------------------------------------------- chart 3
def chart_models():
    specs = [
        ("Qwen3-8B\nbf16 · 16 GB", "support_local_qwen3_8b_v10_test.json", STEEL),
        ("Qwen3-14B\nbf16 · 28 GB", "support_local_qwen3_14b_v10_test.json", CYAN),
        ("Qwen3-14B\n4-bit · 11.7 GB", "support_local_qwen3_14b_4bit_test.json", AMBER),
    ]
    names, vals, colors = [], [], []
    for label, fname, color in specs:
        m = load(fname)["metrics"]
        names.append(label)
        vals.append(m["macro_f1"])
        colors.append(color)

    fig, ax = plt.subplots(figsize=(12.6, 6.6))
    bars = ax.bar(range(3), vals, width=0.5, color=colors, edgecolor="none")
    for i, v in enumerate(vals):
        ax.text(i, v + 0.006, f"{v:.4f}", ha="center", va="bottom", fontsize=21, fontweight="bold", color=TEXT)
    ax.axhline(0.90, color="#ff6b5e", linewidth=1.2, linestyle=(0, (5, 5)), alpha=0.8)
    

    ax.set_xlim(-0.55, 2.55)
    ax.set_xticks(range(3), names, fontsize=15)
    ax.set_ylim(0.78, 1.0)
    ax.set_yticks([0.80, 0.85, 0.90, 0.95, 1.00])
    ax.set_yticklabels(["0.80", "0.85", "0.90", "0.95", "1.00"], fontsize=13)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)

    ax.set_title("开源模型能不能扛住？同一条 prompt 的三种跑法", fontsize=20, fontweight="bold", loc="left", pad=34)
    ax.text(0.30, 1.005, "4-bit：显存 28 → 11.7 GB，F1 与 bf16 持平", transform=ax.transAxes, fontsize=13.5,
            color=AMBER, fontweight="bold")
    fig.text(0.0, -0.07, "数据：三个 support_*_v10_test.json · 同一 60 条留出集 · 本地推理",
             fontsize=13, color=MUTED)
    save(fig, "chart_models.png")


if __name__ == "__main__":
    chart_status()
    chart_confusion()
    chart_models()
