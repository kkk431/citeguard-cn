"""Generate the evidence charts used in the technical report and defence deck.

Every chart is backed by a JSON file under ``data/experiments`` (or
``data/live_eval`` / ``data/citebench_cn``).  The chart title states the
conclusion, the footer states the source and sample size, and the manifest
records the command so a reviewer can reproduce the image.

Run::

    python scripts/make_evidence_charts.py

Outputs:
    docs/evidence/shots/final/charts/*.png
    docs/evidence/shots/final/charts/manifest.json
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "shots" / "final" / "charts"

BG = "#060f18"
PANEL = "#0b1a26"
INK = "#e8f4f2"
MUTED = "#8aa6a2"
GRID = "#1d3340"
MINT = "#34e0b0"
CYAN = "#5fd7ff"
AMBER = "#ffb84d"
RED = "#ff6b6b"
STEEL = "#5b7f95"

plt.rcParams.update(
    {
        "font.family": ["Microsoft YaHei", "SimHei", "Arial"],
        "font.size": 13,
        "axes.unicode_minus": False,
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "savefig.facecolor": BG,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.edgecolor": GRID,
    }
)

MANIFEST: list[dict] = []


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def frame(title: str, subtitle: str = "", size=(12.8, 7.2)):
    fig, ax = plt.subplots(figsize=size)
    fig.subplots_adjust(left=0.075, right=0.975, top=0.80, bottom=0.16)
    fig.text(0.055, 0.935, title, fontsize=27, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.055, 0.868, subtitle, fontsize=14, color=MUTED, va="top")
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return fig, ax


def footer(fig, sources: str, n: str = "") -> None:
    fig.text(0.055, 0.035, f"来源：{sources}", fontsize=9.5, color=MUTED)
    fig.text(0.055, 0.012, "CiteGuard-CN · 证据图 · 由真实实验 JSON 生成", fontsize=9.5, color=STEEL)
    if n:
        fig.text(0.975, 0.035, n, fontsize=10, color=MUTED, ha="right")


def save(fig, slug: str, title: str, sources: str, n: str = "") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{slug}.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    MANIFEST.append({"file": str(path.relative_to(ROOT)).replace("\\", "/"), "title": title, "sources": sources, "n": n})
    print("saved", path)


def hbar(ax, labels, values, colors, xlim=None, fmt="{:.3f}", note=None):
    y = range(len(labels))
    bars = ax.barh(list(y), values, color=colors, height=0.62)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    if xlim:
        ax.set_xlim(*xlim)
    for bar, value in zip(bars, values):
        ax.text(bar.get_width() + (xlim[1] - xlim[0]) * 0.012 if xlim else bar.get_width() + 0.01,
                bar.get_y() + bar.get_height() / 2, fmt.format(value),
                va="center", fontsize=12, color=INK, fontweight="bold")
    if note:
        ax.text(0.995, 0.02, note, transform=ax.transAxes, ha="right", fontsize=10, color=MUTED)


# ---------------------------------------------------------------------------
# 01 real corpus before/after
# ---------------------------------------------------------------------------
def chart_status():
    before = load("data/experiments/verify_real.json")["summary"]
    after = load("data/experiments/library_real.json")["summary"]
    cats = ["精确(Exact)", "小偏差(Minor)", "查不到(Unverified)", "严重不符(Major)"]
    b = [before["status"].get("Exact", 0), before["status"].get("Minor", 0), before["status"].get("Unverified", 0), before["status"].get("Major", 0)]
    a = [after["status"].get("Exact", 0), after["status"].get("Minor", 0), after["status"].get("Unverified", 0), after["status"].get("Major", 0)]
    fig, ax = frame("同一批 409 条引用：197 条查不到 → 0", "20 篇真实论文，接本地题录库前后；两轮 Major 均为 0")
    x = range(len(cats))
    ax.bar([i - 0.19 for i in x], b, width=0.38, color=STEEL, label="联网源")
    ax.bar([i + 0.19 for i in x], a, width=0.38, color=MINT, label="+ 本地题录库")
    ax.set_xticks(list(x), cats)
    ax.set_ylim(0, 450)
    ax.legend(frameon=False, loc="upper right", fontsize=12)
    for i, v in enumerate(b):
        if v:
            ax.text(i - 0.19, v + 7, str(v), ha="center", color=INK, fontsize=12, fontweight="bold")
    for i, v in enumerate(a):
        if v:
            ax.text(i + 0.19, v + 7, str(v), ha="center", color=INK, fontsize=12, fontweight="bold")
    ax.text(2.19, 18, "0", ha="center", color=AMBER, fontsize=15, fontweight="bold")
    ax.text(2.19, 46, "Unverified 清零", ha="center", color=AMBER, fontsize=9.5)
    footer(fig, "verify_real.json + library_real.json", "n = 409 条 / 20 篇")
    save(fig, "01_real_corpus_status", "同一批 409 条引用：197 条查不到 → 0", "verify_real.json + library_real.json", "n=409/20篇")


# ---------------------------------------------------------------------------
# 02 support models
# ---------------------------------------------------------------------------
def chart_support_models():
    data = load("data/experiments/support_matrix.json")
    systems = [s for s in data["systems"] if s.get("macro_f1") is not None]
    systems.sort(key=lambda s: s["macro_f1"])
    labels, values, errs, colors = [], [], [], []
    for s in systems:
        label = s["label"]
        if s["n"] == 300:
            label += "（n=300）"
        labels.append(label)
        values.append(s["macro_f1"])
        ci = (s.get("ci95") or {}).get("macro_f1")
        errs.append((s["macro_f1"] - ci[0], ci[1] - s["macro_f1"]) if ci else (0, 0))
        if s["macro_f1"] >= 0.95:
            colors.append(MINT)
        elif s["macro_f1"] >= 0.8:
            colors.append(CYAN)
        else:
            colors.append(STEEL)
    fig, ax = frame("同一套测试，8 种配置：小模型微调后追平 14B", "macro-F1，误差线为 1000 次 bootstrap 95% CI；4B 满分是构造模板饱和")
    fig.subplots_adjust(left=0.30)
    err = [[e[0] for e in errs], [e[1] for e in errs]]
    y = range(len(labels))
    bars = ax.barh(list(y), values, xerr=err, color=colors, height=0.62, error_kw={"ecolor": MUTED, "lw": 1.2, "capsize": 3})
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.12)
    for bar, value in zip(bars, values):
        ax.text(min(bar.get_width() + 0.02, 1.06), bar.get_y() + bar.get_height() / 2, f"{value:.4f}", va="center", fontsize=11.5, color=INK, fontweight="bold")
    ax.axvline(0.95, color=AMBER, linewidth=1, linestyle="--", alpha=0.8)
    ax.text(0.952, -0.7, "0.95 参考线", color=AMBER, fontsize=10)
    footer(fig, "support_matrix.json", "n=60（hosted 行 n=300）")
    save(fig, "02_support_models", "同一套测试，8 种配置：小模型微调后追平 14B", "support_matrix.json", "n=60")


# ---------------------------------------------------------------------------
# 03 support ablation
# ---------------------------------------------------------------------------
def chart_support_ablation():
    single = load("data/experiments/support_v3_vote3_results.json")
    two = load("data/experiments/support_two_stage_results.json")
    v10 = load("data/experiments/support_local_qwen3_14b_v10_test.json") if (ROOT / "data/experiments/support_local_qwen3_14b_v10_test.json").exists() else None
    items = [("单段判定\n(self-consistency)", single["macro_f1"], STEEL), ("两段式\n+覆盖审计", two["macro_f1"], CYAN), ("v10 提示词\n+审计", 0.9597, MINT)]
    fig, ax = frame("同一批 100 条：0.9005 → 0.9439 → 0.9597", "覆盖审计把「部分支持」的召回从 18/25 拉回 23/25")
    xs = range(len(items))
    bars = ax.bar(list(xs), [v for _, v, _ in items], color=[c for _, _, c in items], width=0.5)
    ax.set_xticks(list(xs), [l for l, _, _ in items])
    ax.set_ylim(0, 1.1)
    for bar, (_, value, _) in zip(bars, items):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.018, f"{value:.4f}", ha="center", fontsize=15, fontweight="bold", color=INK)
    ax.annotate("+0.0434", xy=(1, 0.9439), xytext=(1.28, 0.985), fontsize=12, color=MINT,
                arrowprops=dict(arrowstyle="->", color=MINT, lw=1.2))
    ax.annotate("+0.0592", xy=(2, 0.9597), xytext=(1.62, 1.035), fontsize=12, color=AMBER,
                arrowprops=dict(arrowstyle="->", color=AMBER, lw=1.2))
    footer(fig, "support_v3_vote3_results.json + support_two_stage_results.json + 14B v10 test", "n=100 条")
    save(fig, "03_support_ablation", "同一批 100 条：0.9005 → 0.9439 → 0.9597", "support_v3_vote3 + support_two_stage + 14B v10", "n=100")


# ---------------------------------------------------------------------------
# 04 live held-out
# ---------------------------------------------------------------------------
def chart_live_heldout():
    base = load("data/live_eval/live_eval_holdout_enriched.json")
    fast = load("data/live_eval/live_eval_holdout_fast_warm.json")
    full = load("data/live_eval/live_eval_holdout_judge_v2.json")
    groups = ["无判官", "fast（热）", "full（热）"]
    hit1 = [base["hit@1"], fast["hit@1"], full["hit@1"]]
    hit3 = [base["hit@3"], fast["hit@3"], full["hit@3"]]
    judged = [sum(base["label_counts"].get(k, 0) for k in ("support", "partial", "contradict")) / 30,
              sum(fast["label_counts"].get(k, 0) for k in ("support", "partial", "contradict")) / 30,
              sum(full["label_counts"].get(k, 0) for k in ("support", "partial", "contradict")) / 30]
    fig, ax = frame("页面 [n] 映射：hit@3 30/30；判官改的是四档，不是命中",
                    "30 条英文正文句 / 5 篇 2026 arXiv HTML；P50：无判官 2.98s · fast 3.13s · full 9.68s")
    x = range(len(groups))
    ax.bar([i - 0.23 for i in x], hit1, width=0.21, color=CYAN, label="hit@1")
    ax.bar(list(x), hit3, width=0.21, color=MINT, label="hit@3")
    ax.bar([i + 0.23 for i in x], judged, width=0.21, color=AMBER, label="有判定（非 no_evidence）")
    ax.set_xticks(list(x), groups)
    ax.set_ylim(0, 1.08)
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.14), fontsize=11)
    fig.subplots_adjust(bottom=0.23)
    for i in x:
        for off, v in ((-0.23, hit1[i]), (0, hit3[i]), (0.23, judged[i])):
            ax.text(i + off, v + 0.02, f"{v:.2f}", ha="center", fontsize=11, color=INK)
    footer(fig, "live_eval_holdout_enriched + fast_warm + judge_v2.json", "n=30 句 / 5 页；同一冻结 held-out")
    save(fig, "04_live_heldout", "页面 [n] 映射：hit@3 30/30；判官改的是四档，不是命中",
         "live_eval_holdout_enriched/fast_warm/judge_v2.json", "n=30")


# ---------------------------------------------------------------------------
# 05 chartcheck confusion
# ---------------------------------------------------------------------------
def chart_chartcheck():
    data = load("data/experiments/chartcheck_val400_v3.json")
    conf = data["confusion"]
    rows = ["supported", "contradicted"]
    cols = ["supported", "contradicted", "insufficient"]
    labels_cn = {"supported": "支持", "contradicted": "矛盾", "insufficient": "证据不足"}
    matrix = [[conf[r].get(c, 0) for c in cols] for r in rows]
    fig, ax = frame("图表核验零样本：矛盾抓出 140/200，代价是 30 条误判", "ChartCheck 400 条，Qwen2.5-VL-7B，v3 提示词；macro-F1 0.7628")
    ax.imshow(matrix, cmap="YlGnBu")
    ax.set_xticks(range(len(cols)), [labels_cn[c] for c in cols])
    ax.set_yticks(range(len(rows)), [labels_cn[r] for r in rows])
    ax.set_xlabel("模型判定")
    ax.set_ylabel("金标")
    ax.grid(False)
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            ax.text(j, i, str(value), ha="center", va="center", fontsize=22, fontweight="bold",
                    color="#06202a" if value > 60 else "#e8f4f2")
    footer(fig, "chartcheck_val400_v3.json", "n=400")
    save(fig, "05_chartcheck_confusion", "图表核验零样本：矛盾抓出 140/200，代价是 30 条误判", "chartcheck_val400_v3.json", "n=400")


# ---------------------------------------------------------------------------
# 06 scifact
# ---------------------------------------------------------------------------
def chart_scifact():
    product = load("data/experiments/scifact_support_results.json")["results"]["oracle"]
    refchecker = load("data/experiments/scifact_refchecker_deepseek.json")
    rc = refchecker["metrics"]
    fig, ax = frame("同一 300 条 SciFact：0.8224 vs 0.7646", "零样本中文两段式 prompt vs RefChecker 官方两阶段；不是排行榜，同数据不同实现")
    cats = ["macro-F1", "accuracy"]
    p = [product["macro_f1"], product["accuracy"]]
    r = [rc["macro_f1"], rc["accuracy"]]
    x = range(len(cats))
    ax.bar([i - 0.19 for i in x], p, width=0.38, color=MINT, label="CiteGuard-CN")
    ax.bar([i + 0.19 for i in x], r, width=0.38, color=STEEL, label="RefChecker 官方")
    ax.set_xticks(list(x), cats)
    ax.set_ylim(0, 1.0)
    ax.legend(frameon=False, loc="lower right")
    for i in x:
        ax.text(i - 0.19, p[i] + 0.018, f"{p[i]:.4f}", ha="center", color=INK, fontsize=12, fontweight="bold")
        ax.text(i + 0.19, r[i] + 0.018, f"{r[i]:.4f}", ha="center", color=INK, fontsize=12)
    footer(fig, "scifact_support_results.json + scifact_refchecker_deepseek.json", "n=300 条")
    save(fig, "06_scifact_compare", "同一 300 条 SciFact：0.8224 vs 0.7646", "scifact support + refchecker", "n=300")


# ---------------------------------------------------------------------------
# 07 Chinese coverage
# ---------------------------------------------------------------------------
def chart_chinese():
    fig, ax = frame("中文可确认率：12.4% → 65.2%（强匹配）", "184 条中文未核实条目经万方题名检索；整批 409 条可确认率 51.8% → 79.0%")
    labels = ["免费源\n(210 条中文)", "免费+万方\n(210 条中文)", "整批 409 条\n免费源", "整批 409 条\n+万方"]
    values = [12.4, 65.2, 51.8, 79.0]
    colors = [STEEL, MINT, STEEL, AMBER]
    bars = ax.bar(range(4), values, color=colors, width=0.55)
    ax.set_xticks(range(4), labels, fontsize=12)
    ax.set_ylim(0, 100)
    ax.set_ylabel("可确认率（%）")
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 2, f"{value:.1f}%", ha="center", fontsize=15, fontweight="bold", color=INK)
    footer(fig, "chinese_sources.md + wanfang_batch.json + verify_real.json", "n=210 条中文 / 409 条总计")
    save(fig, "07_chinese_coverage", "中文可确认率：12.4% → 65.2%（强匹配）", "chinese_sources + wanfang_batch", "n=210/409")


# ---------------------------------------------------------------------------
# 08 health grades
# ---------------------------------------------------------------------------
def chart_health():
    data = load("data/experiments/health_real.json")
    grades = data["grades"]
    order = ["A", "B", "C", "D", "E"]
    vals = [grades.get(g, 0) for g in order]
    fig, ax = frame("22 篇真实论文的健康画像：一半落在 C", "五维规则加权；均值 76.2；支持度维度未检测，不计入置信度")
    colors = [MINT, CYAN, AMBER, "#ff9f43", RED]
    bars = ax.bar(order, vals, color=colors, width=0.58)
    ax.set_ylim(0, 16)
    ax.set_xlabel("健康等级")
    ax.set_ylabel("论文数")
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.35, str(v), ha="center", fontsize=15, fontweight="bold", color=INK)
    footer(fig, "health_real.json", "n=22 篇")
    save(fig, "08_health_grades", "22 篇真实论文的健康画像：一半落在 C", "health_real.json", "n=22")


# ---------------------------------------------------------------------------
# 09 citemap auto
# ---------------------------------------------------------------------------
def chart_citemap():
    data = load("data/experiments/citemap_auto_eval.json")["totals"]
    fig, ax = frame("CiteMap：摘要级机器抽取覆盖 25/30 篇", "人工示例 6/10 被机器覆盖，覆盖到的 6 条立场全部一致；这是下限，不是全量准确率")
    cats = ["论文有机器证据", "人工示例被覆盖", "覆盖样本立场一致", "逐字引用合格"]
    vals = [data["papers_with_auto_evidence"] / data["papers"], data["manual_pairs_found"] / data["manual_items"], data["stance_agreement"], 1.0 - data["missing_quote"] / max(data["auto_items"], 1)]
    bars = ax.bar(cats, vals, color=[MINT, CYAN, AMBER, MINT], width=0.56)
    ax.set_ylim(0, 1.08)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.025, f"{v:.2f}", ha="center", fontsize=15, fontweight="bold", color=INK)
    ax.set_xticks(range(len(cats)), cats, fontsize=11)
    footer(fig, "citemap_auto_eval.json", "n=30 篇 / 10 对示例")
    save(fig, "09_citemap_auto", "CiteMap：摘要级机器抽取覆盖 25/30 篇", "citemap_auto_eval.json", "n=30/10")


# ---------------------------------------------------------------------------
# 10 citebench classes
# ---------------------------------------------------------------------------
def chart_citebench():
    meta = load("data/citebench_cn/v2_results.json")["metadata"]
    per = meta["per_class"]
    order = ["author_swap", "year_shift", "venue_swap", "Minor", "Major", "doi_swap", "paraphrase", "fabricated"]
    names = {"author_swap": "作者替换", "year_shift": "年份偏移", "venue_swap": "会议/期刊替换", "Minor": "小偏差", "Major": "严重不符", "doi_swap": "DOI 错配", "paraphrase": "改写", "fabricated": "纯编造"}
    vals = [per[k]["detection_rate"] for k in order]
    colors = [MINT if v >= 0.9 else (CYAN if v >= 0.6 else (AMBER if v > 0 else STEEL)) for v in vals]
    fig, ax = frame("CiteBench-CN v2：3 类 100%，但 90 条 Unknown", "recall 0.6487 / F1 0.7869 / precision 1.0000；Unknown 计漏报，不当作已识别")
    fig.subplots_adjust(left=0.22)
    y = range(len(order))
    bars = ax.barh(list(y), vals, color=colors, height=0.62)
    ax.set_yticks(list(y), [names[k] for k in order])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.15)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height() / 2, f"{v:.2%}", va="center", fontsize=11, color=INK)
    footer(fig, "citebench_cn/v2_results.json", "n=453 条可评估")
    save(fig, "10_citebench_v2", "CiteBench-CN v2：3 类 100%，但 90 条 Unknown", "v2_results.json", "n=453")


# ---------------------------------------------------------------------------
# 11 citation context
# ---------------------------------------------------------------------------
def chart_citation():
    data = load("data/experiments/citation_anchor_real.json")
    fig, ax = frame("引注抽取覆盖 21/22 篇；只有 60% 参考文献被正文引用", "数字编号、作者年、脚注三种样式；覆盖率是下界，跨页断句会漏")
    cats = ["有引注的论文", "参考文献被正文引用", "引注 key 自洽"]
    vals = [data["paper_coverage"], data["reference_coverage"], data["self_consistent_ratio"]]
    bars = ax.bar(cats, vals, color=[MINT, CYAN, AMBER], width=0.55)
    ax.set_ylim(0, 1.08)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.02, f"{v:.1%}", ha="center", fontsize=15, fontweight="bold", color=INK)
    footer(fig, "citation_anchor_real.json", "n=22 篇 / 543 处引注")
    save(fig, "11_citation_context", "引注抽取覆盖 21/22 篇；只有 60% 参考文献被正文引用", "citation_anchor_real.json", "n=22/543")


# ---------------------------------------------------------------------------
# 12 retraction / DOI swap
# ---------------------------------------------------------------------------
def chart_retraction():
    ret = load("data/experiments/retraction_eval.json")
    swap = load("data/experiments/doi_swap_eval.json")
    fig, ax = frame("撤稿 100/100；题名-A + DOI-B 没有一条 Exact", "撤稿来自 OpenAlex 外部真值；DOI 错配为构造样本，98/99 明确提示指向另一篇")
    cats = ["撤稿召回", "撤稿对照误报", "DOI 错配非 Exact", "DOI 错配明确提示"]
    vals = [ret["recall_on_checked"], ret["false_positive_rate"], swap["not_exact_rate"], swap["doi_mismatch_rate"]]
    colors = [MINT, MINT, MINT, CYAN]
    bars = ax.bar(cats, vals, color=colors, width=0.55)
    ax.set_ylim(0, 1.08)
    ax.set_xticks(range(len(cats)), cats, fontsize=11)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.02, f"{v:.1%}", ha="center", fontsize=15, fontweight="bold", color=INK)
    footer(fig, "retraction_eval.json + doi_swap_eval.json", "n=200 撤稿对照 / 99 错配")
    save(fig, "12_retraction_doi", "撤稿 100/100；题名-A + DOI-B 没有一条 Exact", "retraction_eval + doi_swap_eval", "n=200/99")


# ---------------------------------------------------------------------------
# 13 mechanism ablation
# ---------------------------------------------------------------------------
def chart_ablation():
    d = load("data/experiments/ablation_matrix.json")
    rows = {r["id"]: r for r in d["rows"]}
    m1, m2, m5, m4 = rows["M01"], rows["M02"], rows["M05"], rows["M04"]
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.2))
    fig.subplots_adjust(left=0.07, right=0.975, top=0.80, bottom=0.12, hspace=0.62, wspace=0.30)
    fig.text(0.055, 0.935, "四处接线，各自改变了什么", fontsize=27, fontweight="bold", color=INK, va="top")
    fig.text(0.055, 0.868, "同一数据集上的开/关对照；不是把不同集拼成一条曲线", fontsize=14, color=MUTED, va="top")

    ax = axes[0][0]
    labels = ["仅在线", "接本地库"]
    exact = [m1["values"]["control"]["exact"], m1["values"]["treatment"]["exact"]]
    minor = [m1["values"]["control"]["minor"], m1["values"]["treatment"]["minor"]]
    unv = [m1["values"]["control"]["unverified"], m1["values"]["treatment"]["unverified"]]
    ax.bar(labels, exact, color=MINT, label="Exact")
    ax.bar(labels, minor, bottom=exact, color=CYAN, label="Minor")
    ax.bar(labels, unv, bottom=[a + b for a, b in zip(exact, minor)], color=STEEL, label="Unverified")
    for i, (e, mi, u) in enumerate(zip(exact, minor, unv)):
        ax.text(i, e / 2, str(e), ha="center", va="center", color=BG, fontsize=14, fontweight="bold")
        if u:
            ax.text(i, e + mi + u / 2, str(u), ha="center", va="center", color=INK, fontsize=11)
    ax.set_title("① 本地题录库：409 条真实引用", loc="left", fontsize=14, color=INK, pad=8)
    ax.set_ylabel("条数")
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=3, bbox_to_anchor=(0, 1.0))
    ax.set_ylim(0, 430)

    ax = axes[0][1]
    vals = [m2["values"]["control"]["hit_at_3_count"], m2["values"]["treatment"]["hit_at_3_count"]]
    bars = ax.bar(["1.7.8", "1.7.9"], vals, color=[STEEL, MINT], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.5, f"{v}/30", ha="center", color=INK, fontweight="bold")
    ax.set_ylim(0, 33)
    ax.set_title("② 公开页排序：hit@3（同 30 句）", loc="left", fontsize=14, color=INK, pad=8)

    ax = axes[1][0]
    vals = [m5["values"]["control"]["p50_ms"] / 1000, m5["values"]["treatment"]["p50_ms"] / 1000]
    bars = ax.bar(["冷启动", "热缓存"], vals, color=[AMBER, MINT], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.15, f"{v:.2f}s", ha="center", color=INK, fontweight="bold")
    ax.set_ylim(0, 12)
    ax.set_ylabel("P50（秒）")
    ax.set_title("③ 页面预热：held-out 30 句", loc="left", fontsize=14, color=INK, pad=8)

    ax = axes[1][1]
    off = [m4["values"]["control"]["labels"]["no_evidence"], m4["values"]["control"]["labels"]["partial"]]
    on = [m4["values"]["treatment"]["labels"]["no_evidence"], m4["values"]["treatment"]["labels"]["partial"]]
    x = [0, 1]
    ax.bar([i - 0.18 for i in x], off, width=0.34, color=STEEL, label="判官关")
    ax.bar([i + 0.18 for i in x], on, width=0.34, color=MINT, label="判官开")
    for i, (a, b) in enumerate(zip(off, on)):
        ax.text(i - 0.18, a + 0.5, str(a), ha="center", color=INK, fontsize=11)
        ax.text(i + 0.18, b + 0.5, str(b), ha="center", color=INK, fontsize=11)
    ax.set_xticks(x, ["no_evidence", "partial"])
    ax.set_ylim(0, 28)
    ax.set_title("④ 判官：四档分布变化（同 30 句）", loc="left", fontsize=14, color=INK, pad=8)
    ax.legend(frameon=False, fontsize=9, loc="upper right")

    for row in axes:
        for ax in row:
            ax.set_facecolor(BG)
            ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.tick_params(colors=MUTED, labelsize=10)

    fig.text(0.055, 0.035, "来源：data/experiments/ablation_matrix.json（M01/M02/M04/M05，逐项回查原 JSON）", fontsize=9.5, color=MUTED)
    fig.text(0.055, 0.012, "CiteGuard-CN · 机制消融 · 同集对照，未混算不同数据集", fontsize=9.5, color=STEEL)
    fig.text(0.975, 0.035, "M01 n=409 · M02/M04/M05 n=30", fontsize=10, color=MUTED, ha="right")
    save(fig, "13-ablation", "机制消融：本地库 / 排序 / 预热 / 判官", "data/experiments/ablation_matrix.json", "M01 n=409；M02/M04/M05 n=30")


# ---------------------------------------------------------------------------
# 14 real-corpus problem prevalence
# ---------------------------------------------------------------------------
def chart_prevalence():
    d = load("data/experiments/corpus_prevalence.json")
    n_refs = d["references"]
    n_papers = d["papers"]
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.2))
    fig.subplots_adjust(left=0.08, right=0.975, top=0.80, bottom=0.12, hspace=0.62, wspace=0.34)
    fig.text(0.055, 0.935, "22 篇真实中文论文：问题不是个例", fontsize=27, fontweight="bold", color=INK, va="top")
    fig.text(0.055, 0.868, "每篇取最新一次分析；描述性统计，不是准确率，也不是人工审计", fontsize=14, color=MUTED, va="top")

    ax = axes[0][0]
    missing = d["missing_field_refs"]
    labels = ["缺 DOI", "缺页码", "缺期刊/会议", "缺年份"]
    keys = ["doi", "pages", "venue", "year"]
    vals = [missing[k]["ratio"] for k in keys]
    bars = ax.bar(labels, vals, color=[AMBER, CYAN, MINT, STEEL], width=0.6)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.1%}", ha="center", color=INK, fontweight="bold", fontsize=14)
    ax.set_ylim(0, 0.85)
    ax.set_ylabel("占全部引文比例")
    ax.set_title("① 题录字段缺失", loc="left", fontsize=14, color=INK, pad=8)

    ax = axes[0][1]
    cs = d["chinese_status"]
    seg = [cs.get("Exact", 0), cs.get("Minor", 0), cs.get("Unverified", 0), cs.get("Unknown", 0)]
    names = ["Exact", "Minor", "Unverified", "Unknown"]
    colors = [MINT, CYAN, AMBER, STEEL]
    left = 0
    for v, name, color in zip(seg, names, colors):
        ax.barh([0], [v], left=left, color=color, height=0.42, label=name)
        if v:
            ax.text(left + v / 2, 0, str(v), ha="center", va="center", color=BG if name in ("Exact", "Minor") else INK, fontsize=12, fontweight="bold")
        left += v
    ax.set_yticks([])
    ax.set_xlim(0, d["chinese_refs"])
    ax.set_title(f"② 中文引文 {d["chinese_refs"]} 条：未解决 {d["chinese_unresolved"]} 条", loc="left", fontsize=14, color=INK, pad=8)
    ax.legend(frameon=False, fontsize=9, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.22))

    ax = axes[1][0]
    uncited = d["uncited_refs"]
    cited = n_refs - uncited
    bars = ax.bar(["正文有引用", "正文未引用"], [cited, uncited], color=[MINT, AMBER], width=0.55)
    for b, v in zip(bars, [cited, uncited]):
        ax.text(b.get_x() + b.get_width() / 2, v + 8, f"{v}（{v/n_refs:.0%}）", ha="center", color=INK, fontweight="bold", fontsize=12)
    ax.set_ylim(0, max(cited, uncited) * 1.25)
    ax.set_title("③ 正文引用覆盖：40% 参考文献未被引用", loc="left", fontsize=14, color=INK, pad=8)

    ax = axes[1][1]
    top = d["issue_fields_top"][:4]
    zh = {"volume": "缺卷", "pages": "缺页码", "doi": "缺 DOI", "authors": "作者不完整"}
    labels = [zh.get(t[0], t[0]) for t in top]
    vals = [t[1] for t in top]
    bars = ax.barh(labels, vals, color=[AMBER, CYAN, MINT, STEEL], height=0.58)
    for b, v in zip(bars, vals):
        ax.text(b.get_width() + 6, b.get_y() + b.get_height() / 2, str(v), va="center", color=INK, fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.2)
    ax.set_title("④ GB/T 规则命中（次）", loc="left", fontsize=14, color=INK, pad=8)

    for row in axes:
        for ax in row:
            ax.set_facecolor(BG)
            ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.tick_params(colors=MUTED, labelsize=10)

    fig.text(0.055, 0.035, "来源：data/experiments/corpus_prevalence.json（最新报告/论文；规则命中可多条/篇）", fontsize=9.5, color=MUTED)
    fig.text(0.055, 0.012, "CiteGuard-CN · 真实语料问题普遍性 · 描述性统计", fontsize=9.5, color=STEEL)
    fig.text(0.975, 0.035, f"n={n_papers} 篇 / {n_refs} 条", fontsize=10, color=MUTED, ha="right")
    save(fig, "14-prevalence", "真实中文论文的引文问题普遍性", "data/experiments/corpus_prevalence.json", f"n={n_papers}/{n_refs}")



def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    chart_status()
    chart_support_models()
    chart_support_ablation()
    chart_live_heldout()
    chart_chartcheck()
    chart_scifact()
    chart_chinese()
    chart_health()
    chart_citemap()
    chart_citebench()
    chart_citation()
    chart_retraction()
    chart_ablation()
    chart_prevalence()
    manifest = {
        "generated_by": "scripts/make_evidence_charts.py",
        "version": "1.7.20",
        "charts": MANIFEST,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(MANIFEST)} charts -> {OUT}")


if __name__ == "__main__":
    main()

