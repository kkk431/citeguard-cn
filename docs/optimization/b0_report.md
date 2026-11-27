# Batch 0：基线、级联与版本消解

版本：v1.7.51（Batch 0）
基线：v1.7.50 / 1131 tests。

## 0.1 评测/基线 harness

`scripts/tech_eval_harness.py` 把已有结果冻结成一张 scorecard，不重跑模型，避免“记忆中的数字”：

| 数据 | n | 结果 |
| --- | ---: | --- |
| 100 条三人盲标 | 100 | Fleiss κ 0.98116；产品 acc 0.99；macro-F1 0.987707；常数多数类 macro-F1 0.1454 |
| 409 条真实引用 | 409 | Exact 125 / Minor 87 / Unverified 197 / Major **0** |
| 529 条解析 | 529 | clean 1.0 |
| CiteMap 105 格 | 105 | κ 0.6587；机器证据完整支持 8/31（25.8%） |
| 全文层 | 25/30 | 258 组合；full 10 / partial 15 / none 233 |

命令：`python scripts/tech_eval_harness.py --check --out data/experiments/opt_b0_harness_2026-11-27.json`
门禁：5/5 PASS。产物：`docs/optimization/b0_harness.md`。

## 0.2 成本感知级联

`src/citeguard/model_cascade.py`：策略函数 + 可配置阈值；升级条件为低置信、长证据、数字冲突、非法标签；升级失败回退主判，不伪造“更好”的结论。

回放（不是新模型运行）：同一 60 条 test split 上

| 方案 | acc | macro-F1 |
| --- | ---: | ---: |
| 1.7B LoRA（主判） | 0.9667 | 0.9721 |
| 14B 4-bit（全升级 oracle） | 0.9500 | 0.9588 |
| 级联（当前阈值 0.80） | 0.9667 | 0.9721（routed 0） |

结论：**这个 split 上升级没有收益**，1.7B 反而更好；不把级联设为默认路径。级联保留为低置信/长证据/数字冲突场景的可选兜底，不在无收益时增加成本。证据 `data/experiments/opt_b0_cascade_replay_2026-11-27.json`。

## 0.3 版本感知实体消解

`src/citeguard/version_resolution.py`：DOI/arXiv 归一、preprint/published/unknown 分类、同作品版本族、第一作者冲突、年份支持、provenance。
- 集成：`VerifyResult.version` 在 DOI/题名匹配成功时带上版本消解结果；不改变既有状态判定。
- 6 个已知作品 fixture：3 个真实 preprint/published（Attention/BERT/ResNet），同 DOI 双索引、同名不同作者、无匹配；6/6 通过。
- 证据 `data/experiments/opt_b0_version_cases_2026-11-27.json`。

## 边界

- 级联回放用的是历史预测，不是本次新跑；1.7B 的置信度均为 0.8，因此低置信分支没有触发。
- 版本 fixture 是已知作品的手工候选，不是随机样本；409 条真实引用本轮未重跑，只看既有 0 Major 门禁。
- 不新增外部资源、不买库、不训练基础模型；PPT/视频不改。
