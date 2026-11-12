# 公开榜单

这一页只放**能复现、同口径**的数字。不同任务不混排：中文参考文献核验、中文支持度判定、撤稿检查、英文 SciFact、图表核验各自一张表。

## 1. CiteBench-CN v2 · 中文参考文献核验

500 条构造基准（详见 [CiteBench-CN v2](citebench_v2.md)）。产品同一条 `parse_reference → verify_reference` 路径，`Unknown` 单独统计并计为漏报。

| 系统 | 精确 | 召回 | F1 | 准确 | Unknown | 核验后召回 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CiteGuard-CN v1.2.0 | **1.0000** | 0.6487 | 0.7869 | 0.7263 | 19.87% | 0.8707 |

- 0 假阳性：100 条真实 `Exact` 无一被判为问题。
- 漏报全部来自 `Unknown` / `Unverified`（没核完），不是“把假的判成真的”。
- 复现：`PYTHONPATH=src python scripts/eval_citebench_v2.py --workers 6`。
- 提交新系统：按 `data/citebench_cn/v2_predictions.csv` 的 `id` 列输出 `status`（Exact/Minor/Major/Unverified/Unknown），附命令、版本、日期；本页只收可复现结果。

## 2. ClaimSupport-CN · 中文引用-证据支持度（100 条构造集）

四档：支持 / 部分支持 / 矛盾 / 无证据。标签由构造规则决定，非人工标注（见数据集卡）。

| 系统 | macro-F1 | 准确率 | 备注 |
| --- | ---: | ---: | --- |
| DeepSeek-Chat（托管 API） | 0.9597 | 0.96 | 主口径 100 条 |
| Qwen3-14B bf16（本地） | **0.9744** | 0.97 | 全 100 条，产品同路径 |
| Qwen3-14B 4-bit NF4（本地） | **0.9754** | 0.97 | 显存 ~11.7 GB |
| Qwen3-8B bf16（本地） | 0.8664 | 0.87 | 全 100 条 |
| Qwen3-8B 4-bit NF4（本地） | 0.8165 | 0.82 | 全 100 条 |
| Qwen3-1.7B + LoRA（本仓库） | 0.9721 | 0.9667 | **test 60**；与 100 条口径不同；基座零样本 0.4935 |
| Qwen2.5-7B（本地） | 0.7181 | 0.72 | 旧基线 |

- 14B / 4-bit / 8B 为同一接口、同一脚本、完全离线；4-bit 与 bf16 的 macro-F1 在 100 条上基本持平。
- 1.7B LoRA 的训练/评测切分：train 80（ext60 + dev 前 20）、dev 20、test 60；不能与 100 条行直接横比。
- 复现：`scripts/local_text_server.py` + `scripts/eval_support_prompt.py`；LoRA 见 `docs/model_card_support_lora.md`。

## 3. 撤稿 / 勘误

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 合成撤稿集 100 条 | 100/100 检出 | OpenAlex `is_retracted` 取回的真实撤稿记录 |
| 同分布对照 100 条 | 0 误报 | 上述记录的未撤稿版本 |
| CiteBench-CN v2 中文撤稿 17 条 | 17/17 检出 | 外部真值，样本小 |

## 4. 外部参照（不同语言 / 不同任务，非主口径）

| 基准 | 系统 | 结果 | 说明 |
| --- | --- | ---: | --- |
| SciFact（RefChecker 官方两段式，300 对） | CiteGuard-CN | 0.8224 | 英文；官方实现，非中文主口径 |
| ChartCheck 零样本（200 条） | Qwen3-VL-8B | 二分类 macro-F1 0.795 | 图表核验，与文本引用核验不可比 |
| AttributionBench / SciCite | — | 未跑 | 没有结果就不列数字 |

## 5. 一句话

我们最强的不是“抓假召回”，而是**不冤枉真引用**：真实 `Exact` 上 0 假阳性，撤稿 17/17；查不到就诚实报 Unknown，不冒充“已核验”。下一版重点是把 `Unknown` 从 19.9% 降下来，而不是把数字包装得更好看。
