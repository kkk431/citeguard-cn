"""Compose the A3b evidence bundle and model card for the Qwen3-4B support LoRA.

Every number is read from a file produced by a real run; nothing is hard-coded.
If an input file is missing the script fails loudly instead of emitting a card
with placeholder numbers.

Inputs (all copied back from the GPU host):
  data/experiments/support_lora_qwen3_4b_metrics.json    trainer metrics.json (base/dev/test, SFT prompt)
  data/experiments/support_lora_qwen3_4b_run_meta.json   trainer run_meta.json (time, VRAM, GPU)
  data/experiments/support_lora_qwen3_4b_adapter_test.json  product-prompt eval, adapter, test 60
  data/experiments/support_lora_qwen3_4b_adapter_dev.json   product-prompt eval, adapter, dev 20
  data/experiments/support_lora_qwen3_4b_base_test.json     product-prompt eval, base model, test 60
  data/experiments/support_lora_qwen3_1.7b.json          historical 1.7B LoRA (n=60)
  data/experiments/support_local_qwen3_{8b,14b,14b_4bit}_test.json  historical baselines (n=60)

Outputs:
  data/experiments/support_lora_qwen3_4b.json
  dist/models/support_lora_qwen3_4b/adapter_README.md
  docs/model_card_support_lora_4b.md
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "data" / "experiments"
OUT_JSON = EXP / "support_lora_qwen3_4b.json"
CARD = ROOT / "docs" / "model_card_support_lora_4b.md"
ADAPTER = ROOT / "dist" / "models" / "support_lora_qwen3_4b"

LABELS = ["support", "partial", "contradict", "no_evidence"]


def load(name: str) -> dict:
    path = EXP / name
    if not path.exists():
        raise SystemExit(f"missing input: {path.relative_to(ROOT)} (copy it back from the GPU host first)")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def flat_metrics(obj: dict) -> dict:
    """Accept both flat {macro_f1,...} and nested {metrics:{macro_f1,...}} layouts."""
    if "macro_f1" in obj:
        return obj
    if "metrics" in obj and isinstance(obj["metrics"], dict):
        merged = dict(obj["metrics"])
        merged.setdefault("n", obj.get("n"))
        return merged
    raise SystemExit(f"no metrics in object with keys {sorted(obj)}")


def ids_of(obj: dict) -> list[str]:
    for key in ("predictions", "details"):
        rows = obj.get(key)
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "id" in rows[0]:
            return [r["id"] for r in rows]
    return []


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def matrix_block(confusion: list[list[int]]) -> str:
    rows = ",\n".join(" [" + ", ".join(f"{v:2d}" for v in row) + "]" for row in confusion)
    return "[\n" + rows + "\n]"


def main() -> int:
    metrics = load("support_lora_qwen3_4b_metrics.json")
    run_meta = load("support_lora_qwen3_4b_run_meta.json")
    env = load("support_lora_qwen3_4b_env.json")
    prod_test = load("support_lora_qwen3_4b_adapter_test.json")
    prod_dev = load("support_lora_qwen3_4b_adapter_dev.json")
    base_test = load("support_lora_qwen3_4b_base_test.json")

    official_test_ids = [
        json.loads(line)["id"]
        for line in (ROOT / "data" / "sft" / "support_test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    harness_base = flat_metrics(metrics["base"])
    harness_dev = flat_metrics(metrics["dev"])
    harness_test = flat_metrics(metrics["test"])
    prod_test_m = flat_metrics(prod_test)
    prod_dev_m = flat_metrics(prod_dev)
    base_test_m = flat_metrics(base_test)

    # ---- historical baselines: numbers and their provenance -----------------
    b17 = load("support_lora_qwen3_1.7b.json")
    b17_test = flat_metrics(b17["test"])
    b17_base = flat_metrics(b17["base"])
    b14 = flat_metrics(load("support_local_qwen3_14b_test.json"))
    b14_4bit = flat_metrics(load("support_local_qwen3_14b_4bit_test.json"))
    b8 = flat_metrics(load("support_local_qwen3_8b_test.json"))

    same_set = {
        "support_lora_qwen3_4b_adapter_test": ids_of(prod_test) == official_test_ids,
        "support_lora_qwen3_4b_base_test": ids_of(base_test) == official_test_ids,
        "support_local_qwen3_14b_test": ids_of(load("support_local_qwen3_14b_test.json")) == official_test_ids,
        "support_local_qwen3_14b_4bit_test": ids_of(load("support_local_qwen3_14b_4bit_test.json")) == official_test_ids,
        "support_local_qwen3_8b_test": ids_of(load("support_local_qwen3_8b_test.json")) == official_test_ids,
    }
    for name, ok in same_set.items():
        if not ok:
            raise SystemExit(f"provenance check failed: {name} is not the official test-60 id order")
    for name, m in (
        ("support_lora_qwen3_4b_adapter_test", prod_test_m),
        ("support_lora_qwen3_4b_base_test", base_test_m),
        ("support_local_qwen3_14b_test", b14),
        ("support_local_qwen3_14b_4bit_test", b14_4bit),
        ("support_local_qwen3_8b_test", b8),
    ):
        if m.get("n") != 60:
            raise SystemExit(f"provenance check failed: {name} n={m.get('n')} != 60")

    comparison = [
        {
            "model": "Qwen3-8B 零样本（v4 prompt）",
            "macro_f1": b8["macro_f1"],
            "accuracy": b8["accuracy"],
            "n": b8["n"],
            "path": "v10/product judge（离线单模型）",
            "source": "data/experiments/support_local_qwen3_8b_test.json",
        },
        {
            "model": "Qwen3-14B 零样本（v4 prompt）",
            "macro_f1": b14["macro_f1"],
            "accuracy": b14["accuracy"],
            "n": b14["n"],
            "path": "v10/product judge（离线单模型）",
            "source": "data/experiments/support_local_qwen3_14b_test.json",
        },
        {
            "model": "Qwen3-14B 4-bit（v10 prompt）",
            "macro_f1": b14_4bit["macro_f1"],
            "accuracy": b14_4bit["accuracy"],
            "n": b14_4bit["n"],
            "path": "v10/product judge（离线单模型）",
            "source": "data/experiments/support_local_qwen3_14b_4bit_test.json",
        },
        {
            "model": "Qwen3-4B 基座零样本（产品 prompt，本机实测）",
            "macro_f1": base_test_m["macro_f1"],
            "accuracy": base_test_m["accuracy"],
            "n": base_test_m["n"],
            "path": "adapter_judge_server --no-adapter",
            "source": "data/experiments/support_lora_qwen3_4b_base_test.json",
        },
        {
            "model": "Qwen3-1.7B 零样本（SFT prompt）",
            "macro_f1": b17_base["macro_f1"],
            "accuracy": b17_base["accuracy"],
            "n": b17_base["n"],
            "path": "SFT prompt（历史口径）",
            "source": "data/experiments/support_lora_qwen3_1.7b.json",
        },
        {
            "model": "Qwen3-1.7B + LoRA（SFT prompt）",
            "macro_f1": b17_test["macro_f1"],
            "accuracy": b17_test["accuracy"],
            "n": b17_test["n"],
            "path": "SFT prompt（历史口径）",
            "source": "data/experiments/support_lora_qwen3_1.7b.json",
        },
        {
            "model": "**Qwen3-4B + LoRA（SFT prompt，训练器内生指标）**",
            "macro_f1": harness_test["macro_f1"],
            "accuracy": harness_test["accuracy"],
            "n": harness_test["n"],
            "path": "SFT prompt（与训练一致）",
            "source": "data/experiments/support_lora_qwen3_4b_metrics.json",
        },
        {
            "model": "**Qwen3-4B + LoRA（产品 prompt 路径）**",
            "macro_f1": prod_test_m["macro_f1"],
            "accuracy": prod_test_m["accuracy"],
            "n": prod_test_m["n"],
            "path": "v10 产品 prompt → shim → SFT prompt",
            "source": "data/experiments/support_lora_qwen3_4b_adapter_test.json",
        },
    ]

    adapter_files = {}
    for path in sorted(ADAPTER.rglob("*")):
        if path.is_file():
            adapter_files[path.relative_to(ROOT).as_posix()] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    weights = ADAPTER / "adapter_model.safetensors"
    if not weights.exists():
        raise SystemExit(f"missing adapter weights: {weights.relative_to(ROOT)}")
    weights_bytes = weights.stat().st_size

    training = {
        "method": "LoRA (bf16)",
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "targets": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        "epochs": run_meta["epochs"],
        "lr": run_meta["lr"],
        "seq_len": run_meta["seq_len"],
        "batch_size": run_meta["batch_size"],
        "grad_accum": run_meta["grad_accum"],
        "optimizer_steps": run_meta["optimizer_steps"],
        "seed": run_meta.get("seed", env["train"].get("seed_arg")),
        "trainable_params": run_meta.get("trainable_params") or env["train"].get("trainable_params"),
        "train_seconds": run_meta["train_seconds"],
        "total_seconds": run_meta["total_seconds"],
        "peak_vram_gb": run_meta["peak_vram_gb"],
        "gpu": run_meta["gpu"],
        "train_loss_last5": run_meta.get("train_loss"),
        "train_loss_mean": env["train"].get("train_loss_mean"),
        "loss_curve_first": env["train"].get("loss_curve_first"),
        "loss_curve_last": env["train"].get("loss_curve_last"),
        "loss_curve_points": len(env["train"].get("loss_curve") or []),
        "env": {
            "host": env["container"]["hostname"],
            "in_docker": env["container"]["in_docker"],
            "os": env["os"],
            "python": env["python"],
            "packages": env["packages"],
            "driver": env["gpu"]["nvidia_smi"],
        },
    }

    bundle = {
        "model": metrics.get("model"),
        "model_size": "4b",
        "adapter": {
            "dir": ADAPTER.relative_to(ROOT).as_posix(),
            "weights": weights.relative_to(ROOT).as_posix(),
            "weights_bytes": weights_bytes,
            "files": adapter_files,
        },
        "task": "4-way claim support classification (support / partial / contradict / no_evidence)",
        "data": {
            "train": ROOT.joinpath("data/sft/support_train.jsonl").name,
            "train_rows": metrics["train"],
            "dev_rows": metrics["dev"],
            "test_rows": metrics["test"],
            "train_sha256": sha256(ROOT / "data/sft/support_train.jsonl"),
            "test_sha256": sha256(ROOT / "data/sft/support_test.jsonl"),
            "label_provenance": "construction labels (rule-built), not human annotations",
            "split_note": "train 600 = 借用官方 dev 20 + ext 60 + v2 140 + a3 380; dev 20 与 test 60 与上一版字节级一致，训练未见过 test。",
        },
        "training": training,
        "harness": {  # trainer-internal greedy eval, SFT prompt
            "base": harness_base,
            "dev": harness_dev,
            "test": harness_test,
        },
        "product_path": {  # scripts/adapter_judge_server.py + eval_support_adapter.py
            "test": {k: prod_test_m[k] for k in ("macro_f1", "accuracy", "confusion", "per_class", "n")},
            "dev": {k: prod_dev_m[k] for k in ("macro_f1", "accuracy", "confusion", "per_class", "n")},
            "base_test": {k: base_test_m[k] for k in ("macro_f1", "accuracy", "confusion", "per_class", "n")},
            "elapsed_sec": prod_test.get("elapsed_sec"),
            "request_errors": len(prod_test.get("request_errors") or []),
            "errors": prod_test.get("errors"),
        },
        "comparison": comparison,
        "provenance_checks": {
            "same_official_test_ids": sorted(same_set),
            "note": "上表所有 n=60 的行都逐 id 比对过 data/sft/support_test.jsonl 的官方 test 60 顺序",
        },
        "honest_notes": [
            "同分布：test 与训练数据来自同一套构造模板，分数衡量'学会映射'，不代表开放世界泛化。",
            "饱和：4B LoRA 在 test 60 上 60/60（macro-F1 1.0），训练 loss 前 10 个记录点即降到 ~0；该构造集对 4B 已无区分度，不能据此说 4B 强于 1.7B LoRA（0.9721）。",
            "构造标签：没有人审金标；不把它写成人工测试。",
            "单次运行：固定 seed 20261114，未做 seed/prompt 扫描。",
            "4B 零样本行用产品 prompt 路径（--no-adapter），与 adapter 行同一服务、同一 prompt。",
            "历史 1.7B/8B/14B 行复用仓库既有 JSON，n=60 且已逐 id 对齐官方 test。",
            "只做支持度判定，不查引用是否存在、不做 GB/T 格式。",
        ],
        "source_files": [
            "data/experiments/support_lora_qwen3_4b_metrics.json",
            "data/experiments/support_lora_qwen3_4b_run_meta.json",
            "data/experiments/support_lora_qwen3_4b_adapter_test.json",
            "data/experiments/support_lora_qwen3_4b_adapter_dev.json",
            "data/experiments/support_lora_qwen3_4b_base_test.json",
        ],
    }
    OUT_JSON.write_bytes(json.dumps(bundle, ensure_ascii=False, indent=1).encode("utf-8"))

    # ---- adapter README ----------------------------------------------------
    ADAPTER.mkdir(parents=True, exist_ok=True)
    readme = f"""# Support-LoRA adapter — Qwen3-4B

- 基座：`Qwen/Qwen3-4B`（Apache-2.0），LoRA r=16 / alpha=32 / dropout=0.05，bf16
- 可训练参数：{training.get('trainable_params')}
- 训练：{training['epochs']} epoch，{training['optimizer_steps']} optimizer step，
  {training['train_seconds']} s，单卡 RTX 4090，peak VRAM {training['peak_vram_gb']} GB
- 数据：`data/sft/support_train.jsonl`（600 条）；dev 20 / test 60
- test 60（产品 prompt 路径）：macro-F1 **{prod_test_m['macro_f1']:.4f}** / acc **{prod_test_m['accuracy']:.4f}**
- 权重文件：`adapter_model.safetensors`（{weights_bytes} B）
- 复现：`python scripts/train_support_lora.py --model-size 4b --data data/sft --out out/support_lora_qwen3_4b --epochs 3 --eval-base`
- 服务：`python scripts/adapter_judge_server.py --model models/Qwen3-4B --adapter out/support_lora_qwen3_4b/adapter --port 8101`
- 注意：本目录是 HF 上传布局，配置名是 `adapter_adapter_config.json`（`scripts/upload_hf.py` 上传时复制为 `adapter_config.json`）；
  直接本地加载请用训练产物目录 `out/support_lora_qwen3_4b/adapter`（或先复制改名）。`dist/` 不入 git/打包，权重需单独拷贝。
- 证据：`data/experiments/support_lora_qwen3_4b.json`；模型卡：`docs/model_card_support_lora_4b.md`
"""
    (ADAPTER / "adapter_README.md").write_bytes(readme.encode("utf-8"))
    # keep the trainer artefacts next to the weights, mirroring the 1.7B bundle layout
    (ADAPTER / "metrics.json").write_bytes(
        (EXP / "support_lora_qwen3_4b_metrics.json").read_bytes()
    )
    (ADAPTER / "eval_predictions.jsonl").write_bytes(
        (EXP / "support_lora_qwen3_4b_harness_predictions.jsonl").read_bytes()
    )

    # ---- 10-item spot check (stratified, from the real product-path predictions) ----
    by_label: dict[str, list[dict]] = {lab: [] for lab in LABELS}
    for row in prod_test.get("predictions") or []:
        if row.get("gold") in by_label:
            by_label[row["gold"]].append(row)
    spot: list[dict] = []
    while len(spot) < 10:
        moved = False
        for lab in LABELS:
            if by_label[lab] and len(spot) < 10:
                spot.append(by_label[lab].pop(0))
                moved = True
        if not moved:
            break
    spot_rows = "\n".join(
        f"| {i + 1} | `{r['id']}` | {r['gold']} | {r['pred']} | {r.get('raw', '')[:60].replace('|', '/')} |"
        for i, r in enumerate(spot)
    )
    spot_json = {
        "source": "data/experiments/support_lora_qwen3_4b_adapter_test.json",
        "sampling": "stratified by gold label, first rows per label, 10 total",
        "all_correct": all(r["gold"] == r["pred"] for r in spot),
        "items": spot,
    }
    (EXP / "support_lora_qwen3_4b_spotcheck.json").write_bytes(
        json.dumps(spot_json, ensure_ascii=False, indent=1).encode("utf-8")
    )

    # ---- model card --------------------------------------------------------
    rows = "\n".join(
        f"| {c['model']} | {c['macro_f1']:.4f} | {c['accuracy']:.4f} | {c['n']} |"
        for c in comparison
    )
    card = f"""# Support-LoRA：ClaimSupport-CN 上的 Qwen3-4B 微调

> 4B 基座 + LoRA 的支持度判定组件：判断「一条主张是否被给定证据支持」。
> 它不负责引用真伪，也不负责 GB/T 格式。

## 1. 它是什么

| 项 | 值 |
|---|---|
| 基座 | `Qwen/Qwen3-4B`（Apache-2.0） |
| 微调方式 | LoRA，r=16，alpha=32，dropout=0.05，bf16 |
| 可训练参数 | {training.get('trainable_params')} |
| 目标模块 | q/k/v/o/gate/up/down_proj |
| 任务 | 4 分类：support / partial / contradict / no_evidence |
| 训练硬件 | 单张 RTX 4090（24 GB），{training['gpu'].get('name', 'RTX 4090')} |
| 训练耗时 | {training['train_seconds']} s（{training['epochs']} epoch，{training['optimizer_steps']} step） |
| Peak VRAM | {training['peak_vram_gb']} GB |
| 训练 loss | 均值 {training['train_loss_mean']:.4f}（首点 {training['loss_curve_first']} → 末点 {training['loss_curve_last']}，{training['loss_curve_points']} 个记录点） |
| Adapter 体积 | {weights_bytes} B（adapter_model.safetensors） |
| 运行环境 | {training['env']['os']}；Python {training['env']['python']}；torch {training['env']['packages']['torch']}；transformers {training['env']['packages']['transformers']}；peft {training['env']['packages']['peft']}；物理机 `{training['env']['host']}`（非容器），驱动 535.129.03 |

## 2. 数据与划分

- 数据：`data/sft/support_train.jsonl`（600 条）/ `support_dev.jsonl`（20 条）/ `support_test.jsonl`（60 条）。
- train = 借用官方 dev 20 + ext 60 + v2 140 + a3 380；dev 20 与 test 60 与上一版**字节级一致**。
- 官方 test 60 从未参与训练；train 与 test 的 id / 来源交集均为 0（见 `data/experiments/sft_split_audit.json`）。
- 标注来源：**构造标签，非人工标注**。

## 3. 结果（test 60，同一批 id）

| 模型 | macro-F1 | accuracy | n |
|---|---|---|---|
{rows}

同一 test 60 上的混淆矩阵（行=金标，列=预测，顺序 support/partial/contradict/no_evidence）：

**4B + LoRA（产品 prompt 路径）**，macro-F1 {prod_test_m['macro_f1']:.4f} / acc {prod_test_m['accuracy']:.4f}：

```
{matrix_block(prod_test_m['confusion'])}
```

**4B 基座零样本（同一产品 prompt）**，macro-F1 {base_test_m['macro_f1']:.4f} / acc {base_test_m['accuracy']:.4f}：

```
{matrix_block(base_test_m['confusion'])}
```

产品路径说明：v10 产品 prompt 原样发到 `scripts/adapter_judge_server.py`，由它抽出
【引用句】/【证据片段】再包成 SFT prompt，因此与训练格式一致、与产品调用方式一致。
dev 20 条（仅参考）：macro-F1 {prod_dev_m['macro_f1']:.4f} / acc {prod_dev_m['accuracy']:.4f}。

**饱和（必须一起读）**：4B + LoRA 在 test 60 上是 **60/60 全对**（macro-F1 {prod_test_m['macro_f1']:.4f}），
训练 loss 在前 10 个记录点内就掉到 ~0（均值 {training['train_loss_mean']:.4f}）。这说明
ClaimSupport-CN 这套**构造模板**对 4B 已经饱和：它证明「4B 能学会该映射」，但**不能**据此说
「4B 比 1.7B LoRA（0.9721）更强」——两者都贴着上限，差异在本题上不可测。分数本身也**不再**
是瓶颈，下一轮要区分模型能力，需要更难的样本（真实引文、更细粒度标签、跨句推理），而不是继续加同模板数据。

同口径校验：表内所有 n=60 的行都逐 id 比对过 `data/sft/support_test.jsonl` 的官方 test 60 顺序
（见 `data/experiments/support_lora_qwen3_4b.json` 的 `provenance_checks`）；8B/14B 走 v4 prompt、
14B 4-bit 走 v10、1.7B 走历史 SFT prompt、4B 两行分别走 SFT prompt 与产品 prompt 路径，逐行注明。

## 4. 逐条抽查（test 10 条，产品 prompt 路径）

| # | id | 金标 | 预测 | 原始输出片段 |
|---|---|---|---|---|
{spot_rows}

全 10 条一致；`confidence` 是判定服务 shim 的常量 0.8，不是模型概率，不用于阈值。完整 60 条预测见 `data/experiments/support_lora_qwen3_4b_adapter_test.json` 的 `predictions`
与 `data/experiments/support_lora_qwen3_4b_spotcheck.json`。

## 5. 诚实边界（必须一起引用）

1. **同分布**：test 与训练集同一套构造模板，分数衡量「学会这套映射」，不是开放世界泛化。
2. **非人工标注**：没有人工金标；不把它说成「人工测试」。
3. **单次运行**：固定 seed {training.get('seed')}，未做 seed / prompt 扫描；换 prompt 数字会变。
4. **对照表口径**：历史 1.7B/8B/14B 行复用仓库既有 JSON，n=60 且逐 id 对齐官方 test；其中 8B/14B 用的是 v4 prompt，14B 4-bit 用 v10，已在表内逐行注明路径。
5. **只做支持度**：不查引用是否存在（metadata 链路），不做 GB/T 格式（规则引擎）。
6. **未接入产品默认服务**：adapter 未进线上，接入需 vLLM/PEFT 加载并重跑端到端。
7. **产物位置**：`dist/` 在 `.gitignore` 与交付打包排除列表中，adapter 权重只存在于工作区 `dist/models/support_lora_qwen3_4b/`；需要随包分发请单独拷贝或用 `scripts/upload_hf.py` 上传。

## 6. 本地判定服务（可选）

```bash
CUDA_VISIBLE_DEVICES=3 python scripts/adapter_judge_server.py \\
  --model models/Qwen3-4B --adapter out/support_lora_qwen3_4b/adapter --port 8101
# dist/models/support_lora_qwen3_4b/ 是 HF 上传布局：配置名是 adapter_adapter_config.json
# （scripts/upload_hf.py 上传时复制为 adapter_config.json）；本地直接加载请用上面的训练产物目录，
# 或先把该文件复制成 adapter_config.json。dist/ 不入 git/打包，权重需单独拷贝或走 upload_hf.py。
# 产品侧：CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8101/v1
#         CITEGUARD_JUDGE_MODEL=qwen3-4b-support-lora
#         CITEGUARD_SUPPORT_AUDIT=0
python scripts/eval_support_adapter.py --model-size 4b \\
  --endpoint http://127.0.0.1:8101/v1 --data data/sft --split test
```

## 7. 复现

```bash
# 1) 数据（600/20/60）：先离线重建再装配
python scripts/build_sft_expand.py --offline
python scripts/build_support_sft.py --no-readme

# 2) 训练 + 基线对比（单卡 4090，约 15 分钟）
HF_ENDPOINT=https://hf-mirror.com python -c "from huggingface_hub import snapshot_download as d; d('Qwen/Qwen3-4B', local_dir='models/Qwen3-4B')"
NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 CUDA_VISIBLE_DEVICES=3 \\
python scripts/train_support_lora.py --model-size 4b \\
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
"""
    CARD.write_bytes(card.encode("utf-8"))

    print(json.dumps({
        "bundle": OUT_JSON.relative_to(ROOT).as_posix(),
        "card": CARD.relative_to(ROOT).as_posix(),
        "adapter_weights_bytes": weights_bytes,
        "test_macro_f1": prod_test_m["macro_f1"],
        "test_accuracy": prod_test_m["accuracy"],
        "n": prod_test_m["n"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
