#!/usr/bin/env bash
# A3b: train Qwen3-4B LoRA on the expanded ClaimSupport-CN SFT split (GPU 3 only).
BASE=/data1/GYX/citeguard
cd "$BASE/a3b" || exit 1
export CUDA_VISIBLE_DEVICES=3
export PYTHONPATH="$BASE/a3b/src"
export TOKENIZERS_PARALLELISM=false
# RTX 4090 (no NVLink): transformers/accelerate refuses to start without these.
export NCCL_P2P_DISABLE=1
export NCCL_IB_DISABLE=1
mkdir -p logs out
{
  echo "=== $(date -Is) start ==="
  echo "cmd: train_support_lora.py --model-size 4b --data $BASE/a3b/data/sft --out $BASE/a3b/out/support_lora_qwen3_4b --epochs 3 --eval-base --seed 20261114"
  nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader
  "$BASE/venv/bin/python" scripts/train_support_lora.py \
    --model-size 4b --models-dir "$BASE/models" \
    --data "$BASE/a3b/data/sft" --out "$BASE/a3b/out/support_lora_qwen3_4b" \
    --epochs 3 --eval-base --seed 20261114
  echo "TRAIN_EXIT=$?"
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
  echo "=== $(date -Is) done ==="
} 2>&1 | tee -a logs/train_4b.log
