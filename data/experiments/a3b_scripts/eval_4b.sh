#!/usr/bin/env bash
# A3b: product-prompt evaluation of the 4B LoRA adapter and the 4B base (zero-shot).
# Each case starts its own judge server on GPU 3, runs test+dev, then kills it.
BASE=/data1/GYX/citeguard
cd "$BASE/a3b" || exit 1
export CUDA_VISIBLE_DEVICES=3
export PYTHONPATH="$BASE/a3b/src"
PY="$BASE/venv/bin/python"
LOG=logs/eval_4b.log
MODEL="$BASE/models/Qwen3-4B"
mkdir -p logs out

wait_ready() {
  for _ in $(seq 1 150); do
    if curl -s -o /dev/null "http://127.0.0.1:$1/v1/models"; then return 0; fi
    sleep 2
  done
  echo "server not ready on port $1"
  return 1
}

run_case() {  # name port [server flags...]
  local name=$1 port=$2
  shift 2
  echo "=== $(date -Is) case=$name port=$port flags=$* ==="
  "$PY" scripts/adapter_judge_server.py --model "$MODEL" --port "$port" "$@" >> "$LOG" 2>&1 &
  local pid=$!
  if ! wait_ready "$port"; then
    echo "FAILED to start $name"
    kill "$pid" 2>/dev/null
    return 1
  fi
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tee -a "$LOG"
  "$PY" scripts/eval_support_adapter.py --model-size 4b \
      --endpoint "http://127.0.0.1:$port/v1" --data "$BASE/a3b/data/sft" \
      --split test --out "out/eval_${name}_test.json" 2>&1 | tee -a "$LOG"
  "$PY" scripts/eval_support_adapter.py --model-size 4b \
      --endpoint "http://127.0.0.1:$port/v1" --data "$BASE/a3b/data/sft" \
      --split dev --out "out/eval_${name}_dev.json" 2>&1 | tee -a "$LOG"
  kill "$pid" 2>/dev/null
  wait "$pid" 2>/dev/null
  sleep 5
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tee -a "$LOG"
}

run_case adapter 8101 --adapter "$BASE/a3b/out/support_lora_qwen3_4b/adapter"
run_case base 8102 --no-adapter
echo "=== $(date -Is) eval done; gpu state ==="
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tee -a "$LOG"
