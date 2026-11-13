# Support-LoRA：ClaimSupport-CN 上的 Qwen3-4B 微调

发布位置：<https://huggingface.co/dfdafs/citeguard-support-lora-qwen3-4b>（Apache-2.0，含 adapter/config/metrics/训练脚本）。

> 4B 基座 + LoRA 的支持度判定组件：判断「一条主张是否被给定证据支持」。
> 它不负责引用真伪，也不负责 GB/T 格式。

## 1. 它是什么

| 项 | 值 |
|---|---|
| 基座 | `Qwen/Qwen3-4B`（Apache-2.0） |
| 微调方式 | LoRA，r=16，alpha=32，dropout=0.05，bf16 |
| 可训练参数 | 33,030,144 / 4,055,498,240 (0.8145%) |
| 目标模块 | q/k/v/o/gate/up/down_proj |
| 任务 | 4 分类：support / partial / contradict / no_evidence |
| 训练硬件 | 单张 RTX 4090（24 GB），NVIDIA GeForce RTX 4090 |
| 训练耗时 | 956.2 s（3.0 epoch，225 step） |
| Peak VRAM | 10.88 GB |
| 训练 loss | 均值 0.0169（首点 0.4259 → 末点 0.0，45 个记录点） |
| Adapter 体积 | 132187888 B（adapter_model.safetensors） |
| 运行环境 | Linux-5.19.0-46-generic-x86_64-with-glibc2.35；Python 3.9.25；torch 2.6.0+cu124；transformers 4.57.6；peft 0.15.1；物理机 `4-gpu`（非容器），驱动 535.129.03 |

## 2. 数据与划分

- 数据：`data/sft/support_train.jsonl`（600 条）/ `support_dev.jsonl`（20 条）/ `support_test.jsonl`（60 条）。
- train = 借用官方 dev 20 + ext 60 + v2 140 + a3 380；dev 20 与 test 60 与上一版**字节级一致**。
- 官方 test 60 从未参与训练；train 与 test 的 id / 来源交集均为 0（见 `data/experiments/sft_split_audit.json`）。
- 标注来源：**构造标签，非人工标注**。

## 3. 结果（test 60，同一批 id）

| 模型 | macro-F1 | accuracy | n |
|---|---|---|---|
| Qwen3-8B 零样本（v4 prompt） | 0.7817 | 0.7833 | 60 |
| Qwen3-14B 零样本（v4 prompt） | 0.8887 | 0.8833 | 60 |
| Qwen3-14B 4-bit（v10 prompt） | 0.9588 | 0.9500 | 60 |
| Qwen3-4B 基座零样本（产品 prompt，本机实测） | 0.6208 | 0.7000 | 60 |
| Qwen3-1.7B 零样本（SFT prompt） | 0.4935 | 0.4833 | 60 |
| Qwen3-1.7B + LoRA（SFT prompt） | 0.9721 | 0.9667 | 60 |
| **Qwen3-4B + LoRA（SFT prompt，训练器内生指标）** | 1.0000 | 1.0000 | 60 |
| **Qwen3-4B + LoRA（产品 prompt 路径）** | 1.0000 | 1.0000 | 60 |

同一 test 60 上的混淆矩阵（行=金标，列=预测，顺序 support/partial/contradict/no_evidence）：

**4B + LoRA（产品 prompt 路径）**，macro-F1 1.0000 / acc 1.0000：

```
[
 [24,  0,  0,  0],
 [ 0, 15,  0,  0],
 [ 0,  0,  9,  0],
 [ 0,  0,  0, 12]
]
```

**4B 基座零样本（同一产品 prompt）**，macro-F1 0.6208 / acc 0.7000：

```
[
 [24,  0,  0,  0],
 [10,  4,  0,  1],
 [ 7,  0,  2,  0],
 [ 0,  0,  0, 12]
]
```

产品路径说明：v10 产品 prompt 原样发到 `scripts/adapter_judge_server.py`，由它抽出
【引用句】/【证据片段】再包成 SFT prompt，因此与训练格式一致、与产品调用方式一致。
dev 20 条（仅参考）：macro-F1 1.0000 / acc 1.0000。

**饱和（必须一起读）**：4B + LoRA 在 test 60 上是 **60/60 全对**（macro-F1 1.0000），
训练 loss 在前 10 个记录点内就掉到 ~0（均值 0.0169）。这说明
ClaimSupport-CN 这套**构造模板**对 4B 已经饱和：它证明「4B 能学会该映射」，但**不能**据此说
「4B 比 1.7B LoRA（0.9721）更强」——两者都贴着上限，差异在本题上不可测。分数本身也**不再**
是瓶颈，下一轮要区分模型能力，需要更难的样本（真实引文、更细粒度标签、跨句推理），而不是继续加同模板数据。

同口径校验：表内所有 n=60 的行都逐 id 比对过 `data/sft/support_test.jsonl` 的官方 test 60 顺序
（见 `data/experiments/support_lora_qwen3_4b.json` 的 `provenance_checks`）；8B/14B 走 v4 prompt、
14B 4-bit 走 v10、1.7B 走历史 SFT prompt、4B 两行分别走 SFT prompt 与产品 prompt 路径，逐行注明。

## 4. 逐条抽查（test 10 条，产品 prompt 路径）

| # | id | 金标 | 预测 | 原始输出片段 |
|---|---|---|---|---|
| 1 | `cs-0007` | support | support | {"label": "support", "confidence": 0.8, "reason": "SFT adapt |
| 2 | `cs-0001` | partial | partial | {"label": "partial", "confidence": 0.8, "reason": "SFT adapt |
| 3 | `cs-0008` | contradict | contradict | {"label": "contradict", "confidence": 0.8, "reason": "SFT ad |
| 4 | `cs-0005` | no_evidence | no_evidence | {"label": "no_evidence", "confidence": 0.8, "reason": "SFT a |
| 5 | `cs-0014` | support | support | {"label": "support", "confidence": 0.8, "reason": "SFT adapt |
| 6 | `cs-0004` | partial | partial | {"label": "partial", "confidence": 0.8, "reason": "SFT adapt |
| 7 | `cs-0028` | contradict | contradict | {"label": "contradict", "confidence": 0.8, "reason": "SFT ad |
| 8 | `cs-0010` | no_evidence | no_evidence | {"label": "no_evidence", "confidence": 0.8, "reason": "SFT a |
| 9 | `cs-0017` | support | support | {"label": "support", "confidence": 0.8, "reason": "SFT adapt |
| 10 | `cs-0006` | partial | partial | {"label": "partial", "confidence": 0.8, "reason": "SFT adapt |

全 10 条一致；`confidence` 是判定服务 shim 的常量 0.8，不是模型概率，不用于阈值。完整 60 条预测见 `data/experiments/support_lora_qwen3_4b_adapter_test.json` 的 `predictions`
与 `data/experiments/support_lora_qwen3_4b_spotcheck.json`。

## 5. 诚实边界（必须一起引用）

1. **同分布**：test 与训练集同一套构造模板，分数衡量「学会这套映射」，不是开放世界泛化。
2. **非人工标注**：没有人工金标；不把它说成「人工测试」。
3. **单次运行**：固定 seed 20261114，未做 seed / prompt 扫描；换 prompt 数字会变。
4. **对照表口径**：历史 1.7B/8B/14B 行复用仓库既有 JSON，n=60 且逐 id 对齐官方 test；其中 8B/14B 用的是 v4 prompt，14B 4-bit 用 v10，已在表内逐行注明路径。
5. **只做支持度**：不查引用是否存在（metadata 链路），不做 GB/T 格式（规则引擎）。
6. **未接入产品默认服务**：adapter 未进线上，接入需 vLLM/PEFT 加载并重跑端到端。
7. **产物位置**：`dist/` 在 `.gitignore` 与交付打包排除列表中，adapter 权重只存在于工作区 `dist/models/support_lora_qwen3_4b/`；需要随包分发请单独拷贝或用 `scripts/upload_hf.py` 上传。

## 6. 本地判定服务（可选）

```bash
CUDA_VISIBLE_DEVICES=3 python scripts/adapter_judge_server.py \
  --model models/Qwen3-4B --adapter out/support_lora_qwen3_4b/adapter --port 8101
# dist/models/support_lora_qwen3_4b/ 是 HF 上传布局：配置名是 adapter_adapter_config.json
# （scripts/upload_hf.py 上传时复制为 adapter_config.json）；本地直接加载请用上面的训练产物目录，
# 或先把该文件复制成 adapter_config.json。dist/ 不入 git/打包，权重需单独拷贝或走 upload_hf.py。
# 产品侧：CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8101/v1
#         CITEGUARD_JUDGE_MODEL=qwen3-4b-support-lora
#         CITEGUARD_SUPPORT_AUDIT=0
python scripts/eval_support_adapter.py --model-size 4b \
  --endpoint http://127.0.0.1:8101/v1 --data data/sft --split test
```

## 7. 复现

```bash
# 1) 数据（600/20/60）：先离线重建再装配
python scripts/build_sft_expand.py --offline
python scripts/build_support_sft.py --no-readme

# 2) 训练 + 基线对比（单卡 4090，约 15 分钟）
HF_ENDPOINT=https://hf-mirror.com python -c "from huggingface_hub import snapshot_download as d; d('Qwen/Qwen3-4B', local_dir='models/Qwen3-4B')"
NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 CUDA_VISIBLE_DEVICES=3 \
python scripts/train_support_lora.py --model-size 4b \
  --data data/sft --out out/support_lora_qwen3_4b --epochs 3 --eval-base

# 3) 产品 prompt 路径评测（adapter 与基座各一次）
python scripts/adapter_judge_server.py --model models/Qwen3-4B --adapter out/support_lora_qwen3_4b/adapter --port 8101 &
python scripts/eval_support_adapter.py --model-size 4b --endpoint http://127.0.0.1:8101/v1 --data data/sft --split test --out data/experiments/support_lora_qwen3_4b_adapter_test.json
python scripts/adapter_judge_server.py --model models/Qwen3-4B --no-adapter --port 8102 &
python scripts/eval_support_adapter.py --model-size 4b --endpoint http://127.0.0.1:8102/v1 --data data/sft --split test --out data/experiments/support_lora_qwen3_4b_base_test.json

# 4) 汇总证据与模型卡
python scripts/build_a3b_report.py
```

产物：`out/support_lora_qwen3_4b/adapter/`、`metrics.json`、`run_meta.json`；
证据汇总：`data/experiments/support_lora_qwen3_4b.json`。

## 8. 许可证

- 基座 Qwen3-4B：Apache-2.0。
- 本 LoRA adapter：Apache-2.0（随仓库）。
- 训练数据：本仓库构造，随仓库开放；引用第三方摘要的原文见 `THIRD_PARTY_NOTICES.md`。
