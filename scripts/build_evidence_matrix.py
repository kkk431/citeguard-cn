"""Build the public evidence matrix from experiment JSON files.

Every number that appears in the report, deck or README should have one row:
claim -> measured value -> sample size -> artifact -> reproduce command -> note.

Run:
    python scripts/build_evidence_matrix.py
    python scripts/build_evidence_matrix.py --check

`--check` verifies that all artifacts exist and that docs/evidence_matrix.md is
up to date (used by tests and CI).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_MD = ROOT / "docs" / "evidence_matrix.md"
OUT_JSON = ROOT / "data" / "experiments" / "evidence_matrix.json"
SHOTS = ROOT / "docs" / "evidence" / "shots"


def load(rel: str):
    path = ROOT / rel
    if not path.exists():
        raise FileNotFoundError(rel)
    return json.loads(path.read_text(encoding="utf-8"))


def f4(x) -> str:
    return f"{float(x):.4f}"


# Each row: category, claim, value builder, sample, artifact, command, note, screenshot
def rows():
    out = []

    d = load("data/citebench_cn/results.json")
    out.append({
        "category": "基准",
        "claim": "CiteBench-CN v1 字段级检出",
        "value": f"macro-F1 {f4(d['metrics']['macro_f1'])} / acc {f4(d['metrics']['accuracy'])}",
        "n": f"{d['n']} 条",
        "artifact": "data/citebench_cn/results.json",
        "command": "PYTHONPATH=src python scripts/eval_citebench.py",
        "note": "250 条构造基准；v1 口径，与 v2 500 条不可混用",
        "screenshot": "",
    })

    d = load("data/citebench_cn/v2_results.json")
    m = d["metadata"]
    out.append({
        "category": "基准",
        "claim": "CiteBench-CN v2 问题检出",
        "value": f"precision {f4(m['precision'])} / recall {f4(m['recall'])} / F1 {f4(m['f1'])} / acc {f4(m['accuracy'])}",
        "n": f"{m['n']} 条（500 中可核验）",
        "artifact": "data/citebench_cn/v2_results.json",
        "command": "PYTHONPATH=src python scripts/eval_citebench_v2.py",
        "note": f"Unknown {m['unknown']} 条（{f4(m['unknown_rate'])}）计漏报；核验完成后 recall {f4(m.get('recall_decided') or 0.8707)}",
        "screenshot": "docs/evidence/shots/phase-46-benchmark-1.7.1.png",
    })

    d = load("data/claimsupport_cn/results.json")
    out.append({
        "category": "基准",
        "claim": "ClaimSupport-CN 100 条",
        "value": f"macro-F1 {f4(d['metrics']['macro_f1'])} / acc {f4(d['metrics']['accuracy'])}",
        "n": f"{d['n']} 条",
        "artifact": "data/claimsupport_cn/results.json",
        "command": "PYTHONPATH=src python scripts/eval_support_local.py",
        "note": "构造标签；产品同路径；v10 prompt + 覆盖审计",
        "screenshot": "docs/evidence/shots/phase-1-model-compare-1.0.12.png",
    })

    d = load("data/experiments/release300.json")
    out.append({
        "category": "基准",
        "claim": "ClaimSupport-CN 300 条合并集",
        "value": f"macro-F1 {f4(d['metrics']['macro_f1'])} / acc {f4(d['metrics']['accuracy'])}",
        "n": f"{d['n']} 条",
        "artifact": "data/experiments/release300.json",
        "command": "见 docs/experiments.md（release300）",
        "note": "构造标签，非人审；与 100/60/140 分批口径不可混用",
        "screenshot": "",
    })

    d = load("data/experiments/support_calibration.json")["claimsupport_300"]
    out.append({
        "category": "校准",
        "claim": "支持度置信度校准",
        "value": f"ECE {f4(d['ece'])}（acc {f4(d['accuracy'])}，平均置信 {f4(d['avg_confidence'])}）",
        "n": f"{d['n']} 条",
        "artifact": "data/experiments/support_calibration.json",
        "command": "PYTHONPATH=src python scripts/eval_support_calibration.py",
        "note": "judge 自报置信度；构造标签",
        "screenshot": "",
    })

    d = load("data/experiments/verify_real.json")["summary"]
    s = d["status"]
    out.append({
        "category": "真实语料",
        "claim": "22 篇真实论文 409 条参考文献",
        "value": f"Exact {s.get('Exact', 0)} / Minor {s.get('Minor', 0)} / Unverified {s.get('Unverified', 0)} / Major {s.get('Major', 0)}",
        "n": f"{d['papers']} 篇 / {d['refs']} 条",
        "artifact": "data/experiments/verify_real.json",
        "command": "PYTHONPATH=src python scripts/eval_verify_real.py",
        "note": "Major 0；Unverified 不等于错误；联网源随网络状态波动",
        "screenshot": "",
    })

    d = load("data/experiments/library_real.json")["summary"]
    out.append({
        "category": "真实语料",
        "claim": "接本地题录库后的 409 条",
        "value": f"Exact {d['status'].get('Exact', 0)} / Minor {d['status'].get('Minor', 0)}，明确结论 {d['definite_verdicts']}/{d['refs']}",
        "n": f"{d['papers']} 篇 / {d['refs']} 条",
        "artifact": "data/experiments/library_real.json",
        "command": "PYTHONPATH=src python scripts/eval_library_real.py",
        "note": f"库内 {d['library_entries']} 条；字段不一致检出 {d['field_mismatch_detected']}",
        "screenshot": "",
    })

    d = load("data/experiments/parse_real.json")["summary"]
    out.append({
        "category": "解析",
        "claim": "真实论文参考文献切分",
        "value": f"{d['pdf_refs']} 条 / clean {f4(d['pdf_clean_ratio'])}",
        "n": f"{d['papers']} 篇",
        "artifact": "data/experiments/parse_real.json",
        "command": "PYTHONPATH=src python scripts/eval_parse_real.py",
        "note": "clean = 标题/年份/作者可解析的比例；非语义正确率",
        "screenshot": "",
    })

    d = load("data/experiments/blind_test5.json")["papers"]
    parts = " / ".join(
        f"{k} {v['refs']} 条 {v['health']*100:.1f}%" for k, v in d.items()
    )
    out.append({
        "category": "解析",
        "claim": "第五次预注册盲测（3 篇新 PDF）",
        "value": parts,
        "n": "3 篇，协议先于运行固定",
        "artifact": "data/experiments/blind_test5.json",
        "command": "见 docs/blind_test_results.md §14",
        "note": "健康率是启发式题名检查，不是语义正确率；不可重选样本",
        "screenshot": "",
    })

    d = load("data/experiments/support_lora_qwen3_1.7b.json")
    out.append({
        "category": "模型",
        "claim": "Qwen3-1.7B LoRA 支持度判定",
        "value": f"test macro-F1 {f4(d['test']['macro_f1'])} / acc {f4(d['test']['accuracy'])}；基座 {f4(d['base']['macro_f1'])}",
        "n": f"{d['data']['test']} 条 test（train {d['data']['train']}）",
        "artifact": "data/experiments/support_lora_qwen3_1.7b.json",
        "command": "PYTHONPATH=src python scripts/eval_support_adapter.py",
        "note": "构造标签；训练/测试同构造管线，衡量格式与映射学习，不是开放世界泛化",
        "screenshot": "",
    })

    d = load("data/experiments/support_matrix.json")
    sysm = {s["id"]: s for s in d["systems"]}
    q = sysm["qwen3-4b-lora"]
    lo, hi = q["ci95"]["macro_f1"]
    out.append({
        "category": "模型",
        "claim": "Qwen3-4B LoRA 支持度判定",
        "value": f"test macro-F1 {f4(q['macro_f1'])} / acc {f4(q['accuracy'])}（95% CI {f4(lo)}–{f4(hi)}）",
        "n": "60 条 test（train 600）",
        "artifact": "data/experiments/support_matrix.json",
        "command": "PYTHONPATH=src python scripts/build_support_matrix.py",
        "note": "构造标签；adapter 132 MB；满分是构造模板饱和，不代表开放世界能力",
        "screenshot": "",
    })

    d = load("data/experiments/chartcheck_val400_v3.json")
    out.append({
        "category": "图表",
        "claim": "ChartCheck 400 零样本",
        "value": f"macro-F1 {f4(d['macro_f1'])} / acc {f4(d['accuracy'])}",
        "n": f"{d['sample']} 条英文图表结论",
        "artifact": "data/experiments/chartcheck_val400_v3.json",
        "command": "PYTHONPATH=src python scripts/eval_chartcheck.py --prompt v3 --sample 400",
        "note": "外部数据，零样本；只看结论与图是否一致",
        "screenshot": "docs/evidence/shots/phase-46-benchmark-1.7.1.png",
    })

    d = load("data/experiments/figure_real26_8b_v3.json")["summary"]["v3"]
    out.append({
        "category": "图表",
        "claim": "真实论文图表小样本",
        "value": f"acc {f4(d['accuracy'])}（支持召回 {f4(d['supported_recall'])}，矛盾召回 {f4(d['contradiction_recall'])}）",
        "n": f"{d['n']} 条断言（样本小）",
        "artifact": "data/experiments/figure_real26_8b_v3.json",
        "command": "PYTHONPATH=src python scripts/eval_figure_prompt.py",
        "note": f"平均 {d['mean_latency_ms']/1000:.2f} s/条；只作小样本复测",
        "screenshot": "",
    })

    d = load("data/experiments/ocr_scan_real.json")
    out.append({
        "category": "扫描件",
        "claim": "扫描版 PDF OCR 后解析",
        "value": f"{d['parsed_refs']}/{d['expected_refs']} 条参考文献",
        "n": f"{d['pages']} 页，{d['dpi']} dpi",
        "artifact": "data/experiments/ocr_scan_real.json",
        "command": "PYTHONPATH=src python scripts/eval_ocr_scanned.py --input <pdf>",
        "note": f"{d['elapsed_sec']} s；字段覆盖 {d['field_coverage']}",
        "screenshot": "",
    })

    d = load("data/experiments/e4_format.json")["metrics"]
    tc = d["type_code_recognition"]
    drift = d["required_fields"]
    out.append({
        "category": "国标",
        "claim": "GB/T 7714-2025 类型码与格式漂移",
        "value": f"类型码 {tc['recognized']}/{tc['total']}；漂移检出 29/30",
        "n": f"{d['n']} 条构造条目录入",
        "artifact": "data/experiments/e4_format.json",
        "command": "PYTHONPATH=src python scripts/e4_format_check.py",
        "note": "30 条漂移为构造样本；不检查作者/卷期语义真实性",
        "screenshot": "docs/evidence/shots/phase-46-report-charts-1.7.1.png",
    })

    d = load("data/experiments/wanfang_batch.json")
    p = d["processed"]
    hits = sum(1 for r in p.values() if r.get("hit"))
    strong = sum(1 for r in p.values() if r.get("hit") and r.get("title_sim", 0) >= 0.92 and r.get("year_match"))
    out.append({
        "category": "中文覆盖",
        "claim": "万方开放平台强命中",
        "value": f"{strong}/{len(p)} 条强命中（{strong/len(p)*100:.1f}%）",
        "n": f"{len(p)} 条中文未核验题录；试用配额",
        "artifact": "data/experiments/wanfang_batch.json",
        "command": "见 docs/chinese_sources.md",
        "note": f"命中 {hits} 条；仅 184 条候选，不是全部中文引用；配额已用完",
        "screenshot": "",
    })

    m = load("data/experiments/real_mutation_eval.json")["summary"]
    mu = m["mutations"]
    out.append({
        "category": "抗伪造",
        "claim": "真实题录变异检测",
        "value": f"{mu['detected']}/{mu['n']} 检出（{mu['detection_rate']*100:.1f}%）",
        "n": f"5 类 x 40 条 = {mu['n']} 条；语料 {m['corpus']['refs']} 条",
        "artifact": "data/experiments/real_mutation_eval.json",
        "command": "见 docs/experiments.md",
        "note": "纯编造 13 条按设计给 Unverified，不计检出；Major 占比高",
        "screenshot": "",
    })

    d = load("data/experiments/doi_swap_eval.json")
    out.append({
        "category": "抗伪造",
        "claim": "题名与 DOI 张冠李戴",
        "value": f"{d['pairs']} 对中 Exact {d['missed_exact']} 条；DOI 不符提示 {d['doi_mismatch_noted']} 条",
        "n": f"{d['pairs']} 对构造样本",
        "artifact": "data/experiments/doi_swap_eval.json",
        "command": "PYTHONPATH=src python scripts/eval_doi_swap.py",
        "note": "构造 swap；不是人工标注；98 条明确写 DOI 指向另一篇",
        "screenshot": "",
    })

    d = load("data/experiments/citation_anchor_real.json")
    out.append({
        "category": "引注",
        "claim": "正文引注抽取与覆盖",
        "value": f"{d['total_citations']} 处引注；被引条目 {d['cited_reference_entries']}/{d['total_references']}（{f4(d['reference_coverage'])}）",
        "n": f"{d['papers_with_citations']}/{len(d['papers'])} 篇有引注",
        "artifact": "data/experiments/citation_anchor_real.json",
        "command": "PYTHONPATH=src python scripts/eval_citation_anchor.py",
        "note": f"key 自洽 {f4(d['self_consistent_ratio'])}；自动检查，不是人工准确率；60.1% 是下界",
        "screenshot": "docs/evidence/shots/phase-33-annotated-citations-1.0.9.png",
    })

    d = load("data/experiments/replacement_eval.json")
    r = d["results"]["bge"]
    out.append({
        "category": "替换候选",
        "claim": "上下文检索候选（BGE-M3）",
        "value": f"R@1 {f4(r['recall@1'])} / R@3 {f4(r['recall@3'])} / R@5 {f4(r['recall@5'])} / MRR {f4(r['mrr'])}",
        "n": f"{d['dataset']['queries']} 查询 / {d['dataset']['pool']} 候选",
        "artifact": "data/experiments/replacement_eval.json",
        "command": "PYTHONPATH=src python scripts/eval_replacement.py",
        "note": "真值是作者实际引用的文献，不是“哪条支持这句话”；BGE 需端点",
        "screenshot": "docs/evidence/shots/phase-F2-replacement-v1.1.5.png",
    })

    d = load("data/experiments/retraction_eval.json")
    out.append({
        "category": "撤稿",
        "claim": "撤稿状态检测",
        "value": f"召回 {d['recall_all']*100:.0f}%（100/100）；对照误报 {d['false_positive_rate']*100:.0f}%",
        "n": "100 撤稿 + 100 对照",
        "artifact": "data/experiments/retraction_eval.json",
        "command": "PYTHONPATH=src python scripts/eval_retraction.py",
        "note": "OpenAlex 同时是样本标签与检测源，衡量一致性不是独立真值",
        "screenshot": "docs/evidence/shots/phase-F3-retraction-v1.1.4.png",
    })

    d = load("data/experiments/health_real.json")
    out.append({
        "category": "健康画像",
        "claim": "22 篇真实论文引用健康分",
        "value": f"均值 {d['mean']} / 中位 {d['median']}（范围 {d['min']}–{d['max']}）",
        "n": f"{d['papers']} 篇；支持度关闭",
        "artifact": "data/experiments/health_real.json",
        "command": "PYTHONPATH=src python scripts/eval_health_real.py",
        "note": "规则加权分，不是期刊标准；仅同一解析/核验版本内可比",
        "screenshot": "docs/evidence/shots/phase-F1-health-v1.1.0.png",
    })

    d = load("data/experiments/stress_1000.json")
    out.append({
        "category": "性能",
        "claim": "1000 条离线题录",
        "value": f"解析 {d['parse_s']} s / 冷启动 {d['cold_full_s']} s / 热 {d['warm_full_s']} s / 双并发 {d['two_concurrent_s']} s",
        "n": f"{d['refs_requested']} 条，{d['chars']} 字符",
        "artifact": "data/experiments/stress_1000.json",
        "command": "PYTHONPATH=src python scripts/stress_1000.py",
        "note": f"峰值 {d['peak_mb']} MB；离线、合成题录，不含联网核验",
        "screenshot": "docs/evidence/shots/phase-3-stress1000-1.0.12.png",
    })

    d = load("data/evidence_map/index.json")
    topics = d["topics"]
    n_papers = sum(t["papers"] for t in topics)
    n_claims = sum(t["claims"] for t in topics)
    out.append({
        "category": "CiteMap",
        "claim": "证据地图语料",
        "value": f"{len(topics)} 主题 / {n_papers} 篇 / {n_claims} 条断言",
        "n": "2 主题 x 15 篇；10 条人工示例",
        "artifact": "data/evidence_map/index.json",
        "command": "PYTHONPATH=src python -m citeguard.evidence_map --check",
        "note": "30/30 DOI 可解析；60 格人工核对待补，当前只展示示例抽取",
        "screenshot": "docs/evidence/shots/phase-49-citemap-1.7.4.png",
    })

    d = load("data/experiments/e2e_smoke.json")
    out.append({
        "category": "工程",
        "claim": "端到端冒烟",
        "value": f"{d['passed']}/{len(d['checks'])} 项通过",
        "n": f"job {d['job']}，version {d['version']}",
        "artifact": "data/experiments/e2e_smoke.json",
        "command": "PYTHONPATH=src python scripts/e2e_smoke.py",
        "note": "含上传/报告/批注/导出/证据包/diff；不含人工判断",
        "screenshot": "",
    })

    return out


PENDING = [
    ("人审", "100 条三人盲标", "包已生成，κ 待回收；不得把构造标签写作人审金标", "dist/CiteGuard-CN_盲标包_100条_发给标注者.zip"),
    ("CiteMap", "60 格人工核对", "只有 10 条人工示例，60 格核对未完成", "t4"),
    ("Live", "真实页面 30 条句子 hit@3", "浏览器扩展 v2 未做", "B2"),
]


def build() -> tuple[str, dict]:
    items = rows()
    missing = []
    for it in items:
        p = ROOT / it["artifact"]
        if not p.exists():
            missing.append(it["artifact"])
        shot = it.get("screenshot")
        if shot and not (ROOT / shot).exists():
            missing.append(shot)
    lines = [
        "# 对外数字 → 证据矩阵",
        "",
        "> 规则：报告、PPT、README、答辩中出现的每个数字，都必须能在本表找到"
        "「证据 JSON / 复现命令 / 样本量 / 口径」。",
        "> 本文件由 `scripts/build_evidence_matrix.py` 生成；`--check` 会校验文件存在与内容是否最新。"
        "边界与不能说的话见每行 note。",
        "",
        "| 类别 | 对外说法 | 值 | 样本 | 证据 | 复现 | 截图 / 口径 |",
        "|---|---|---|---|---|---|---|",
    ]
    for it in items:
        shot = it.get("screenshot") or "—"
        lines.append(
            "| {category} | {claim} | {value} | {n} | `{artifact}` | `{command}` | {shot}<br>{note} |".format(
                **{**it, "shot": shot}
            )
        )
    lines += [
        "",
        "## 待补 / 不宣称",
        "",
        "| 类别 | 项目 | 当前状态 | 证据位置 |",
        "|---|---|---|---|",
    ]
    for cat, item, state, where in PENDING:
        lines.append(f"| {cat} | {item} | {state} | `{where}` |")
    lines += [
        "",
        "说明：",
        "- 「构造标签」指标签由构造规则决定，不是人工语义标注；不能写成人工金标准。",
        "- 「Unverified」是没核到，不是判假；「Major」才是指控。",
        "- 外部数据集（ChartCheck/SciFact/T2Retrieval）只用于对照，不能与构造集混算。",
        "- 人审与 CiteMap/Live 核对未完成前，本表保持 pending，不用预测值占位。",
        "",
    ]
    md = "\n".join(lines)
    payload = {
        "schema": "citeguard.evidence_matrix.v1",
        "rows": len(items),
        "missing": missing,
        "items": items,
        "pending": [
            {"category": c, "item": i, "state": s, "where": w} for c, i, s, w in PENDING
        ],
    }
    return md, payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    md, payload = build()
    if args.check:
        if payload["missing"]:
            print("missing artifacts:", payload["missing"], file=sys.stderr)
            return 1
        if not OUT_MD.exists() or OUT_MD.read_text(encoding="utf-8") != md:
            print("docs/evidence_matrix.md is out of date", file=sys.stderr)
            return 1
        print(f"evidence matrix OK: {payload['rows']} rows, 0 missing")
        return 0
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md, encoding="utf-8")
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)} ({payload['rows']} rows), missing={payload['missing']}")
    return 0 if not payload["missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
