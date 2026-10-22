# 引证卫士 CiteGuard-CN

> 给中文论文做一次「引文体检」：**引文是否真实存在、引用是否支持正文那句话、格式是否符合 GB/T 7714-2025**。每条结论都带证据链接。

CiteGuard-CN 是一个开源的中文引文核验工作台，面向毕业论文、课程论文与期刊投稿场景。它把「中文引文解析 → 多源元数据核验 → 引用支持度判定 → 新国标规则检查」串成一条可复现的流水线，并附带一个 250 条的中文评测基准 **CiteBench-CN**。

## 它做什么

| 检查 | 做法 | 输出 |
|---|---|---|
| **引文真实性** | 解析 DOI / 题名，查 OpenAlex → Crossref → arXiv；DOI 404 视为虚构，DOI 命中但题名对不上视为张冠李戴 | `Exact` / `Minor` / `Major` + 证据链接 |
| **引用支持度** | 抽取正文引用句 + 被引论文摘要，交给可选的 LLM judge | `支持` / `部分支持` / `矛盾` / `无证据` / `未检测` |
| **新国标格式** | 按 GB/T 7714-2025 的 14 类文献类型检查字段、作者名、永久标识符 | 逐条「缺什么 / 错在哪 / 怎么改」 |

## 实测结果

在自建 CiteBench-CN（250 条：100 真实 / 75 元数据扰动 / 75 虚构或错配）上：

| 系统 | Macro-F1 | Accuracy |
|---|---|---|
| **CiteGuard v1.1** | **0.9684** | **0.968** |
| DeepSeek zero-shot（prompt v3 冻结） | 0.5159 | 0.536 |

```
混淆矩阵（行=真实，列=预测）
        Exact  Minor  Major
Exact  [ 100,     0,     0 ]
Minor  [   8,    67,     0 ]
Major  [   0,     0,    75 ]

消融
full              0.9684
- DOI anchor      0.8071  (Δ -0.1613)
- title search    0.7744  (Δ -0.1940)
```

> 评测集、数据卡、评测脚本与 DeepSeek 基线都在 `data/citebench_cn/` 与 `scripts/` 下；`seed=20261022`，重建字节级一致（SHA-256 `1a8e466b…`）。

## 架构

```
输入 PDF/TXT
  → ① 中文引文解析器（自研）：正文夹注 ↔ 文后参考文献表对齐
  → ② 多源元数据核验（自研编排）：OpenAlex(CC0) → Crossref → arXiv(CC0)
  → ③ 引用支持度判定（自研 + 可选 LLM judge）：claim 抽取 → 摘要证据 → 四分类
  → ④ GB/T 7714-2025 规则引擎（自研）：14 类文献类型字段检查
  → ⑤ 证据报告（Web / HTML / Markdown / JSON）
```

## 快速开始

```bash
python3 -m pip install -r requirements.txt

# CLI：分析一篇论文
PYTHONPATH=src python3 -m citeguard.cli --input web/static/samples/sample_paper.txt --out out/demo

# Web 工作台
PYTHONPATH=src python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000

# 评测 CiteBench-CN
PYTHONPATH=src python3 scripts/evaluate_citebench.py --limit 0 --out data/citebench_cn/results.json
```

服务器环境（无 venv 时依赖装在 `.pylibs`）：

```bash
PYTHONPATH=src:.pylibs python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000
PYTHONPATH=src:.pylibs python3 scripts/evaluate_citebench.py --limit 0
```

### 引用支持度（可选）

支持度判定需要一个 LLM judge。默认读环境变量 `DEEPSEEK_API_KEY`；没有 key 时自动降级为「未检测」，不影响真实性/格式核验。

```bash
export DEEPSEEK_API_KEY=...   # 只在本地/服务器环境中设置，不要提交
PYTHONPATH=src python3 -m uvicorn web.app:app --port 8000
```

## 目录

```
citeguard/
├── src/citeguard/        # 核心包：解析 / 核验 / 规则 / 支持度 / 报告
├── web/                  # FastAPI + Jinja2 工作台（4 个页面）
├── scripts/              # 评测、基线、样例、复现、自检
├── data/citebench_cn/    # CiteBench-CN 数据集、结果、数据卡
├── docs/                 # 评测规划、PPT 一页纸
├── requirements.txt
├── reproduce.sh
├── LICENSE               # Apache-2.0
├── NOTICE
└── THIRD_PARTY_NOTICES.md
```

## 数据与许可证

| 资源 | 用途 | 许可证 |
|---|---|---|
| 本项目代码 | — | Apache-2.0 |
| CiteBench-CN | 中文引文核验评测集 | CC-BY-4.0 |
| OpenAlex | 文献元数据 | CC0 1.0 |
| arXiv 元数据 | 预印本元数据 | CC0 1.0 |
| Crossref | DOI 元数据 | 元数据开放；摘要版权归出版商 |
| Qwen3-8B / Qwen3-Embedding / Reranker | 主模型 / 检索 | Apache-2.0 |
| bge-m3 | 多语嵌入 | MIT |
| PaddleOCR / Docling | OCR / PDF 解析 | Apache-2.0 / MIT |

完整清单见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

> 不使用知网 / 万方全文；不 re-host NC/ND 数据；CiteBench-CN 只包含自建标注与公开元数据 ID，不含第三方全文或摘要。

## 已知局限

- 中文文献在 OpenAlex / Crossref 的摘要覆盖有限，部分条目支持度会显示「未检测」。
- 作者顺序、机构作者、拼音/中文别名会造成少量误判。
- 支持度判定为辅助提示，不构成学术结论。
- GB/T 7714-2025 规则引擎基于公开规则事实编码，未复制标准原文；请以国家标准原文与人工复核为准。

## 参考与致谢

- OpenAlex（CC0）、Crossref、arXiv 提供开放元数据。
- 方法对标：OpenScholar（Nature 2025）、RefChecker（MIT）、CiteCheck、DeepSciVerify、CNCV、PaperQA2、LitSearch。
- Qwen3 技术报告（arXiv:2505.09388）。
