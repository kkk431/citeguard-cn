# 对外数字 → 证据矩阵

> 规则：报告、PPT、README、答辩中出现的每个数字，都必须能在本表找到「证据 JSON / 复现命令 / 样本量 / 口径」。
> 本文件由 `scripts/build_evidence_matrix.py` 生成；`--check` 会校验文件存在与内容是否最新。边界与不能说的话见每行 note。

| 类别 | 对外说法 | 值 | 样本 | 证据 | 复现 | 截图 / 口径 |
|---|---|---|---|---|---|---|
| 基准 | CiteBench-CN v1 字段级检出 | macro-F1 0.9684 / acc 0.9680 | 250 条 | `data/citebench_cn/results.json` | `PYTHONPATH=src python scripts/eval_citebench.py` | —<br>250 条构造基准；v1 口径，与 v2 500 条不可混用 |
| 基准 | CiteBench-CN v2 问题检出 | precision 1.0000 / recall 0.6487 / F1 0.7869 / acc 0.7263 | 453 条（500 中可核验） | `data/citebench_cn/v2_results.json` | `PYTHONPATH=src python scripts/eval_citebench_v2.py` | docs/evidence/shots/phase-46-benchmark-1.7.1.png<br>Unknown 90 条（0.1987）计漏报；核验完成后 recall 0.8707 |
| 基准 | ClaimSupport-CN 100 条 | macro-F1 0.9597 / acc 0.9500 | 100 条 | `data/claimsupport_cn/results.json` | `PYTHONPATH=src python scripts/eval_support_local.py` | docs/evidence/shots/phase-1-model-compare-1.0.12.png<br>构造标签；产品同路径；v10 prompt + 覆盖审计 |
| 基准 | ClaimSupport-CN 300 条合并集 | macro-F1 0.9841 / acc 0.9833 | 300 条 | `data/experiments/release300.json` | `见 docs/experiments.md（release300）` | —<br>构造标签，非人审；与 100/60/140 分批口径不可混用 |
| 校准 | 支持度置信度校准 | ECE 0.0400（acc 0.9833，平均置信 0.9477） | 300 条 | `data/experiments/support_calibration.json` | `PYTHONPATH=src python scripts/eval_support_calibration.py` | —<br>judge 自报置信度；构造标签 |
| 真实语料 | 22 篇真实论文 409 条参考文献 | Exact 125 / Minor 87 / Unverified 197 / Major 0 | 20 篇 / 409 条 | `data/experiments/verify_real.json` | `PYTHONPATH=src python scripts/eval_verify_real.py` | —<br>Major 0；Unverified 不等于错误；联网源随网络状态波动 |
| 真实语料 | 接本地题录库后的 409 条 | Exact 405 / Minor 4，明确结论 409/409 | 20 篇 / 409 条 | `data/experiments/library_real.json` | `PYTHONPATH=src python scripts/eval_library_real.py` | —<br>库内 408 条；字段不一致检出 4 |
| 解析 | 真实论文参考文献切分 | 529 条 / clean 1.0000 | 22 篇 | `data/experiments/parse_real.json` | `PYTHONPATH=src python scripts/eval_parse_real.py` | —<br>clean = 标题/年份/作者可解析的比例；非语义正确率 |
| 解析 | 第五次预注册盲测（3 篇新 PDF） | qwen3 73 条 100.0% / deepseek_r1 92 条 96.7% / mixtral 35 条 100.0% | 3 篇，协议先于运行固定 | `data/experiments/blind_test5.json` | `见 docs/blind_test_results.md §14` | —<br>健康率是启发式题名检查，不是语义正确率；不可重选样本 |
| 模型 | Qwen3-1.7B LoRA 支持度判定 | test macro-F1 0.9721 / acc 0.9667；基座 0.4935 | 60 条 test（train 80） | `data/experiments/support_lora_qwen3_1.7b.json` | `PYTHONPATH=src python scripts/eval_support_adapter.py` | —<br>构造标签；训练/测试同构造管线，衡量格式与映射学习，不是开放世界泛化 |
| 模型 | Qwen3-4B LoRA 支持度判定 | test macro-F1 1.0000 / acc 1.0000（95% CI 1.0000–1.0000） | 60 条 test（train 600） | `data/experiments/support_matrix.json` | `PYTHONPATH=src python scripts/build_support_matrix.py` | —<br>构造标签；adapter 132 MB；满分是构造模板饱和，不代表开放世界能力 |
| 图表 | ChartCheck 400 零样本 | macro-F1 0.7628 / acc 0.6950 | 400 条英文图表结论 | `data/experiments/chartcheck_val400_v3.json` | `PYTHONPATH=src python scripts/eval_chartcheck.py --prompt v3 --sample 400` | docs/evidence/shots/phase-46-benchmark-1.7.1.png<br>外部数据，零样本；只看结论与图是否一致 |
| 图表 | 真实论文图表小样本 | acc 1.0000（支持召回 1.0000，矛盾召回 1.0000） | 10 条断言（样本小） | `data/experiments/figure_real26_8b_v3.json` | `PYTHONPATH=src python scripts/eval_figure_prompt.py` | —<br>平均 2.25 s/条；只作小样本复测 |
| 扫描件 | 扫描版 PDF OCR 后解析 | 23/24 条参考文献 | 7 页，150 dpi | `data/experiments/ocr_scan_real.json` | `PYTHONPATH=src python scripts/eval_ocr_scanned.py --input <pdf>` | —<br>42.5 s；字段覆盖 {'title': 23, 'authors': 23, 'year': 23, 'venue': 19, 'doi': 0} |
| 国标 | GB/T 7714-2025 类型码与格式漂移 | 类型码 100/100；漂移检出 29/30 | 100 条构造条目录入 | `data/experiments/e4_format.json` | `PYTHONPATH=src python scripts/e4_format_check.py` | docs/evidence/shots/phase-46-report-charts-1.7.1.png<br>30 条漂移为构造样本；不检查作者/卷期语义真实性 |
| 中文覆盖 | 万方开放平台强命中 | 111/184 条强命中（60.3%） | 184 条中文未核验题录；试用配额 | `data/experiments/wanfang_batch.json` | `见 docs/chinese_sources.md` | —<br>命中 138 条；仅 184 条候选，不是全部中文引用；配额已用完 |
| 抗伪造 | 真实题录变异检测 | 197/200 检出（98.5%） | 5 类 x 40 条 = 200 条；语料 409 条 | `data/experiments/real_mutation_eval.json` | `见 docs/experiments.md` | —<br>纯编造 13 条按设计给 Unverified，不计检出；Major 占比高 |
| 抗伪造 | 题名与 DOI 张冠李戴 | 99 对中 Exact 0 条；DOI 不符提示 98 条 | 99 对构造样本 | `data/experiments/doi_swap_eval.json` | `PYTHONPATH=src python scripts/eval_doi_swap.py` | —<br>构造 swap；不是人工标注；98 条明确写 DOI 指向另一篇 |
| 引注 | 正文引注抽取与覆盖 | 543 处引注；被引条目 318/529（0.6011） | 21/22 篇有引注 | `data/experiments/citation_anchor_real.json` | `PYTHONPATH=src python scripts/eval_citation_anchor.py` | docs/evidence/shots/phase-33-annotated-citations-1.0.9.png<br>key 自洽 0.8950；自动检查，不是人工准确率；60.1% 是下界 |
| 替换候选 | 上下文检索候选（BGE-M3） | R@1 0.1986 / R@3 0.3219 / R@5 0.3973 / MRR 0.2948 | 438 查询 / 477 候选 | `data/experiments/replacement_eval.json` | `PYTHONPATH=src python scripts/eval_replacement.py` | docs/evidence/shots/phase-F2-replacement-v1.1.5.png<br>真值是作者实际引用的文献，不是“哪条支持这句话”；BGE 需端点 |
| 撤稿 | 撤稿状态检测 | 召回 100%（100/100）；对照误报 0% | 100 撤稿 + 100 对照 | `data/experiments/retraction_eval.json` | `PYTHONPATH=src python scripts/eval_retraction.py` | docs/evidence/shots/phase-F3-retraction-v1.1.4.png<br>OpenAlex 同时是样本标签与检测源，衡量一致性不是独立真值 |
| 健康画像 | 22 篇真实论文引用健康分 | 均值 76.2 / 中位 79.2（范围 48.3–95.9） | 22 篇；支持度关闭 | `data/experiments/health_real.json` | `PYTHONPATH=src python scripts/eval_health_real.py` | docs/evidence/shots/phase-F1-health-v1.1.0.png<br>规则加权分，不是期刊标准；仅同一解析/核验版本内可比 |
| 性能 | 1000 条离线题录 | 解析 0.118 s / 冷启动 0.718 s / 热 0.159 s / 双并发 0.329 s | 1000 条，86263 字符 | `data/experiments/stress_1000.json` | `PYTHONPATH=src python scripts/stress_1000.py` | docs/evidence/shots/phase-3-stress1000-1.0.12.png<br>峰值 5.2 MB；离线、合成题录，不含联网核验 |
| CiteMap | 证据地图语料 | 2 主题 / 30 篇 / 7 条断言 | 2 主题 x 15 篇；10 条人工示例 | `data/evidence_map/index.json` | `PYTHONPATH=src python -m citeguard.evidence_map --check` | docs/evidence/shots/phase-49-citemap-1.7.4.png<br>30/30 DOI 可解析；60 格人工核对待补，当前只展示示例抽取 |
| Live | 公开页 30 句检索命中 | hit@3 0.70 (21/30) / hit@1 0.57 (17/30) | 30 句英文 / 5 篇 arXiv HTML | `data/live_eval/live_eval_public.json` | `PYTHONPATH=src python scripts/eval_live.py --claims data/live_eval/claims_public.jsonl --pages data/live_eval/pages_public.json --out data/live_eval/live_eval_public.json` | docs/evidence/shots/phase-53-live-result-1.7.7.png<br>句子真实出现在页面上；标题优先排序后 hit@3 0.60→0.70；9 条未进 top-3（4 条排 4-5、5 条更后）；规则在同一集选定，需新集复核 |
| Live | 中文跨语言 30 句检索命中 | hit@3 0.00 (0/30) | 30 句中文 / 5 个无关公开页 | `data/live_eval/live_eval_crosslingual.json` | `PYTHONPATH=src python scripts/eval_live.py --out data/live_eval/live_eval_crosslingual.json` | —<br>句子来自本地中文 PDF，页面不是句子所在论文页；任务与公开页集不同，禁止混算；不声称检索天花板 |
| 工程 | 端到端冒烟 | 14/14 项通过 | job 94c2214965b1，version 1.0.11 | `data/experiments/e2e_smoke.json` | `PYTHONPATH=src python scripts/e2e_smoke.py` | —<br>含上传/报告/批注/导出/证据包/diff；不含人工判断 |

## 待补 / 不宣称

| 类别 | 项目 | 当前状态 | 证据位置 |
|---|---|---|---|
| 人审 | 100 条三人盲标 | 包已生成，κ 待回收；不得把构造标签写作人审金标 | `dist/CiteGuard-CN_盲标包_100条_发给标注者.zip` |
| CiteMap | 60 格人工核对 | 只有 10 条人工示例，60 格核对未完成 | `t4` |

说明：
- 「构造标签」指标签由构造规则决定，不是人工语义标注；不能写成人工金标准。
- 「Unverified」是没核到，不是判假；「Major」才是指控。
- 外部数据集（ChartCheck/SciFact/T2Retrieval）只用于对照，不能与构造集混算。
- 人审与 CiteMap/Live 核对未完成前，本表保持 pending，不用预测值占位。
