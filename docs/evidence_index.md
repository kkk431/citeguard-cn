# 对外数字 → 证据索引

> 规则：任何对外使用的数字，必须能在这里找到 **证据文件 / 复现命令 / 样本量 / 口径**。
> 1.7.x 及之后的对外数字以 `docs/evidence_matrix.md`（脚本生成）为准；本页保留历史明细。
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
| 盲测 5：Qwen3 **73 条/100%**、R1 **92 条/96.7%**、Mixtral **35 条/100%** | `data/experiments/blind_test5.json`、`data/experiments/blind_test5_protocol.json` | 见 `docs/blind_test_results.md` §14 | 预注册协议，健康率启发式，不是语义正确率 |
| LoRA（Qwen3-1.7B）test **0.9721 / 0.9667** | `data/experiments/support_lora_qwen3_1.7b.json` | `PYTHONPATH=src python scripts/eval_support_adapter.py` | test 60 条；基座零样本 0.4935/0.4833 |
| 图表 ChartCheck 400 零样本 **0.7628**（三分类 0.695） | `data/experiments/chartcheck_val400_v3.json` | 见 `docs/experiments.md` | 400 条英文图表结论 |
| 图表真实论文（8B）n=10 **acc 1.0**（小样本） | `data/experiments/figure_real26_8b_v3.json` | `PYTHONPATH=src python scripts/eval_figure_prompt.py` | 仅 10 条，只能作小样本复测 |
| 扫描件 OCR **23/24 条** | `data/experiments/ocr_scan_real.json` | `PYTHONPATH=src python scripts/eval_ocr_scanned.py --input <pdf>` | 7 页扫描 PDF，题名/年份/作者 23/23 |
| GB/T E4 严格控制漂移 **29/30** | `data/experiments/e4_format.json` | `PYTHONPATH=src python scripts/e4_format_check.py` | 30 个构造样本 |
| 万方中文强命中 **111/184** | `data/experiments/wanfang_batch.json` | 见 `docs/chinese_sources.md` | 184 条中文题录，试用配额；非全样本 |
| 测试 **808 passed** | `pytest -q` | `PYTHONPATH=src python -m pytest tests -q` | 本地 Python 3.13 |
| 交付自检 **137/137** | `scripts/verify_artifacts.py` | `PYTHONPATH=src python scripts/verify_artifacts.py` | 版本/路由/文档/数字一致性 |
| 知网导入 **22 → 27 条，Exact** | `data/library/cnki_demo.enw`、`data/library/library.json` | `PYTHONPATH=src python -m citeguard.cli --import-library data/library/cnki_demo.enw` | 5 条机构导出题录 |

## 截图登记

| 截图 | 内容 | 数据来源 |
|---|---|---|
| E69 | 信息架构改版（1.4.0） | `web/templates/base.html`、`index.html`、`history.html`、`report.html`；`web/static/css/refresh.css`；`tests/test_web.py`、`tests/conftest.py`、`tests/test_history_db.py` | 左侧导航改为「核验 / 工具 / 更多」三段，桌面端默认展开显示文字；首页上传卡进入 hero 右栏；报告页先结论与健康画像，检查明细默认折叠；历史页统一选择框、时间可读；测试不再写真实 history DB 且索引会剪除缺失 JSON 行；`pytest` 664 passed | `docs/evidence/shots/phase-41-home-ia-1.4.0.png`、`docs/evidence/shots/phase-41-history-ia-1.4.0.png`、`docs/evidence/shots/phase-41-report-ia-1.4.0.png`、`docs/evidence/shots/phase-41-report-ia-1440-1.4.0.png` |
| E68 | Docker 1.3.4 镜像（1.3.4） | `docker/Dockerfile`；`docs/deployment.md`；`docs/status_v1.3.4.md` | `citeguard-cn:1.3.4` 493 MB；容器 `-p 18082:8000 -e CITEGUARD_OFFLINE=1` health `{"ok":true,"version":"1.3.4","offline":true}`；启动时曾遇 WSL vpnkit 超时，`wsl --terminate docker-desktop` + 重启 Docker Desktop 后恢复 | `docs/evidence/logs/docker-1.3.4-health.txt` |
| E67 | OpenAPI 契约（1.3.4） | `tests/test_openapi.py`；`web/app.py` 的 `openapi_extra` | 13 个公开路径均在 schema；`info.version == app.version`；`/api/support/check`、`/api/support/batch` 公开 JSON requestBody（运行时仍返回 400，未改行为）；3 个测试 + test_web 52 passed | 无界面截图，测试即证据 |
| E66 | 截图自动化（1.3.4） | `scripts/capture_evidence.py`；`docs/evidence/shots/README.md` | Playwright 1920×1080；11 个页面 + `--job` 报告页，实测 12/12 OK；控制台报错或加载失败非零退出；输出目录已 gitignore，入库证据仍按 phase-* 命名 | 输出 `docs/evidence/shots/captured/`（不入库） |
| `docs/evidence/shots/phase-0-plan-1.0.12.png` | 30 天规划页（mkdocs 渲染）：Phase 0 合规、Phase 1–4 与 DoD | `docs/plan_national.md` |
| `docs/evidence/shots/phase1-01-report-charts-v0.9.85.png` | 报告总览三张真图：核验结论分布 / 支持度四档 / GB/T 问题 Top 字段（CSS 条形图 + 表格视图） | 任务 `4e5b9681ea00` 的 `report.json`（15 条真实文献） |
| `docs/evidence/shots/phase-1-model-compare-1.0.12.png` | 同一 100 条构造集：14B bf16 / 14B 4bit / 8B bf16 / 8B 4bit 的 macro-F1（另：1.7B LoRA test60 0.9721，口径不同不混画） | `data/experiments/support_local_qwen3_14b_v10_all.json`、`data/experiments/support_local_qwen3_14b_4bit_all.json`、`data/experiments/support_local_qwen3_8b_product_all.json`、`data/experiments/support_local_qwen3_8b_4bit_v10_all.json` |
| `docs/evidence/shots/phase-09-diff-ui-0.9.89.png` | 复检 diff 界面：已解决/仍存在/新增 | 任务前后两份 report.json |
| `docs/evidence/shots/phase-3-stress1000-1.0.12.png` | 1000 条合成题录离线解析/全流程/并发耗时（峰值 5.2 MB） | `data/experiments/stress_1000.json` |
| `docs/evidence/shots/phase-13-library-suggest-0.9.91.png` | 题录库外部检索补库（候选/一键入库） | job/截图 0.9.91 |
| `docs/evidence/shots/phase-16-model-registry-0.9.95.png` | 模型注册表设置页（来源/许可/测连接） | 0.9.95 |
| `docs/evidence/shots/phase-24-keyboard-nav-1.0.0.png` | 报告页 j/k 条目导航 | 1.0.0 |
| `docs/evidence/shots/phase-25-light-contrast-1.0.1.png` | 浅色主题 WCAG AA 修复 | `data/experiments/contrast_report.json` |
| `docs/evidence/shots/phase-33-annotated-citations-1.0.9.png` | 批注 PDF 标正文引注（第 8 页） | job `dfdd817f81af` |
| `docs/evidence/shots/phase1-01-report-charts-v0.9.85-charts.png` | 报告三张真图单独裁切 | 同上 |
| `docs/evidence/shots/phase4-v1.0-docs-site-1.0.0.png` | v1.0 文档站首版截图 | `mkdocs.yml` |

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
| E41 | 正文引注抽取真实语料评测 | 1.0.7 | `data/experiments/citation_anchor_real.json` + `data/experiments/citation_anchor_sample.csv` + `docs/citation_eval.md` | `PYTHONPATH=src python scripts/eval_citation_anchor.py` | 22 篇 / 529 条：21 篇有引注（95.5%）、参考文献被引 318 条（60.1%）、自洽 486/543（89.5%） |
| E42 | 正文引注页码定位 | 1.0.8 | `docs/evidence/shots/phase-32-citation-pages-1.0.8.png` | `pytest tests/test_citation_anchor.py -q` + 真实任务报告 `citations.items[*].page` | 10 页真实论文 18 处引注，17 处定位到页（94.4%） |
| E43 | 批注 PDF 标正文引注 | 1.0.9 | `tests/test_annotate.py::test_annotate_pins_in_text_citations` + 真实任务 `annotated` 统计 | `pytest tests/test_annotate.py -q`；下载 `report.annotated.pdf` 数 `/Annots` | 10 页真实论文：17 处可定位引注贴左页边，1 处未定位如实计数 |

| E44 | 图表引用抽取（22 篇真实语料 185 处 / 101 标签） | `data/experiments/citation_captions.json`；`python scripts/eval_caption_mentions.py`（规则） | 22 篇 / 12 篇有提及；规则匹配、下界 | 报告页引注面板 `docs/evidence/shots/phase-34-caption-mentions-1.0.10.png` |

| E45 | 条目↔正文双向定位：15/15 条命中，抽屉显示引用句与页码 | 报告 JSON `references[*].cited_in`；`tests/test_cited_in.py` | 真实任务 77136f8db5cc；15 条均有正文引用（每页最多 5 处） | `docs/evidence/shots/phase-35-reference-cited-in-1.0.11.png` |
| E46 | 端到端冒烟 14/14（上传→报告→批注→导出→证据包→diff） | `scripts/e2e_smoke.py`；`data/experiments/e2e_smoke.json`；job 94c2214965b1 | 1 篇真实论文 / 14 项检查 | `docs/evidence/shots/phase-36-e2e-report-1.0.11.png` |
| E47 | 文档站 mkdocs 本地构建（12 项导航） | `mkdocs.yml`；`requirements-docs.txt`；`docs/index.md` | 构建成功，`site/index.html` | `docs/evidence/shots/phase-37-docs-site-1.0.11.png` |
| E48 | 全站可访问性/键盘巡检 50/50（11 页 + 报告页） | `scripts/audit_frontend.py http://127.0.0.1:8014`；`data/experiments/frontend_audit.json` | 11 页 × 4 项 + 6 项键盘 = 50 | `docs/evidence/shots/phase-38-a11y-pages-1.0.12.png` |

自检：`python scripts/audit_evidence.py`（见 [evidence_audit.md](evidence_audit.md)）。

- E49 Docker 重置与 1.0.12 镜像验证：`docs/evidence/logs/docker-1.0.12-health.txt`（构建 DONE、镜像 414 MB、容器 health 200 / version 1.0.12 / offline=true）。

- E50 HuggingFace 发布：数据集 <https://huggingface.co/datasets/dfdafs/claimsupport-cn-300>（5 文件）、适配器 <https://huggingface.co/models/dfdafs/citeguard-support-lora-qwen3-1.7b>（9 文件，含 training/ 脚本）；4B 适配器 <https://huggingface.co/dfdafs/citeguard-support-lora-qwen3-4b>（9 文件，132 MB，base_model Qwen/Qwen3-4B）；API 校验 `private=false`，上传脚本 `scripts/upload_hf.py`（支持 `--only`）。

- E51 BGE-M3 真实端点召回：`data/experiments/embeddings_recall_bge_m3_n300.json`（n=300，recall@1 0.8667 / MRR 0.9042 / 编码 20.24 s）；服务脚本 `scripts/bge_embed_server.py`，评测脚本 `scripts/eval_embeddings_recall.py`；`docs/embeddings.md`。构造集、5 个干扰项、单次运行；只验证链路，不代表语义检索 SOTA；服务用完已关。

- E52 GROBID 参考文献对照：`data/experiments/grobid_eval.json`，`scripts/eval_grobid.py`，`docs/ocr_grobid_eval.md` §2。Qwen3 74 vs 73、DeepSeek-R1 90 vs 92、Mixtral 35 vs 27；只比条数、不做字段级质量，未计时。

- E53 Docker 数据盘迁移与 1.0.12 镜像复验：`docs/evidence/logs/docker-1.0.12-health.txt`；`docker_data.vhdx` 由 C: 迁到 `D:\Docker\wsl` 并留 junction，C: 释放约 15.6 GB（3.1→18.7 GB）；迁后 engine 29.9.2、`hello-world` 与 `citeguard-cn:1.0.12` 镜像均在。

- E54 版面/文本选路（1.0.14）：`data/experiments/refs_layout_selection.json`，`scripts/eval_layout_selection.py`。6 篇盲测 PDF 复查；旧 +0.02 健康度门槛让 Phi-3 停在文本路径（71 条 / 0.972），新规则（版面条数不减少且题名健康度更高；或持平但条目更多）改走版面（72 条 / 0.986）。Mixtral 产品路径本来就是文本 35 条 / 1.000，版面 27 条 / 0.926，因此维持文本，不宣称“27→35 修复”。

| E55 | 引用健康画像（1.1.0） | `src/citeguard/health.py`；`tests/test_health.py`；`docs/health.md`；`data/experiments/health_real.json` | 真实任务 `ddf4a1d38040`：95.9 / A；22 篇基线：均值 76.2、中位 79.2、范围 48.3–95.9 | `docs/evidence/shots/phase-F1-health-v1.1.0.png` |

| E56 | 问题分诊（1.1.1） | `src/citeguard/triage.py`；`tests/test_triage.py`；`docs/api.md`；`web/static/js/report.js` | 真实任务 `ddf4a1d38040`：第 1 条标为已修，筛选“已修”返回 1 条；复检 diff 的 resolved 会自动关闭（ignored 保留）；624 tests | `docs/evidence/shots/phase-S2-triage-buttons-v1.1.1.png`、`docs/evidence/shots/phase-S2-triage-filter-v1.1.1.png` |

| E57 | 页内证据视图（1.1.2） | `src/citeguard/pipeline.py::_save_citation_pages`；`tests/test_citation_pages.py`；`docs/api.md`；`web/static/js/report.js` | 真实任务 `96511af51c97`：点「第 2 页」显示原页渲染图 + 页文本，引用句高亮；引注页码定位 17/18（94.4%，跨页断句会漏）；3 个单测 | `docs/evidence/shots/phase-S1-page-view-v1.1.2.png` |

| E65 | 离线 E2E 进 CI（1.3.3） | `scripts/e2e_smoke.py`（`--text`）；`.github/workflows/ci.yml` 的 `smoke` job；`data/experiments/e2e_offline_1.3.2.json`；`docs/e2e.md` | 本地 13/13（health/报告 3 条/引注 2/图表标签 1/5 种导出/证据包 9 文件/diff 自比）；离线状态 Unknown，不冒充准确率；workflow 已加，远端 run 以 Actions 为准 | 无界面截图（CI 日志即证据） |
| E64 | 题录库 SQLite sidecar（1.3.2） | `src/citeguard/library_db.py`；`scripts/migrate_library_sqlite.py`；`tests/test_library_db.py`；`docs/storage.md` | 真实库 28 条 JSON → 28 条 DB → 回读 28 条；JSON 删除后可从 sidecar 恢复；sidecar 损坏时回退空库不抛异常；DOI 去重 2→1；回滚空库拒绝覆盖 | 工具/存储类，无界面截图 |
| E63 | 人工盲标评分工具（1.3.1） | `src/citeguard/audit_score.py`；`scripts/score_audit_sheet.py`；`tests/test_audit_score.py`；`docs/audit_scoring.md`；`data/audit/audit_sheet.csv`（空白）+ `audit_key.json` | 60 条分层盲标；空表 exit 2；5 个单测覆盖完美/混淆/κ、空表与错标、低覆盖、系统-人工一致率；**尚无人填表，不得写人工准确率** | 工具类，无界面截图；证据为 stdout 与测试 |
| E62 | CiteBench-CN v2 + 公开榜单（1.3.0） | `scripts/build_citebench_v2.py`；`scripts/eval_citebench_v2.py`；`data/citebench_cn/citebench_cn_v2.jsonl`；`data/citebench_cn/v2_results.json`；`docs/citebench_v2.md`；`docs/leaderboard.md` | 500 条 11 类；453 条元数据：精确率 1.0000 / 召回 0.6487 / F1 0.7869，Unknown 19.87%（90 条），核验完成后召回 0.8707、准确率 0.9063；中文撤稿 17/17；predatory 无专用检测器（28/30 仅被当作 venue 偏差） | `docs/evidence/shots/phase-F4-citebench-v2-1.3.0.png`、`docs/evidence/shots/phase-F4-leaderboard-1.3.0.png` |
| E61 | 批量聚合（1.2.0） | `src/citeguard/aggregate.py`；`web/app.py` 的 `/api/aggregate(.csv)`；`web/templates/aggregate.html`；`web/static/js/aggregate.js`；`docs/aggregate.md` | 21 篇不同论文 / 509 条引用 / 平均健康分 76.1（A1 B2 C13 D1 E4）；按文件名合并重复报告；Major 9 条经人工核对为双栏 PDF 解析噪声（DOI 截断），不是造假；CSV 可导出 | `docs/evidence/shots/phase-F5-aggregate-21-v1.2.0.png`、`docs/evidence/shots/phase-F5-aggregate-21-table-v1.2.0.png` |
| E60 | 替换建议（1.1.5） | `web/app.py` 的 `/api/report/{id}/replacement`；`web/static/js/report.js`；`scripts/build_replacement_eval.py`；`scripts/eval_replacement.py`；`docs/replacement.md` | 438 条引用句查询、477 条候选池：BGE-M3 R@1 0.1986 / R@3 0.3219 / MRR 0.2948，优于 BM25 与题名重叠；真实任务 `4f00472bc471` 返回 2 条中文候选并生成 GB/T 条目；候选明确标注为线索 | `docs/evidence/shots/phase-F2-replacement-v1.1.5.png` |
| E59 | 撤稿/勘误检查（1.1.4） | `src/citeguard/retraction.py`；`tests/test_retraction.py`；`docs/retraction.md`；`web/static/js/report.js`；`scripts/eval_retraction.py`；`scripts/eval_doi_swap.py` | 真实撤稿 DOI `10.1016/S0140-6736(20)30367-6` → retracted；对照 `10.1038/nature14539` → clean；100 条撤稿 100/100 召回、100 条对照 0 误报（OpenAlex 同源）；99 条 DOI 互换 0 Exact、98 条明确提示；端到端报告 `4f00472bc471` 红色横幅 | `docs/evidence/shots/phase-F3-retraction-v1.1.4.png` |
| E58 | 修订预览（1.1.3） | `src/citeguard/fix.py`；`tests/test_fix.py`；`web/static/js/report.js`；`docs/api.md` | 真实任务 `96511af51c97`：15 条全部可重排、15 条字段完整；修复卷期/页码重复与 Article ID 重复；仅重排已解析字段、不补全缺失项 | `docs/evidence/shots/phase-F2-fix-preview-v1.1.3.png` |
| E70 | 独立首页与工作台拆分（1.5.0） | `web/templates/landing.html`、`web/static/css/landing.css`、`web/static/js/landing.js`、`web/templates/base.html`、`web/app.py`、`tests/test_web.py`、`scripts/capture_evidence.py` | 新增 `/` 品牌首页（极光背景、真实报告截图、三个问题、真实数字、工作流、开源与边界、最终 CTA）；原上传工作台移到 `/workspace`，导航/命令面板/报告返回链接同步；`capture_evidence.py` 增加 landing 与 workspace 两个场景；`pytest` 665 passed | `docs/evidence/shots/phase-42-landing-1.5.0.png`、`docs/evidence/shots/phase-42-workspace-1.5.0.png` |
| E71 | 工作台回归功能页（1.5.1） | `web/templates/index.html`、`web/static/css/refresh.css`、`web/app.py`、`tests/test_web.py` | 删除工作台上的 hero 大标题、产品数字条、工具行与「怎么工作」营销段落；改为紧凑标题 + 上传表单 + 右侧「本次会检查 / 最近报告 / 本地题录库」；最近报告按 `has_report` 过滤；`pytest` 665 passed | `docs/evidence/shots/phase-43-workspace-focus-1.5.1.png` |
| E72 | 任务分区整合（1.6.0） | `web/templates/base.html`、`web/templates/_section_tabs.html`、`index/support/batch/history/aggregate/figure/compare/discover/about/benchmark/settings_models.html`、`web/static/css/refresh.css`、`web/static/js/app.js`、`web/app.py`、`tests/test_web.py` | 导航收成工作台 / 报告 / 题录库 / 工具 / 关于五区，区内用标签切换（论文体检·快速判定·批量判定；全部报告·批量聚合；图表·对比·发现；关于·评测·模型）；删除各功能页英文 kicker、营销式统计卡与重复说明；历史页默认按文件名合并（显示「· N 次」），可切 `?all=1` 查看每次分析；报告页检查明细默认折叠；命令面板同步；`pytest` 668 passed | `docs/evidence/shots/phase-45-workspace-1.6.0.png`、`docs/evidence/shots/phase-45-reports-1.6.0.png`、`docs/evidence/shots/phase-45-tools-1.6.0.png`、`docs/evidence/shots/phase-45-about-1.6.0.png`、`docs/evidence/shots/phase-45-support-1.6.0.png`、`docs/evidence/shots/phase-45-library-1.6.0.png` |
| E73 | 图表层（1.7.1） | `web/static/js/charts.js`、`web/static/vendor/echarts.min.js`、`docs/charts.md`、`web/app.py`（`/api/history/trend`、`benchmark_v2`、`year_hist`）、`aggregate/history/library/benchmark/batch/report` 模板与 JS、`tests/test_web.py` | ECharts 5.5.1 仓库内置（1,030,855 B，Apache-2.0，不走 CDN）；聚合 5 篇示例三图、历史 2 个有报告日、题录库 27 条、CiteBench v2 500 条（TP229/FP0/FN124/TN100，撤稿 17/17）、批量四档环、报告页 ECharts + fallback；671 tests | `docs/evidence/shots/phase-46-aggregate-1.7.1.png`、`docs/evidence/shots/phase-46-history-1.7.1.png`、`docs/evidence/shots/phase-46-library-1.7.1.png`、`docs/evidence/shots/phase-46-benchmark-1.7.1.png`、`docs/evidence/shots/phase-46-report-charts-1.7.1.png` |
| E74 | 列表分页与检查抽屉（1.7.3） | `web/static/js/pager.js`、`web/static/js/report.js`、`web/static/js/charts.js`（`resize`）、`web/templates/base/history/library/aggregate/batch/report.html`、`web/static/css/refresh.css`、`tests/test_web.py`、`scripts/capture_ux_1_7_3.py`、`docs/ui_patterns.md` | 共享分页组件：页码/上下页/10-20-50/每页计数，URL 写 `?page=`；已接历史 23 行、题录库 28 条、聚合 20 篇、批量结果。报告检查明细改右侧 680px 抽屉，六标签按数据自动隐藏，Esc/遮罩关闭，图表切标签后 resize；`pytest` 673 passed，web 60 passed | `docs/evidence/shots/phase-47-history-pager-1.7.3.png`、`docs/evidence/shots/phase-47-library-pager-1.7.3.png`、`docs/evidence/shots/phase-47-report-checks-1.7.3.png`、`docs/evidence/shots/phase-47-report-checks-charts-1.7.3.png` |
| E75 | 修复闭环（1.7.4） | `src/citeguard/fix.py`、`web/app.py`（`/api/report/{id}/repair/*`、报告页改用 `_load_active_report`）、`web/templates/report.html`、`web/static/js/report.js`、`web/static/css/refresh.css`、`tests/test_repair_api.py`、`docs/repair_loop.md` | 预览/应用/撤销真实任务 `96511af51c97`：15 条全部可修，应用后 `report.fixed.json` + `repair.json`，30 分钟撤销倒计时，撤销后两文件删除、state 回 unfixed；`pytest` 792 passed，repair API 4 passed | `docs/evidence/shots/phase-48-repair-preview-1.7.4.png`、`docs/evidence/shots/phase-48-repair-applied-1.7.4.png` |
| E76 | CiteMap 证据地图（1.7.4） | `src/citeguard/evidence_map.py`、`data/evidence_map/`、`web/templates/citemap.html`、`web/static/js/citemap.js`、`web/static/css/citemap.css`、`web/app.py`（`/citemap`、`/api/citemap/*`）、`tests/test_evidence_map.py`、`tests/test_citemap_page.py`、`docs/evidence_map.md` | 2 主题 × 15 篇开放论文；AI 教育 15 篇/4 claim/5 evidence/3 gap/30 DOI 30/30；人工示例 10 条、`verified=false`、仅摘要；页面真实渲染并选中论文展示 claim/quote/locator/method/sample/gap | `docs/evidence/shots/phase-49-citemap-1.7.4.png` |
| E77 | 证据矩阵（1.7.5） | `scripts/build_evidence_matrix.py`、`docs/evidence_matrix.md`、`data/experiments/evidence_matrix.json`、`tests/test_evidence_matrix.py` | 32 条对外数字统一收口：每条含值/样本/证据 JSON/复现命令/口径；`--check` 校验文件存在与最新；待补 2 项（100 条人审、CiteMap 60 格）；`pytest` 858 passed | `docs/evidence/shots/phase-50-evidence-matrix-1.7.5.png` |
| E78 | 题录库标签与重复合并（1.7.5） | `src/citeguard/local_library.py`、`src/citeguard/library_db.py`、`web/app.py`、`web/templates/library.html`、`web/static/js/library.js`、`docs/library_tags.md`、`tests/test_local_library.py`、`tests/test_web.py` | 3 条演示题录：2 条同 DOI 被分组并可合并；标签列显示 AI/教育、综述、深度学习；JSON 主存 + SQLite sidecar schema 2 迁移；标签/重复/合并 API 3 个；`pytest` 808 passed | `docs/evidence/shots/phase-51-library-tags-1.7.5.png`、`docs/evidence/shots/phase-51-library-dupes-1.7.5.png` |
| E79 | 支持度模型矩阵（1.7.6） | `scripts/build_support_matrix.py`、`data/experiments/support_matrix.json`、`docs/model_matrix.md`、`tests/test_support_matrix.py`；4B 产物 `data/experiments/support_lora_qwen3_4b*.json`、`docs/model_card_support_lora_4b.md` | 8 行同口径矩阵：14B 0.9574、14B 4-bit 0.9588、8B 0.8515、1.7B LoRA 0.9721、4B LoRA 1.0000（构造模板饱和）；有逐条预测的行给 1000 次 bootstrap 95% CI 与错误清单；不能当人审 | `docs/model_matrix.md` |
| E80 | CiteGuard Live 网页试用（1.7.7） | `web/templates/live.html`、`web/static/js/live.js`、`web/static/css/live.css`、`src/citeguard/live_check.py`、`extension/v2/`、`tests/test_live_page.py`、`tests/test_live_check.py` | 划句 → 检索候选摘要 → 四档 + 逐字证据；单次实测 6.7 s、5 候选；扩展 v2 为 MV3 侧边栏；不读全文，`no_evidence` 不当假 | `docs/evidence/shots/phase-53-live-page-1.7.7.png`、`docs/evidence/shots/phase-53-live-result-1.7.7.png` |
| E81 | Live 公开页评测（1.7.8） | `scripts/eval_live.py`、`data/live_eval/claims_public.jsonl`、`data/live_eval/pages_public.json`、`data/live_eval/live_eval_public.json`、`tests/test_live_eval.py`、`docs/live_eval.md` | 5 篇 arXiv HTML、30 条英文正文句、每页 6 条；hit@3 0.70（21/30）/ hit@1 0.5667；P50 7.8 ms、P95 16.5 ms；标题优先排序在公开页集上选定（0.60→0.70），9 条未进 top-3，需新集复核；中文跨语言集 0/30 另计不混算 | `docs/live_eval.md` |
| E82 | 外部基线汇总（1.7.9） | `docs/baselines.md`、`data/experiments/scifact_support_results.json`、`data/experiments/scifact_refchecker_deepseek.json`、`data/experiments/chartcheck_val400_v3.json`、`data/experiments/embeddings_recall_bge_m3_n300.json`、`docs/research/experiments/e3_t2retrieval.json` | SciFact 300 条本产品 0.8224 / RefChecker 0.7646；ChartCheck 400 三分类 0.7628、二分类 0.7903；BGE-M3 recall@1 0.8667；T2Retrieval BM25 R@3 0.79；每条附 n 与不可比说明 | `docs/baselines.md` |
