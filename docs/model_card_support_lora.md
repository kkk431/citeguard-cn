# Support-LoRA：ClaimSupport-CN 上的 Qwen3-1.7B 微调

> 一个 1.7B 的开源小模型 + LoRA，专门判断「一条主张是否被给定证据支持」。
> 它是引证卫士的**支持度判定组件**，不负责引用真伪，也不负责 GB/T 格式。

## 1. 它是什么

| 项 | 值 |
|---|---|
| 基座 | `Qwen/Qwen3-1.7B`（Apache-2.0） |
| 微调方式 | LoRA，r=16，alpha=32，dropout=0.05 |
| 可训练参数 | 17,432,576 / 1,738,007,552（1.003%） |
| 目标模块 | q/k/v/o/gate/up/down_proj |
| 任务 | 4 分类：support / partial / contradict / no_evidence |
| 训练硬件 | 单张 RTX 4090（24 GB），bf16 |
| 训练耗时 | 109.2 s（3 epoch，30 step） |
| Adapter 体积 | 82 MB（含 tokenizer 文件；权重 69.8 MB） |

## 2. 数据与划分

- 数据：`ClaimSupport-CN`（100 条构造集）+ `ClaimSupport-CN-Ext`（60 条 disjoint 构造集）。
- 官方 100 集只有 dev 40 + test 60，没有官方 train。
- 因此：`train = ext 60 + dev 前 20`，`dev = dev 后 20`，`test = 官方 test 60`（训练从未见过）。
- 校验：train/test 的 id 交集为 **0**。
- 标注来源：**构造标签，非人工标注**；test 也是构造标签。

## 3. 结果（同一 prompt、同一 test 60 条）

| 模型 | macro-F1 | accuracy |
|---|---|---|
| Qwen3-1.7B 基座，零样本 | 0.4935 | 0.4833 |
| **+ LoRA（本 adapter）** | **0.9721** | **0.9667** |
| （dev 20 条，仅参考） | 0.9365 | 0.9500 |

混淆矩阵（test 60，行=金标，列=预测，顺序 support/partial/contradict/no_evidence）：

```
[[24,  0, 0, 0],
 [ 2, 13, 0, 0],
 [ 0,  0, 9, 0],
 [ 0,  0, 0,12]]
```

唯一错误：2 条 partial 被判成 support。

**产品提示词路径（同一 adapter）**：把 v10 产品 prompt 原样发给
`scripts/adapter_judge_server.py`，由它抽出【引用句】/【证据片段】再包成 SFT prompt，
test 60 仍是 **0.9721 / 0.9667**（`data/experiments/support_adapter_product_path.json`）。
说明它能在产品调用方式下稳定工作；但这一轮只测了支持度判定，没有跑检索、真伪与审计两段。

## 4. 诚实边界（必须一起引用）

1. **同分布**：test 与训练用的扩展集来自同一套构造模板，0.9721 衡量的是「学会这套映射」，不是开放世界泛化。
2. **非人工标注**：没有人工金标；不把它说成「人工测试」。
3. **单次运行**：固定 seed，没有做 seed/prompt 扫描；换 prompt 数字会变。
4. **评测 prompt 不是产品 prompt**：本结果用紧凑 SFT prompt；产品线仍是 `PROMPT_VERSION v10` 的 judge（托管 0.9597 / 14B 0.9744）。
5. **只做支持度**：不查引用是否存在（那是 metadata 链路），不做 GB/T 格式（规则引擎）。
6. **未接入产品**：adapter 还没进在线服务；接入需要 vLLM/PEFT 加载并重跑端到端。

## 5. 本地判定服务（可选）

```bash
CUDA_VISIBLE_DEVICES=3 python scripts/adapter_judge_server.py \
  --model models/Qwen3-1.7B --adapter out/support_lora/adapter --port 8101
# 产品侧：CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8101/v1
#         CITEGUARD_JUDGE_MODEL=qwen3-1.7b-support-lora
#         CITEGUARD_SUPPORT_AUDIT=0   （本服务只做支持度判定）
python scripts/eval_support_adapter.py --endpoint http://127.0.0.1:8101/v1
```

## 6. 复现

```bash
# 1) 生成 SFT 划分（train 80 / dev 20 / test 60）
python scripts/build_support_sft.py --out data/sft

# 2) 训练 + 基线对比（单卡 4090）
NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 CUDA_VISIBLE_DEVICES=3 \
python scripts/train_support_lora.py \
  --model models/Qwen3-1.7B --data data/sft --out out/support_lora \
  --epochs 3 --eval-base
```

产物：`out/support_lora/adapter/`、`metrics.json`、`eval_predictions.jsonl`。
证据汇总：`data/experiments/support_lora_qwen3_1.7b.json`。

## 7. 许可证

- 基座 Qwen3-1.7B：Apache-2.0。
- 本 LoRA adapter：Apache-2.0（随仓库）。
- 训练数据：本仓库构造，随仓库开放；引用第三方摘要的原文见 `THIRD_PARTY_NOTICES.md`。
