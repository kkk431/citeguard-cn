# 对外数字 → 证据索引

> 规则：任何对外使用的数字，必须能在这里找到 **证据文件 / 复现命令 / 样本量 / 口径**。
> 截图统一放 `docs/evidence/shots/`，命名 `phase-序号-名称-版本.png`。

## 主结果

| 数字 | 证据 | 复现 | 样本量 / 口径 |
|---|---|---|---|
| CiteBench-CN macro-F1 **0.9684** / acc 0.968 | `data/citebench_cn/results.json` | `PYTHONPATH=src python scripts/eval_citebench.py` | 250 条，字段级构造基准 |
| ClaimSupport-CN（原 100 条）**0.9597** / 0.95 | `data/claimsupport_cn/results.json` | `PYTHONPATH=src python scripts/eval_support_local.py` | 100 条，构造标签 |
| ClaimSupport-CN 300 条 **0.9841** / 0.9833 | `data/experiments/release300.json` | 见 `docs/experiments.md` | 300 条合并集，审计 v3；与 100/60/140 分批评测不可混用 |
| 置信度校准 300 条 ECE **0.0400**；弃权 0.9 覆盖 96.67%、准确 98.97% | `data/experiments/support_calibration.json`、`docs/calibration.md` | `PYTHONPATH=src python scripts/eval_support_calibration.py` | 构造标签；judge 自报置信度 |
| 真实文献 **409 条，Major 0** | `data/experiments/verify_real.json` | `PYTHONPATH=src python scripts/eval_verify_real.py` | 22 篇已发表论文的 409 条参考文献 |
| 本地库 definite **409/412（99.27%）** | `data/experiments/library_real.json` | `PYTHONPATH=src python scripts/eval_library_real.py` | 建库后 412 条；10 条字段偏差 |
| 解析 **529 条 / clean 1.0** | `data/experiments/parse_real.json` | `PYTHONPATH=src python scripts/eval_parse_real.py` | 22 篇，标题行/题名覆盖率 |
| 盲测 5：Qwen3 **73 条/100%**、R1 **92 条/96.7%**、Mixtral **35 条/100%** | `data/experiments/blind_test5.json`、`blind_test5_protocol.json` | 见 `docs/blind_test_results.md` §14 | 预注册协议，健康率启发式，不是语义正确率 |
| LoRA（Qwen3-1.7B）test **0.9721 / 0.9667** | `data/experiments/support_lora_qwen3_1.7b.json` | `PYTHONPATH=src python scripts/eval_support_adapter.py` | test 60 条；基座零样本 0.4935/0.4833 |
| 图表 ChartCheck 400 零样本 **0.7628**（三分类 0.695） | `data/experiments/chartcheck_val400_v3.json` | 见 `docs/experiments.md` | 400 条英文图表结论 |
| 图表真实论文（8B）n=10 **acc 1.0**（小样本） | `data/experiments/figure_real26_8b_v3.json` | `PYTHONPATH=src python scripts/eval_figure_prompt.py` | 仅 10 条，只能作小样本复测 |
| 扫描件 OCR **23/24 条** | `data/experiments/ocr_scan_real.json` | `PYTHONPATH=src python scripts/eval_ocr_scanned.py --input <pdf>` | 7 页扫描 PDF，题名/年份/作者 23/23 |
| GB/T E4 严格控制漂移 **29/30** | `data/experiments/e4_format.json` | `PYTHONPATH=src python scripts/e4_format_check.py` | 30 个构造样本 |
| 万方中文强命中 **111/184** | `data/experiments/wanfang_batch.json` | 见 `docs/chinese_sources.md` | 184 条中文题录，试用配额；非全样本 |
| 测试 **569 passed** | `pytest -q` | `PYTHONPATH=src python -m pytest tests -q` | 本地 Python 3.13 |
| 交付自检 **137/137** | `scripts/verify_artifacts.py` | `PYTHONPATH=src python scripts/verify_artifacts.py` | 版本/路由/文档/数字一致性 |
| 知网导入 **22 → 27 条，Exact** | `data/library/cnki_demo.enw`、`data/library/library.json` | `PYTHONPATH=src python -m citeguard.cli --import-library data/library/cnki_demo.enw` | 5 条机构导出题录 |

## 截图登记

| 截图 | 内容 | 数据来源 |
|---|---|---|
| `phase0-plan.png`（待补） | 本清单/许可证整改 | `docs/plan_national.md` |
| `phase1-01-report-charts-v0.9.85.png` | 报告总览三张真图：核验结论分布 / 支持度四档 / GB/T 问题 Top 字段（CSS 条形图 + 表格视图） | 任务 `4e5b9681ea00` 的 `report.json`（15 条真实文献） |
| `phase1-model-compare.png`（待补） | 模型对比（1.7B/8B/14B/4bit/API） | `data/experiments/support_local_*.json` |
| `phase2-diff.png`（待补） | 复检 diff | 任务前后两份 report.json |
| `phase3-1000refs.png`（待补） | 1000 条压测 | `docs/performance.md` |

## 不能这么说（边界）

- “替代人工核验 / 超过人工 / SOTA”——没有对照实验，禁用。
- “人工标注 300 条”——标签由构造规则决定，只有 20% 规则复核，无双人标注/κ。
- “真实用户测试”——未开展外部真人测试，不能写。
- “ChartCheck 0.76 是论文级准确率”——零样本、英文、非中文期刊图表，只能说“公开基准零样本结果”。

| phase-09-diff-ui-0.9.89.png | 报告页“对比历史报告”面板：字段级 diff、状态迁移、已解决/仍存在/新增 | `docs/evidence/shots/phase-09-diff-ui-0.9.89.png` | 2026-11-11 |
| phase-10-batch-ui-0.9.90.png | 批量核验页 `/batch`：3 条示例、逐条判定、置信度、理由、CSV 下载 | `docs/evidence/shots/phase-10-batch-ui-0.9.90.png` | 2026-11-11 |
| E22 | 批注 PDF（7 条问题标到原文页） | `docs/evidence/shots/phase-11-annotated-pdf-0.9.91.png`；脚本 `python -m pytest tests/test_annotate.py -q`（8 passed）；接口 `GET /api/report/{job_id}/annotated` 头 `x-annotated: 7`、`x-unmapped: 0` | 真实中文论文 hanspub_152575.pdf，14 条引用中 7 条可定位 |
| E23 | 批量报告打包（多任务 ZIP + 合并 RIS/ENW） | `docs/evidence/shots/phase-12-batch-reports-0.9.91.png`；`GET /api/reports/zip?ids=cf6d160d6fd7,135fc226f7de` 实测 18 个文件、含 `all.ris`；`python -m pytest tests/test_annotate.py -q`（5 passed） | 两份真实报告；最多 20 份/次 |

| E24 | 题录库外部检索补库（Attention 6 条，TOP1 2017/136007 引用） | phase-13-library-suggest-0.9.91.png | 0.9.91 | 2026-11-11 |

| E25 | 图注修改建议（规则版，supported 不给建议） | 单元测试 tests/test_figure_advice.py；截图待视觉服务在线时补 | 0.9.94 | 2026-11-11 |

| E26 | 第六次预注册盲测（Llama3 187/99.47%、Phi-3 71/97.18%、Qwen2 79/100%） | data/experiments/blind_test6.json + docs/blind_test_results.md §15 | 41a18d7 | 2026-11-11 |
| E27 | 判定模型设置页（hosted / 14B bf16 / 4bit / LoRA，切换前实测连通性） | docs/evidence/shots/phase-16-model-registry-0.9.95.png | 0.9.95 | 2026-11-11 |
| E28 | 1000 条引用离线压测：解析 0.118 s / 冷 0.718 s / 热 0.159 s / 双并发 0.329 s / 峰值 5.2 MB | data/experiments/stress_1000.json；命令见 docs/performance.md | 0.9.96 | 2026-11-11 |

| E29 | 中文标题繁简归一 | 206 条真实中文题名；繁体标题检出率 0.0% → 1.0%，平均相似度 0.6191 → 1.0 | `data/experiments/title_norm_cn.json`；`PYTHONPATH=src python scripts/eval_title_norm.py` | optional OpenCC；只改进匹配层，不改变题录来源 |

| E30 | 版面回退去 PyMuPDF | 三篇盲测 PDF 条目数 pypdfium2 与旧 PyMuPDF 完全一致（73/92/27） | `data/experiments/refs_layout_pdfium_parity.json`；`python -c "..."` 对比脚本 | 只测条目数，不测语义；现有解析回归 529/clean 1.0 另行保证 |

| E31 | OCR 后端对照 | 单页 200dpi+轻噪声；RapidOCR 10.3s / CER 0.1825，PaddleOCR 109.3s / CER 0.1530；GROBID 拉取失败（read-only fs）与公共端点不可达，未评测 | `data/experiments/ocr_backends_eval.json`；`PYTHONPATH=src python scripts/eval_ocr_backends.py` | 单页单篇、数字 PDF 渲染；PaddleOCR 仅评测不入依赖 |

- E32 发布清单：v1.0.0 tag、CHANGELOG、mkdocs 严格构建通过（`site/index.html`）、数据集发布包 sha256 见 MANIFEST。
- E33 v1.0 发布物料：`dist/CiteGuard-CN_LoRA-Qwen3-1.7B_v1.0.zip`（含 MANIFEST sha256）、`docker/docker-compose.yml`、文档站构建 `site/`。
- E34 键盘导航与无障碍：`docs/evidence/shots/phase-24-keyboard-nav-1.0.0.png`（j 键移动焦点，`.ref.kb-active` 可见）；报告 verdict 加 `aria-live`；589 tests。

| E35 | 浅色主题 WCAG AA 对比度 | 1.0.1 | `data/experiments/contrast_report.json` | `PYTHONPATH=src python scripts/check_contrast.py` | 20 组配色全部通过 |

| E36 | 前端键盘/可访问性审计 | 1.0.2 | `data/experiments/frontend_audit.json` + `docs/evidence/shots/phase-26-keyboard-a11y-1.0.2.png` | `PYTHONPATH=src python scripts/audit_frontend.py` | 8 项全过 |
| E37 | 正文引注列表（报告总览） | 1.0.3 | `docs/evidence/shots/phase-27-citation-list-1.0.3.png` | `pytest tests/test_web.py -q` | 真实任务 18 处引注 / 覆盖 18 句，前 6 条渲染 |
| E38 | 正文引注 → 条目跳转 | 1.0.4 | `docs/evidence/shots/phase-28-citation-jump-1.0.4.png` | Playwright 点击 `.cite-jump` 后断言 `aria-selected=true`、抽屉 `open` 且序号为 [1] | 真实任务 18 处引注可跳转 |
| E39 | 正文引注覆盖率 | 1.0.5 | `docs/evidence/shots/phase-29-citation-coverage-1.0.5.png` + `tests/test_citation_anchor.py::test_coverage_counts_only_cited_numbers` | `pytest tests/test_citation_anchor.py -q` | 真实任务 15/15 条被引用，0 条未被引用 |
| E40 | 可选向量接口层（BGE-M3 / OpenAI 兼容） | 1.0.6 | `tests/test_embeddings.py`（6 例，本地假服务）+ `docs/embeddings.md` | `pytest tests/test_embeddings.py -q` | 接口/错误/重排全过；真实 BGE-M3 未部署，无召回数字 |
| E41 | 正文引注抽取真实语料评测 | 1.0.7 | `data/experiments/citation_anchor_real.json` + `citation_anchor_sample.csv` + `docs/citation_eval.md` | `PYTHONPATH=src python scripts/eval_citation_anchor.py` | 22 篇 / 529 条：21 篇有引注（95.5%）、参考文献被引 318 条（60.1%）、自洽 486/543（89.5%） |
