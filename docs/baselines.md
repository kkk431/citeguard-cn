# 外部基线与检索对照（A4）

> 目的：把「本产品」与公开数据集/外部实现放在同一张表里，说明每个数字的 n、口径与不可比之处。
> 规则：不同任务不混算；不把零样本结果与在数据集上微调的系统直接比高低。

## 1. 支持度判定：SciFact（英文，300 条）

SciFact（Wadden et al., EMNLP 2020，CC BY 4.0 / ODC-By 1.0）是英文科学断言 + 摘要证据的三分类任务。我们用**中文两段式 prompt 的产品判定器零样本**跑 300 条，`partial` 映射为 SUPPORT、`no_evidence` 映射为 NOT_ENOUGH_INFO；**没有在 SciFact 上训练**。

| 系统 | 设定 | macro-F1 | accuracy | n | 说明 |
|---|---|---:|---:|---:|---|
| 引证卫士（本产品） | oracle 证据句 | **0.8224** | 0.8267 | 300 | 零样本，中文 prompt；`data/experiments/scifact_support_results.json` |
| 引证卫士（本产品） | 仅摘要 | 0.7939 | 0.8000 | 300 | 同上 |
| RefChecker 官方两阶段 | oracle 证据句 | 0.7646 | 0.7933 | 300 | 按其仓库流程重跑；`data/experiments/scifact_refchecker_deepseek.json` |

结论边界：这是**同数据、不同实现**的对照，不是排行榜；两者都未针对 SciFact 微调，提示词与标签映射不同，差异不等于模型能力差异；上游 PR 已关闭未合并，不宣称被 RefChecker 采纳。

## 2. 图表一致性：ChartCheck（英文，400 条零样本）

ChartCheck（Akhtar et al. 2024）是图表—陈述一致性二分类。我们用 Qwen3-VL-8B 零样本、v3 二分类 prompt，按分层抽样 400 条：

| 系统 | 设定 | macro-F1 | accuracy | n | 说明 |
|---|---|---:|---:|---:|---|
| Qwen3-VL-8B + v3 prompt | 零样本三分类 | **0.7628** | 0.6950 | 400 | `data/experiments/chartcheck_val400_v3.json`；二分类 macro-F1 0.7903 / acc 0.7925 |
| Qwen3-VL-8B + v3 prompt | 零样本三分类 | 0.7763 | 0.7200 | 200 | 较小样本；二分类 macro-F1 0.7938 / acc 0.795，`data/experiments/chartcheck_val200_v3.json` |

边界：ChartCheck 是英文图表问答式数据，与中文论文图表分布不同；0.76–0.80 只能说明零样本可做「第一道筛查」，不能替代人读图。

## 3. 检索与重排

| 组件 | 数据/设定 | 指标 | n | 说明 |
|---|---|---|---:|---|
| BGE-M3（1024 维） | ClaimSupport-CN 300 条，1 正例 + 5 干扰 | recall@1 **0.8667** / MRR **0.9042** | 300 | 构造集，只验证链路；`data/experiments/embeddings_recall_bge_m3_n300.json` |
| BM25（char-bigram） | T2Retrieval dev，固定 seed 42 抽 200 query | R@1 0.73 / R@3 0.79 / R@5 0.84 / MRR 0.7715 | 200 | 通用检索 smoke test，不是产品依赖；`docs/research/experiments/e3_t2retrieval.json` |
| 标题/BM25/BGE 替换候选 | 21 篇真实论文、438 查询、477 候选 | BGE R@3 **0.3219**（title 0.2329 / BM25 0.2580） | 438 | 真值是作者实际引用的文献，不是「哪条支持这句话」；`data/experiments/replacement_eval.json` |

结论边界：替换候选是**线索**，R@3 约 1/3 意味着不能承诺高命中率；产品里明确写「线索，不代表支持该句」。

## 4. 复现命令

```bash
# SciFact 产品零样本
PYTHONPATH=src python scripts/eval_support_scifact.py --limit 300
# ChartCheck 400
PYTHONPATH=src python scripts/eval_chartcheck.py --prompt v3 --sample 400
# BGE-M3 召回（需 CITEGUARD_EMBED_ENDPOINT）
PYTHONPATH=src python scripts/eval_embeddings_recall.py --n 300
# 替换候选
PYTHONPATH=src python scripts/eval_replacement.py --method bge
```

## 5. 不能这么说

- 不能把 SciFact 0.8224 与「在 SciFact 上微调过的系统」直接排名。
- 不能把 ChartCheck 0.76–0.80 说成「图表核验准确率 80%」；它只覆盖 ChartCheck 分布。
- 不能把 BGE-M3 的 recall@1 0.8667 当作端到端支持度准确率；它只测候选排序。
- 不能把 T2Retrieval BM25 的 0.79 当作产品检索质量；它只是通用检索 smoke test。
