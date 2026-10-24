#!/bin/bash
cd /data1/GYX/citeguard
export LD_LIBRARY_PATH=$(ls -d /data1/GYX/miniconda3/envs/llm/lib/python3.9/site-packages/nvidia/*/lib | tr '\n' ':')$LD_LIBRARY_PATH
export PYTHONPATH=src
CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8098/v1 CITEGUARD_JUDGE_MODEL=qwen3-8b \
  venv/bin/python -u scripts/eval_support_prompt.py --split dev --tag qwen3-8b-v4-v2-vote3-dev \
  --prompt v4 --audit-style v2 --votes 3 --temperature 0.7 > logs/eval_qwen3-8b-v4-v2-vote3-dev.log 2>&1
CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8097/v1 CITEGUARD_JUDGE_MODEL=qwen3-14b \
  venv/bin/python -u scripts/eval_support_prompt.py --split test --tag qwen3-14b-v4-v2-test \
  --prompt v4 --audit-style v2 > logs/eval_qwen3-14b-v4-v2-test.log 2>&1
