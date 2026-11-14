# 机制消融与评分差距证据矩阵

> 只引用仓库已有 JSON 的同集对照，不跑新实验、不改产品代码。共 12 行机制对照（10 行可比、2 行未做/不可比），以及 6 个评分项的“当前最强证据 / 缺口 / 可补的可验证项”。所有数字都来自本页列出的 JSON；推导值（如确定判定率）在行内注明公式。

## 1. 范围与方法

- **同集**：同一评测集、同一口径（同 n、同 prompt/split、同指标）下比较开/关或前后两个版本；不同集只作参考，不写进结论。
- **来源**：每行 `source` 指向仓库内现有 JSON；另有 `source_git` 的，用 `git show <rev>:<path>` 复现，不伪造工作区副本。
- **未做**：没有同集 JSON 的机制（审计 on/off、`[n]` 映射 on/off）明确写“未做/不可比”，不用跨集数字归因。
- **边界**：构造标签、单人非盲判定、单机延迟都如实标注；不做无来源的排名性结论。

## 2. 机制消融表

| ID | 机制 | 对照 → 处理 | 指标 | n | 来源 JSON | 结论（同集） |
|---|---|---|---|---|---|---|
| M01 | 本地题录库匹配 | 仅在线核验（verify_real）→ 在线 + 本地题录库（library_real） | Exact / 确定判定率 | 409 | `data/experiments/verify_real.json`、`data/experiments/library_real.json` | Exact 125 → 405；确定判定 212/409（51.83%）→ 409/409（100%）。两文件独立运行，非逐条配对。 |
| M02 | 公开页候选排序（标题覆盖优先） | 1.7.8 排序 → 1.7.9 排序（标题 0.85 + 数字 0.15） | hit@3 | 30 | `data/live_eval/live_eval_public.json`；旧版 `git show e7383de:data/live_eval/live_eval_public.json` | hit@3 18/30（0.60）→ 21/30（0.70）；hit@1 14/30（0.4667）→ 17/30（0.5667）。排序规则在本集选定，属开发集结果。 |
| M03 | Live fast / full | fast（判 1 条候选）→ full（判前 3 条候选），均页面热缓存 | hit@3 / P50 | 30 | `data/live_eval/live_eval_holdout_fast_warm.json`、`data/live_eval/live_eval_holdout_judge_v2.json` | 命中一致（hit@3 1.00）；P50 3.13 s → 9.68 s（3.09×）。四档由 support 1/partial 12/no_ev 17 变为 support 2/partial 16/no_ev 12。 |
| M04 | 判官调用 on/off | nojudge（判定模型不可用，规则回退）→ judge（判定模型可用），均 full | hit@3 / 四档 / P50 | 30 | `data/live_eval/live_eval_holdout_nojudge.json`、`data/live_eval/live_eval_holdout_judge_v2.json` | 命中不变（hit@3 1.00）；no_evidence 25 → 12、partial 4 → 16；P50 7.94 s → 9.68 s（+1.74 s）。仅说明口径差异。 |
| M05 | 页面参考文献进程缓存 / 预热 | 冷启动（fast）→ 热缓存（fast） | P50 / P95 | 30 | `data/live_eval/live_eval_holdout_fast_noaudit.json`、`data/live_eval/live_eval_holdout_fast_warm.json` | P50 10.52 s → 3.13 s（−70.2%）；P95 28.45 s → 4.50 s；hit@3 不变（1.00）。 |
| M06 | 中文 claim 英文检索 + arXiv DOI 摘要回填 | v2 冷启动（1.7.17）→ v3 冷启动（1.7.18） | hit@3 / P50 / P95 | 30 | `data/live_eval/live_eval_holdout_fast_noaudit.json`、`data/live_eval/live_eval_holdout_fast_v3.json` | 无命中增益（hit@3 均 1.00、hit@1 均 0.90）；P50 10.52 s → 10.12 s（−3.8%），属波动，不宣称提速。 |
| M07 | Qwen3-1.7B 基座 vs LoRA | 基座零样本 → LoRA（r=16） | macro-F1 / accuracy | 60 | `data/experiments/support_matrix.json`、`data/experiments/support_lora_qwen3_1.7b.json` | macro-F1 0.4935 → 0.9721；acc 0.4833 → 0.9667。标签为构造标签，单 seed。 |
| M08 | Qwen3-4B 基座 vs LoRA | 基座零样本 → LoRA | macro-F1 / accuracy | 60 | `data/experiments/support_matrix.json`、`support_lora_qwen3_4b_base_test.json`、`support_lora_qwen3_4b_adapter_test.json` | 0.6208 → 1.0000、acc 0.70 → 1.00（60/60 全对）。**必须标“构造模板饱和”**，不能解读为 4B 比 14B 强，见 `docs/model_card_support_lora_4b.md:72`。 |
| M09 | Qwen3-14B bf16 vs 4-bit | bf16 → NF4 4-bit（同 prompt v10 + audit v2） | macro-F1 / accuracy | 100 | `data/experiments/support_local_qwen3_14b_product_all.json`、`data/experiments/support_local_qwen3_14b_4bit_all.json` | macro-F1 0.9744 → 0.9754（差 0.001）；acc 均 0.97。只能说明该构造集上量化未掉点，不能宣称 4-bit 更优。 |
| M10 | `[n]` → 页面参考文献映射 | 无同集关闭映射运行 → 开启映射 | hit@3（同集 on/off） | 0（未做） | 无 | **未做/不可比**：工作区没有关闭映射的同集 JSON。跨集 18/30→21/30 同时改了排序规则，不能归因于映射。 |
| M11 | 修复/替换候选检索 | title → BM25 → BGE-M3 | R@3 / MRR | 438 | `data/experiments/replacement_eval.json` | R@3：title 0.2329、BM25 0.2580、BGE-M3 0.3219；MRR 0.2245 / 0.2428 / 0.2948。BGE 比 BM25 高 0.0639，但绝对值仍低，且不是“支持度”指标。 |
| M12 | 覆盖审计 on/off | fast 跳过 Stage-2 审计 → full 含审计 | hit@3 / P50 | 0（未做） | 无（相关运行见 `live_eval_holdout_fast_warm.json`、`live_eval_holdout_judge_v2.json`，但差异不单一） | **未做/不可比**：fast/full 同时改变判官候选数（1 vs 3），不能把延迟差归因于审计。 |

## 3. 未做 / 不可比的两行

- **M10（页面引用映射）**：要把 `[n]` 映射算成机制收益，必须在冻结的 held-out 30 句上增加“关闭映射”开关跑一次；本任务不改产品代码，故留作下一步。
- **M12（审计）**：需要一个“只切审计、不切判官候选数”的同集运行；现有 fast/full 是复合变量。

## 4. 评分表对应证据

| 评分项 | 当前最强证据（来源 + 数字） | 缺口 | 可补的可验证项 | 人工盲标 |
|---|---|---|---|---|
| 问题场景（15） | `real_mutation_eval.json`：200 处构造突变检出 197（0.985），基线 40 条 Exact 28（0.70）；`retraction_eval.json`：撤稿 100/100、对照 100/100、FP 0；`doi_swap_eval.json`：99 对 swap 0 条 Exact、98 条标 DOI 不一致；`e4_format.json`：类型码 100/100、必备字段 300/305（98.36%）；`replacement_eval.json`：BGE R@3 0.3219 | 八类问题无统一人工金标；现有数字来自构造突变/构造标签 | 100 条真实中文文献双人盲标，输出八类混淆矩阵；构造标签与人工标签分表 | 未完成 |
| 创新（20） | `library_real.json`：同 409 条 Exact 125→405、确定判定 100%；`live_eval_holdout_enriched.json`：held-out hit@3 30/30、证据 7（下界）→11；`citemap_auto_eval.json`：25/30 篇有自动证据、10 条人工配对覆盖 6 条、stance 3/3；`e7_manual_verdicts.json`：12 条单人非盲判定 | 缺外部同类系统同集对比；CiteMap 人工配对仅 10 条；[n] 映射无同集 on/off | 30 篇 CiteMap 全量人工审计 + 第二人复核；冻结 held-out 上关映射跑同集对照 | 未完成（12 条为单人非盲） |
| AI + 开源（20） | `support_matrix.json`：n=60，1.7B LoRA 0.9721、4B LoRA 1.0（饱和）、14B bf16 0.9574、14B 4-bit 0.9588；`support_calibration.json`：ClaimSupport-100 acc 0.95、ECE 0.0265；`support_local_qwen3_14b_product_all.json`：全集 100 条 0.9744 | 4B 饱和限制演示价值；hosted 0.9841 是 n=300，不能与 n=60 同表；无第三方复现 | 按模型卡在 test60 复跑 adapter，记录命令/耗时/分数；发布复现脚本与输出 JSON | 不适用（构造标签） |
| 完成度（25） | `e2e_offline_1.3.2.json`：13 项检查全过；`stress_1000.json`：1000 条解析 0.118 s、冷跑 0.718 s、热跑 0.159 s、峰值 5.2 MB；`frontend_audit.json`：页面检查全 ok；`evidence_audit.json`：172 个证据路径、missing 为空 | 测试数量只有 CHANGELOG 记录（非 JSON 归档）；完整度评分含人工判断 | 把 pytest 数量/耗时/退出码归档 JSON；干净环境复跑 e2e 并记录版本 | 不适用 |
| 开放成果（15） | `support_matrix.json`（模型族与数据口径同表，hosted 行标注不可比）；`replacement_eval.json`（候选池/queries/边界写入 dataset/boundary）；`live_eval_public.json`（公开页 30 句命中/延迟） | Live 公开页集仅 30 句/5 页；无 stance 金标；正式数据卡未写 | 发布数据卡；held-out 扩到 ≥60 句并保持同协议；公开人工复核 | 未完成 |
| 材料（5） | `evidence_audit.json`：172 个索引路径全部存在；`frontend_audit.json`：页面检查全 ok | 材料多为截图/文档，缺“评分项→JSON→证据编号”机器校验映射；视频/PPT 无 JSON | 每个评分项挂 1 个 JSON + 1 个证据编号，自动校验存在性与数字一致性 | 不适用 |

## 5. 复现命令

```powershell
# 5.1 校验矩阵：行数、来源是否存在、JSON 可加载
python -c "import json,os;m=json.load(open('data/experiments/ablation_matrix.json',encoding='utf-8'));print('rows',len(m['rows']));print('missing',[(r['id'],s) for r in m['rows'] for s in r['source'] if not os.path.exists(s)])"

# 5.2 逐项复核（示例：M03 fast vs full）
python -c "import json;d=json.load(open('data/live_eval/live_eval_holdout_fast_warm.json',encoding='utf-8'));print(d['n'],d['hit@3'],d['p50_ms'],d['label_counts'])"
python -c "import json;d=json.load(open('data/live_eval/live_eval_holdout_judge_v2.json',encoding='utf-8'));print(d['n'],d['hit@3'],d['p50_ms'],d['label_counts'])"

# 5.3 M02 的旧版对照（工作区已被 1.7.9 覆盖）
git show e7383de:data/live_eval/live_eval_public.json > $env:TEMP\live_public_1.7.8.json
python -c "import json,os;d=json.load(open(os.path.join(os.environ['TEMP'],'live_public_1.7.8.json'),encoding='utf-8'));print(d['n'],d['hit@1'],d['hit@3'])"

# 5.4 评分项证据
python -c "import json;d=json.load(open('data/experiments/retraction_eval.json',encoding='utf-8'));print(d['recall_all'],d['false_positive_rate'])"
python -c "import json;d=json.load(open('data/experiments/e4_format.json',encoding='utf-8'))['metrics'];print(d['type_code_recognition'],d['required_fields']['overall'])"
```

## 6. 边界与诚实声明

1. **构造标签**：ClaimSupport-CN、CiteBench-CN、real_mutation 等均为规则/模板构造，不是人工判断；本页不把它们写成人类金标。
2. **单人非盲**：`e7_manual_verdicts.json` 的 12 条是单人逐条核对，未做第二人复核，不能当准确率。
3. **4B 饱和**：4B LoRA 的 1.00 是构造模板饱和（见模型卡），不构成“4B 强于 14B”的证据。
4. **非配对**：M01 两个 JSON 是独立运行，409 条不是逐条 join；只能看总量变化。
5. **复合变量**：M03/M04/M12 中 fast/full、判官、审计同时变化，延迟差不能归因到单一机制。
6. **跨集不归因**：M02 的 0.60→0.70 是开发集结果；M10 的跨集参考不能当映射收益。
7. **单机延迟**：所有 P50/P95 为本机 wall clock，受网络长尾与缓存影响；不承诺稳定延迟。
8. **无人工盲标**：截至 2026-11-15，仓库没有独立人工盲标 JSON；评分表中的“人工盲标”列一律为“未完成/不适用”。

## 7. 文件清单

| 文件 | 说明 |
|---|---|
| `data/experiments/ablation_matrix.json` | 本页的机器可读版：12 行 `rows[]` + 6 项 `scoring_gaps[]` |
| `docs/research/ablation_matrix.md` | 本页 |
| `data/experiments/verify_real.json`、`library_real.json` | M01 |
| `data/live_eval/live_eval_public.json` | M02（+ git `e7383de` 旧版） |
| `data/live_eval/live_eval_holdout_fast_warm.json`、`live_eval_holdout_judge_v2.json` | M03、M04、M05、M12 的相关运行 |
| `data/live_eval/live_eval_holdout_fast_noaudit.json`、`live_eval_holdout_fast_v3.json` | M05、M06 |
| `data/experiments/support_matrix.json`、`support_lora_qwen3_1.7b.json`、`support_lora_qwen3_4b_*_test.json` | M07、M08 |
| `data/experiments/support_local_qwen3_14b_product_all.json`、`support_local_qwen3_14b_4bit_all.json` | M09 |
| `data/experiments/replacement_eval.json` | M11 |
| `data/experiments/real_mutation_eval.json`、`retraction_eval.json`、`doi_swap_eval.json`、`e4_format.json` | 问题场景证据 |
| `data/experiments/citemap_auto_eval.json`、`e7_manual_verdicts.json` | 创新证据 |
| `data/experiments/support_calibration.json` | AI 证据 |
| `data/experiments/e2e_offline_1.3.2.json`、`stress_1000.json`、`frontend_audit.json`、`evidence_audit.json` | 完成度/材料证据 |
