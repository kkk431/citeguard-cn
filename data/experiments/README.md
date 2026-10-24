# 实验结果索引（`data/experiments/`）

> 这里存放所有评测/实验的**原始结果 JSON**，是 README、`docs/ppt_numbers.md`、评测页 `/benchmark`
> 里每个数字的证据文件。第三方全文语料（`data/real_corpus/`）与 HTTP 缓存（`cache_*`、`manual_cache`）
> 只在本地产出、**不随仓库分发**；对应的抓取/评测脚本都在 `scripts/`，可按口径复跑。

## 1. 自建评测集（主结果）

| 文件 | 内容 | 脚本 | 关键数字 |
|---|---|---|---|
| 上级目录 `data/citebench_cn/` | CiteBench-CN：250 条中文引文真实性评测集 + 结果 + 数据卡 | `scripts/build_citebench.py`、`scripts/evaluate_citebench.py` | macro-F1 **0.9684** / acc 0.968；DeepSeek 零样本基线 0.5159 |
| 上级目录 `data/claimsupport_cn/` | ClaimSupport-CN：100 条引用支持度评测集 + 两段式 judge 正式结果（现行 v10 prompt；历史 v4 为 0.9328、v8 为 0.9544） | `scripts/build_claimsupport.py`、`scripts/evaluate_support.py` | macro-F1 **0.9597** / acc 0.950 |
| `support_two_stage_results.json` | 两段式 judge 的独立 harness（历史对照，v4 时期） | `scripts/experiment_support_two_stage.py` | harness 0.9439 vs 当时产品路径 0.9328；现行 v10 产品路径 0.9597 |
| `support_v2_results.json` … `support_v5_results.json`、`support_v3_rerun_results.json`、`support_v3_vote3_results.json` | 支持度 prompt 消融记录（v1–v5、自一致性投票等） | `scripts/experiment_support_prompt.py` | v3 单段 0.9005、v1 0.7951；prompt 版本见 `scripts/support_prompt_*.txt` |

## 2. 真实已发表论文语料（本地语料，不随仓库分发）

语料：20 篇汉斯出版社 OA 中文论文（发布版参考文献 + PDF）+ 2 篇 OpenAlex 英文/中文 OA 论文（PDF）。
抓取脚本：`scripts/fetch_hanspub_corpus.py`、`scripts/fetch_real_corpus.py`。

| 文件 | 内容 | 脚本 | 关键数字 |
|---|---|---|---|
| `parse_real.json` | 22 篇真实论文的参考文献解析（发布版 409 条 / PDF 抽取 529 条） | `scripts/eval_parse_real.py` | 干净率 **100%**（发布版）/ **99.8%**（PDF，逐条 99.6%）；标题定位 22/22 |
| `verify_real.json` | 20 篇真实论文 409 条已发表引文的真实性核验 | `scripts/eval_verify_real.py` | Exact 125 / Minor 87 / Unverified 197，**Major 0**；网页引文链接检查 13 live / 3 mismatch / 7 blocked |
| `library_real.json` | 本地题录库实验：库由发布版列表构建（408 条），输入为 PDF 抽取（409 条） | `scripts/eval_library_real.py` | 可判定 **409/409（100%）**，字段偏差 4 条 |
| `ocr_scan_real.json` | 纯图片 PDF 的 OCR 兜底实测（7 页真实论文渲染成扫描件） | `scripts/make_scanned_pdf.py`、`scripts/eval_ocr_scanned.py` | 解析出 **23/24 条**；题名/年份 23/23 |
| `real_mutation_eval.json` | 真实文献注入错误：40 条带 DOI 引文 × 5 类可控变异，另 40 条未改动基线与 13 条无锚点伪造 | `scripts/eval_real_mutation.py` | 检出 **197/200（98.5%）**；基线 Major **0/40**；无锚点伪造 13/13 Unverified（按设计不指控） |

## 3. 公开外部数据（可分发）

| 文件 | 内容 | 脚本 | 关键数字 |
|---|---|---|---|
| `scifact_support_results.json` | 英文 SciFact dev 300 条**零样本**支持度判定（未训练/微调） | `scripts/eval_support_scifact.py` | oracle 证据句 macro-F1 **0.8224** / 整段摘要 **0.7939** |
| `search_recall.json` | 中文题名检索召回（OpenAlex 已收录的 25 篇中文论文回搜） | `scripts/experiment_search_recall.py` | OpenAlex 标题检索召回 **0.92** |
| `support_local_qwen25_3b_gpu.json` / `_simple.json` | Qwen2.5-3B-Instruct 在 1×TITAN Xp 上的支持度判定（100 条，产品/精简 prompt） | `scripts/local_judge_server.py` + `scripts/evaluate_support.py` | 产品 0.3894 / 精简 **0.6291** |
| `support_local_qwen25_7b_gpu.json` / `_simple.json` | Qwen2.5-7B-Instruct 在 2×TITAN Xp 上的支持度判定（100 条，产品/精简 prompt） | 同上 | 产品两段式 **0.7181** / 精简 0.7022 |
| `support_local_qwen3_1.7b_simple.json` | Qwen3-1.7B（Apache-2.0）在 CPU 上离线跑支持度（20 条试点，精简 prompt） | `scripts/eval_support_local.py` | macro-F1 **0.7059**（46 s/条） |
| `support_local_Qwen_Qwen3-1_7B.json` | 同模型、产品长 prompt 的试点（对照） | 同上 | macro-F1 0.5060（93 s/条） |
| `support_local_qwen3_8b_v8_test.json` / `support_local_qwen3_14b_v8_{dev,test,all}.json` | Qwen3-8B/14B 在 4×RTX 4090 上的 **v8 few-shot + 审计 v2** 实测（历史对照） | `scripts/local_judge_server.py` + `scripts/eval_support_prompt.py`（`--prompt-file scripts/support_prompt_v8.txt --audit-style v2`） | 14B test 0.9574、all 100 0.9661；8B test 0.8346 |
| `support_local_qwen3_8b_v10_{dev,test}.json` / `support_local_qwen3_14b_v10_{dev,test,all}.json` | Qwen3-8B/14B **v10 few-shot + 审计 v2** 实测（dev 40 / test 60 / all 100） | 同上（`--prompt-file scripts/support_prompt_v10.txt --audit-style v2`） | 14B dev **1.0000**、test **0.9574**、all 100 **0.9744**；8B test **0.8515**；托管 v10 0.9597 |
| `support_local_qwen3_{14b,8b}_product_all.json` | **产品代码路径直调**（`support.judge_support`，自动 v10 + 审计 v2，全 100 条），证明本地模型不是只在评测脚本里成立 | `scripts/evaluate_support.py`（`DEEPSEEK_BASE_URL` 指向本地 OpenAI 兼容服务） | 14B **0.9744** / 8B **0.8664**，与脚本逐条一致；该复核修掉审计风格检测与缓存键两个产品 bug |
| `support_local_qwen3_gpu.json` | 上面各本地模型的汇总表（供 `/benchmark` 页面直接读取） | 手工汇总自各 JSON | 16 行（v4 基线 + v7/v8/v10 + 产品路径） |
| `support_local_qwen3_8b_v10_v2_thinking_dev.json` | 消融：Qwen3-8B 开 thinking（`THINKING=1`，v10 + 审计 v2，dev 40） | `scripts/eval_support_prompt.py --max-tokens 900` | **0.8084 / 0.70**，54.2 s/条——比非 thinking 的 0.8882 更差，未采用 |
| `local_gpu_memory.json` | 本地模型显存/延迟实测（VL、8B、14B；含峰值显存与单卡/双卡口径） | 实测采集 | VL-7B 17.2 GB / 1.55 s；Qwen3-8B 16.7 GB / 6.0 s；Qwen3-14B 29.9 GB（双卡）/ 8.1 s |

## 4. 格式规则与工程实验

| 文件 | 内容 | 脚本 | 关键数字 |
|---|---|---|---|
| `e4_format.json` | E4：100 条真实中文文献回灌 GB/T 7714-2025 检查 + 30 条受控漂移 | `scripts/e4_format_check.py` | 类型码识别 **100%**、必填字段 98.4%、受控漂移严格检出 **29/30** |
| `e5_retrieval.json` | E5：CiteBench-CN 检索锚点与延迟统计 | `scripts/e5_retrieval_stats.py` | DOI 锚定命中率 0.7886（真实 DOI 1.0 / 伪造 DOI 404 率 0.8919） |
| `e5_cold_sample.json` | E5：冷启动 12 条抽样延迟（无缓存） | 同上 | 中位 1.54 s/条（含两次 HTTP） |
| `e7_usability.json` | E7：Web 工作台**内部**可用性自测（不是用户研究） | `scripts/e7_usability.py` | 契约探针 + 12 条人工核对；见 `docs/user_test_kit.md` |
| `e7_manual_records.json` / `e7_manual_verdicts.json` | E7：12 条引文的人工核对原始记录与判定 | 同上 | 与工具判定逐条对照，差异已写进 `docs/experiments.md` |
| `citation_consistency.json` | 正文引注一致性检查器的 15 例规则自检用例（未引用 / 缺失编号 / 顺序倒置 / 范围引注等） | `scripts/eval_citation_consistency.py` | **15/15 通过**；用例按 GB/T 顺序编码制构造，非人工标注集 |

| `vl_synth_results.json` / `vl_real_results.json` | E10：图表结论核验（Qwen2.5-VL-7B）合成 40 条 / 真实 10 条 | `scripts/vl_figtest.py`（需 GPU 服务） | 准确率 **0.90 / 0.90**，误报矛盾 0 |
| `figure_prompt_eval.json` | E10 续：图表 prompt/上下文消融（50 条；v1 / v2 / v2+上下文） | `scripts/eval_figure_prompt.py`（需 GPU 服务） | v2+上下文 **0.94**（仅图 0.90），误报矛盾 0 |

## 5. 口径与注意事项

- **代码快照**：`e4_format.json`、`e5_retrieval.json`、`e7_usability.json` 等记录生成时的 `code_snapshot`
  （关键源文件 sha256_16 + mtime），用于说明数字对应哪一版代码；`parse_real / verify_real / library_real / ocr_scan_real`
  的复跑时间与语料数量写在各自 `summary` 里。
- **缓存**：`cache_e4/`、`cache_e5/`、`manual_cache/`、`support_prompt_cache/`、`data/cache/` 都是 HTTP / LLM 缓存，
  已 git-ignore；删除后重跑会重新联网（结果可复现，但耗时与外部数据源当时状态有关）。
- **不可分发的数据**：`data/real_corpus/`（第三方 PDF 全文）已 git-ignore，仅本地评测使用；仓库只保留
  抓取脚本、评测脚本与结果 JSON，符合「不转存、不分发第三方全文」的原则。
- **诚实边界**：构造集（CiteBench-CN / ClaimSupport-CN）的标签由构造过程决定，不是人工双标；真实语料评测是
  内部实验，没有真人用户研究。所有口径与「不能这么说」见 `docs/ppt_numbers.md`。
