#!/bin/bash
cd /data1/GYX/citeguard
export LD_LIBRARY_PATH=$(ls -d /data1/GYX/miniconda3/envs/llm/lib/python3.9/site-packages/nvidia/*/lib | tr '\n' ':')$LD_LIBRARY_PATH
export PYTHONPATH=src
run() {
  tag=$1; port=$2; model=$3; shift 3
  CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:$port/v1 CITEGUARD_JUDGE_MODEL=$model \
    venv/bin/python -u scripts/eval_support_prompt.py --split dev --tag "$tag" "$@" \
    > logs/eval_$tag.log 2>&1
}
run qwen3-8b-v4-v3-dev 8098 qwen3-8b --prompt v4 --audit-style v3
run qwen3-8b-v7-v3-dev 8098 qwen3-8b --prompt v7 --audit-style v3
run qwen3-14b-v7-v3-dev 8097 qwen3-14b --prompt v7 --audit-style v3
