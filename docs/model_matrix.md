# 支持度判定模型对比矩阵

> 数据集：ClaimSupport-CN **构造标签**（不是人工金标）。除特别注明外，n=60 为同一 held-out 构造测试集；
> 有逐条预测的行给 bootstrap 95% CI（1000 次、seed 20261114），只有汇总指标的行给点估计。
> 4B LoRA 的满分是构造模板饱和的结果，不能解读为「4B 比 14B 强」。

| 系统 | n | macro-F1 | accuracy | 95% CI (F1) | 错误数 | 提示词/口径 | 来源 |
|---|---|---|---|---|---|---|---|
| DeepSeek（产品同路径） | 300 | 0.9841 | 0.9833 | 0.9671–0.9972 | 5 | support_prompt_v10 + audit v3 | `data/experiments/release300.json` |
| Qwen3-14B bf16 | 60 | 0.9574 | 0.9500 | 0.8974–1.0000 | 3 | support_prompt_v10 + audit v2 | `data/experiments/support_local_qwen3_14b_v10_test.json` |
| Qwen3-14B 4-bit | 60 | 0.9588 | 0.9500 | 0.8993–1.0000 | 3 | support_prompt_v10 + audit v2 | `data/experiments/support_local_qwen3_14b_4bit_test.json` |
| Qwen3-8B bf16 | 60 | 0.8515 | 0.8333 | 0.7497–0.9325 | 10 | support_prompt_v10 + audit v2 | `data/experiments/support_local_qwen3_8b_v10_test.json` |
| Qwen3-1.7B 基座（零样本） | 60 | 0.4935 | 0.4833 | — | — | SFT 同款短提示词 | `data/experiments/support_lora_qwen3_1.7b.json` |
| Qwen3-1.7B + LoRA | 60 | 0.9721 | 0.9667 | 0.9262–1.0000 | 2 | SFT 短提示词（产品路径 shim） | `data/experiments/support_lora_qwen3_1.7b_test_predictions.json` |
| Qwen3-4B 基座（零样本） | 60 | 0.6208 | 0.7000 | 0.4812–0.7486 | 18 | SFT 同款短提示词 | `data/experiments/support_lora_qwen3_4b_base_test.json` |
| Qwen3-4B + LoRA | 60 | 1.0000 | 1.0000 | 1.0000–1.0000 | 0 | SFT 短提示词（产品路径 shim） | `data/experiments/support_lora_qwen3_4b_test_predictions.json` |

## 错误分析（有逐条预测的行）

- **DeepSeek（产品同路径）**：5 条，c2-0048（contradict→partial）、c2-0103（no_evidence→partial）、cs-0001（partial→support）、cs-0027（support→partial）、cs-0056（partial→support）
- **Qwen3-14B bf16**：3 条，cs-0001（partial→support）、cs-0027（support→no_evidence）、cs-0044（support→partial）
- **Qwen3-14B 4-bit**：3 条，cs-0001（partial→support）、cs-0027（support→partial）、cs-0049（partial→support）
- **Qwen3-8B bf16**：10 条，cs-0001（partial→support）、cs-0007（support→partial）、cs-0009（partial→no_evidence）、cs-0014（support→partial）、cs-0024（support→partial）、cs-0027（support→no_evidence）、cs-0031（partial→support）、cs-0037（partial→support）、cs-0049（partial→support）、cs-0065（partial→support）
- **Qwen3-1.7B + LoRA**：2 条，cs-0001（partial→support）、cs-0034（partial→support）
- **Qwen3-4B 基座（零样本）**：18 条，cs-0001（partial→support）、cs-0006（partial→support）、cs-0008（contradict→support）、cs-0025（partial→support）、cs-0028（contradict→support）、cs-0031（partial→support）、cs-0034（partial→support）、cs-0037（partial→support）、cs-0040（contradict→support）、cs-0049（partial→support）、cs-0050（partial→support）、cs-0061（partial→support）、cs-0063（contradict→support）、cs-0065（partial→support）、cs-0072（partial→no_evidence）、cs-0083（contradict→support）、cs-0084（contradict→support）、cs-0085（contradict→support）

## 不能这么说

- 不能说「4B LoRA 准确率 100%」：测试集是同一构造规则生成的模板，训练/测试 claim 不重叠但分布接近；
- 不能把 n=300 的 DeepSeek 行与 n=60 行直接排名；
- 不能把这里的分数当作真人盲标结果；100 条三人盲标尚未回收。
