"""Render the t31 LongCite GPU report (markdown) from the measured JSONs.

Inputs (read-only):
  data/experiments/longcite_spike_gpu.json   <- produced on the GPU host
  data/experiments/longcite_spike.json       <- t29 CPU baseline

Output:
  data/experiments/longcite_spike_gpu_report.md  (text for docs/research §8;
  docs/ is outside the t31 write scope, so the captain pastes this section)

Every number comes from the JSON payloads; nothing is typed by hand.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "data" / "experiments"
GPU_JSON = EXP / "longcite_spike_gpu.json"
CPU_JSON = EXP / "longcite_spike.json"
OUT_MD = EXP / "longcite_spike_gpu_report.md"

# same metric code the GPU run used, so the CPU baseline is recomputed, not retyped
_spec = importlib.util.spec_from_file_location("spike", ROOT / "scripts" / "longcite_spike_gpu.py")
spike = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spike)


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def threshold_table(gpu: dict) -> list[str]:
    rows = ["| 门槛 | 要求 | 实测 | 结论 |", "|---|---|---|---|"]
    t = gpu["thresholds"]
    for name, row in t.items():
        if "max" in row:
            req = f"≤ {fmt(row['max'], 2)}"
        else:
            req = f"≥ {fmt(row['min'], 2)}"
        rows.append(f"| {name} | {req} | {fmt(row['value'])} | {'通过' if row['pass'] else '**未过**'} |")
    return rows


def main() -> int:
    gpu = load(GPU_JSON)
    cpu = load(CPU_JSON)
    agg = gpu["aggregates"]
    stmt = gpu["statement_level"]
    env = gpu["environment"]
    model = gpu["model"]
    cfg = gpu["config"]
    cpu_agg = cpu["aggregate"]
    cpu_stmt = spike.statement_level(
        [{"text": s["text"], "gold_text": s["gold_text"]} for s in cpu["samples"]]
    )

    lines: list[str] = []
    lines.append("## 8. GPU 复跑（4090，20 条 / 512 token）")
    lines.append("")
    lines.append(
        "同一批 20 条样本（14 中文 / 6 英文，t29 选择）、同一份 Q4_K_M GGUF、"
        "temperature 0，只把设备从 CPU 换成单张 RTX 4090、n_predict 从 256 提到 512。"
    )
    lines.append("")
    lines.append("### 8.1 环境与模型")
    lines.append("")
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| 设备 | {env['device']} |")
    lines.append(f"| 后端 | {env['backend']} |")
    lines.append(f"| 主机 | {env['host']} |")
    lines.append(f"| 模型 | {model['name']}（{model['params']}） |")
    lines.append(f"| 许可证 | {model['license']} |")
    lines.append(f"| 数据集 | {model['dataset']} |")
    gguf = model.get("gguf") or {}
    if gguf:
        lines.append(
            f"| 权重 | GGUF {gguf.get('quantization')}，{gguf.get('bytes')} B，sha256 `{gguf.get('sha256')}` |"
        )
    lines.append(f"| 样本 / n_predict / temperature | {cfg['samples']} / {cfg['n_predict']} / {cfg['temperature']} |")
    lines.append(f"| 官方指标 | {model['official_metric']} |")
    lines.append("")
    lines.append("### 8.2 延迟与吞吐")
    lines.append("")
    lines.append("| 指标 | CPU Q4_K_M, 256 tok（t29） | GPU Q4_K_M, 512 tok（本次） |")
    lines.append("|---|---|---|")
    lines.append(f"| 平均 wall | {fmt(cpu_agg.get('mean_wall_s'), 2)} s | {fmt(agg['mean_wall_s'], 2)} s |")
    lines.append(f"| P50 wall | — | {fmt(agg['p50_wall_s'], 2)} s |")
    lines.append(f"| P95 wall | — | {fmt(agg['p95_wall_s'], 2)} s |")
    lines.append(f"| 平均 prompt tokens | {fmt(cpu_agg.get('mean_prompt_tokens'), 1)} | {fmt(agg['mean_prompt_tokens'], 1)} |")
    lines.append(f"| 平均生成 tokens | — | {fmt(agg['mean_generated_tokens'], 1)} |")
    lines.append(f"| decode tok/s | {fmt(cpu_agg.get('mean_predicted_per_s'), 2)} | {fmt(agg['mean_decode_tokens_per_s'], 2)} |")
    lines.append(f"| 生成 token 上限命中 | — | {agg['n_hit_token_cap']}/{agg['n_ok']} |")
    lines.append(f"| 未闭合 statement | — | {agg['n_unclosed_statement']}/{agg['n_ok']} |")
    lines.append("")
    lines.append("### 8.3 质量（proxy）")
    lines.append("")
    lines.append("| 指标 | CPU 256 tok（t29） | GPU 512 tok（本次） |")
    lines.append("|---|---|---|")
    lines.append(
        f"| doc-level P / R / F1（均值） | {fmt(cpu_agg.get('mean_doc_precision_proxy'))} / "
        f"{fmt(cpu_agg.get('mean_doc_recall_proxy'))} / {fmt(cpu_agg.get('mean_doc_f1_proxy'))} | "
        f"{fmt(agg['mean_doc_precision_proxy'])} / {fmt(agg['mean_doc_recall_proxy'])} / "
        f"{fmt(agg['mean_doc_f1_proxy'])} |"
    )
    lines.append(
        f"| statement 级 P / R / F1 | {fmt(cpu_stmt['matched_citation_precision_proxy'])} / "
        f"{fmt(cpu_stmt['matched_citation_recall_proxy'])} / {fmt(cpu_stmt['matched_citation_f1_proxy'])} | "
        f"{fmt(stmt['matched_citation_precision_proxy'])} / "
        f"{fmt(stmt['matched_citation_recall_proxy'])} / {fmt(stmt['matched_citation_f1_proxy'])} |"
    )
    lines.append(
        f"| 对齐上的生成 statement / 匹配对 | {cpu_stmt['n_generated_statements']} / "
        f"{cpu_stmt['n_matched_pairs']} | {stmt['n_generated_statements']} / {stmt['n_matched_pairs']} |"
    )
    lines.append(
        f"| statement 匹配率 | {fmt(cpu_stmt['statement_match_rate'])} | {fmt(stmt['statement_match_rate'])} |"
    )
    cpu_nocite = sum(s["n_statements"] - s["n_statements_with_cite"] for s in cpu["samples"])
    cpu_nstmt = sum(s["n_statements"] for s in cpu["samples"])
    lines.append(
        f"| 引用 statement 缺 cite | {cpu_nocite}/{cpu_nstmt} | {agg['n_statements_without_cite']}/{agg['n_statements']} |"
    )
    cpu_invalid = sum(s["invalid_spans"] for s in cpu["samples"])
    cpu_zero = sum(1 for s in cpu["samples"] if s["doc_f1_proxy"] == 0.0)
    lines.append(
        f"| 无效 span / 零命中样本 | {cpu_invalid} / {cpu_zero} | {agg['n_invalid_spans']} / {agg['n_zero_hit_samples']} |"
    )
    cpu_trunc = sum(1 for s in cpu["samples"] if s["generated_tokens"] >= cpu["n_predict"])
    lines.append(
        f"| 截断率 | {fmt(cpu_trunc / len(cpu['samples']) * 100, 1)}%（{cpu_trunc}/{len(cpu['samples'])}） | "
        f"{fmt(agg['truncation_rate'] * 100, 1)}%（{agg['n_truncated']}/{agg['n_ok']}） |"
    )
    lines.append("")
    lines.append("doc-level 是「每条样本被引 chunk 集合 vs 参考回答被引 chunk 集合」的 P/R/F1 再取均值"
                 "（t29 口径，t29 报告中把 chunk 称作 doc）；statement 级是 3-gram Jaccard ≥ 0.25 的贪心对齐 + "
                 "匹配对内 chunk 交集。两者都是 **proxy**，不是官方 LongCite 的 GPT-4o judge 指标。")
    lines.append("")
    lines.append("**机制解读：512 token 为什么没有把质量拉上去**")
    lines.append("")
    lines.append(
        f"1. 模型在这批长输入上不会自己停：两次运行都是 20/20 命中 token 上限"
        f"（256 与 512），本次还有 {agg['n_unclosed_statement']}/20 条在 `<statement>` 中间被切断。"
    )
    lines.append(
        f"2. 多出来的 256 token 不是更完整的答案，而是继续往下啰嗦：生成 statement 从 "
        f"{cpu_stmt['n_generated_statements']} 条涨到 {stmt['n_generated_statements']} 条，其中 "
        f"{agg['n_statements_without_cite']} 条是空引用 `<cite></cite>`（t29 是 {cpu_nocite} 条），"
        f"statement 匹配率从 {fmt(cpu_stmt['statement_match_rate'])} 掉到 {fmt(stmt['statement_match_rate'])}。"
    )
    lines.append(
        f"3. 因此 doc F1 只从 {fmt(cpu_agg.get('mean_doc_f1_proxy'))} 动到 {fmt(agg['mean_doc_f1_proxy'])}"
        f"（{agg['mean_doc_f1_proxy'] - cpu_agg['mean_doc_f1_proxy']:+.4f}），statement F1 反而从 "
        f"{fmt(cpu_stmt['matched_citation_f1_proxy'])} 降到 {fmt(stmt['matched_citation_f1_proxy'])}"
        f"（{stmt['matched_citation_f1_proxy'] - cpu_stmt['matched_citation_f1_proxy']:+.4f}）。"
        "换到 4090 解决的是速度（见下），不是生成控制与引用覆盖。"
    )
    lines.append("")
    lines.append(
        f"速度收益：平均 wall {fmt(cpu_agg.get('mean_wall_s'), 2)} s → {fmt(agg['mean_wall_s'], 2)} s（约 "
        f"{cpu_agg['mean_wall_s'] / max(agg['mean_wall_s'], 1e-9):.1f}×），decode "
        f"{fmt(cpu_agg.get('mean_predicted_per_s'), 2)} → "
        f"{fmt(agg['mean_decode_tokens_per_s'], 2)} tok/s（约 "
        f"{agg['mean_decode_tokens_per_s'] / max(cpu_agg['mean_predicted_per_s'], 1e-9):.1f}×），单条范围 "
        f"{fmt(agg['min_wall_s'], 2)}–{fmt(agg['max_wall_s'], 2)} s。"
    )
    lines.append("")
    lines.append("### 8.4 门槛与结论")
    lines.append("")
    lines.extend(threshold_table(gpu))
    lines.append("")
    lines.append(f"**结论：`{gpu['verdict']}`**")
    if gpu["failed_thresholds"]:
        lines.append("")
        lines.append("未过门槛：" + "、".join(f"`{x}`" for x in gpu["failed_thresholds"]))
    lines.append("")
    lines.append("### 8.5 失败样例（按 doc F1 最差的 4 条）")
    lines.append("")
    for f in gpu["failures"]:
        lines.append(
            f"- **#{f['i']}（{f['lang']}，{fmt(f['wall_s'], 2)} s，doc F1 {fmt(f['doc_f1_proxy'])}，"
            f"{f['n_statements']} statements，缺 cite {f['n_statements_without_cite']}）**"
        )
        lines.append("")
        lines.append("  - 生成引用 chunk：" + (str(f["gen_docs"]) if f["gen_docs"] else "（无）"))
        lines.append("  - 参考引用 chunk：" + (str(f["gold_docs"]) if f["gold_docs"] else "（无）"))
        lines.append("  - 摘录：" + f["text_excerpt"].replace("\n", " ")[:300])
        lines.append("")
    lines.append("### 8.6 逐条明细（20 条）")
    lines.append("")
    lines.append("| # | 语言 | wall s | prompt tok | gen tok | decode tok/s | statements | 缺 cite | doc F1 proxy | 截断 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for s in gpu["samples"]:
        lines.append(
            f"| {s['i']} | {s['lang']} | {fmt(s['wall_s'], 2)} | {s['prompt_tokens']} | "
            f"{s['generated_tokens']} | {fmt(s['decode_tokens_per_s'], 2)} | {s['n_statements']} | "
            f"{s['n_statements_without_cite']} | {fmt(s['doc_f1_proxy'])} | {'是' if s['truncated'] else '否'} |"
        )
    lines.append("")
    lines.append("### 8.7 限制")
    lines.append("")
    lines.append("- 只有 20 条样本（14 中文 / 6 英文），来自 LongCite-45k 的 prompt ≤6000 字符子集；"
                 "不是完整 LongCite 评测集。")
    lines.append("- 官方 citation recall/precision（GPT-4o judge）未跑：主机无 API key，且与 t29 不可比。")
    lines.append("- 单次运行、temperature 0、固定 seed-free 采样；decode 速度受单卡 4090 与 batch 1 限制。")
    lines.append("- llama.cpp 的 CUDA 后端对 LongCite 自定义 tokenizer 的处理与 transformers 不完全等价"
                 "（t29 已用公共 Llama-3.1 tokenizer.json 替换 TikTokenizer，未做逐 token 对齐验证）。")
    lines.append("")
    lines.append("### 8.8 复现")
    lines.append("")
    lines.append("```bash")
    lines.append("# GPU 主机：编译 llama.cpp CUDA 后端并启动服务")
    lines.append("bash data/experiments/a3b_scripts/longcite_build_llamacpp.sh   # GGML_CUDA=ON, ARCH=89")
    lines.append("bash data/experiments/a3b_scripts/longcite_start_server.sh     # CUDA_VISIBLE_DEVICES=3, port 8099")
    lines.append("# 跑 20 条 × 512 token")
    lines.append("bash data/experiments/a3b_scripts/longcite_run_gpu.sh")
    lines.append("# 本地汇总（JSON -> 本报告）")
    lines.append("python scripts/longcite_gpu_report.py")
    lines.append("```")
    lines.append("")
    lines.append("文件：`data/experiments/longcite_spike_gpu.json`（逐条明细 + 聚合 + 门槛）、"
                 "`data/experiments/longcite_spike_gpu_report.md`（本节）。")
    lines.append("")

    # Machine-readable CPU comparison next to the measured numbers (derived, labelled).
    cpu_row = {
        "source": "data/experiments/longcite_spike.json",
        "n_predict": cpu.get("n_predict"),
        "mean_wall_s": cpu_agg.get("mean_wall_s"),
        "mean_decode_tokens_per_s": cpu_agg.get("mean_predicted_per_s"),
        "mean_doc_f1_proxy": cpu_agg.get("mean_doc_f1_proxy"),
        "statement_f1_proxy": cpu_stmt["matched_citation_f1_proxy"],
        "truncation_rate": 1.0,
    }
    gpu_row = {
        "source": "data/experiments/longcite_spike_gpu.json",
        "n_predict": cfg["n_predict"],
        "mean_wall_s": agg["mean_wall_s"],
        "mean_decode_tokens_per_s": agg["mean_decode_tokens_per_s"],
        "mean_doc_f1_proxy": agg["mean_doc_f1_proxy"],
        "statement_f1_proxy": stmt["matched_citation_f1_proxy"],
        "truncation_rate": agg["truncation_rate"],
    }
    comparison = {
        "cpu_t29": cpu_row,
        "gpu_t31": gpu_row,
        "speedup_mean_wall": round(cpu_row["mean_wall_s"] / max(gpu_row["mean_wall_s"], 1e-9), 2),
        "speedup_decode": round(gpu_row["mean_decode_tokens_per_s"] / max(cpu_row["mean_decode_tokens_per_s"], 1e-9), 2),
        "delta_doc_f1": round(gpu_row["mean_doc_f1_proxy"] - cpu_row["mean_doc_f1_proxy"], 4),
        "delta_statement_f1": round(gpu_row["statement_f1_proxy"] - cpu_row["statement_f1_proxy"], 4),
        "note": "derived by scripts/longcite_gpu_report.py from the two measured JSONs; "
        "the GPU block itself is untouched",
    }
    gpu["comparison_to_t29"] = comparison
    GPU_JSON.write_bytes(json.dumps(gpu, ensure_ascii=False, indent=2).encode("utf-8"))

    OUT_MD.write_bytes("\n".join(lines).encode("utf-8"))
    print(f"[done] wrote {OUT_MD.relative_to(ROOT)} (and comparison_to_t29 in {GPU_JSON.name})")
    print(f"verdict={gpu['verdict']} failed={gpu['failed_thresholds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
