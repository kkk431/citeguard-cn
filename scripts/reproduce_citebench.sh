#!/usr/bin/env bash
# Reproduce the CiteBench-CN benchmark part end to end (dataset -> evaluation -> checks).
#
# Works both on the dev machine (src/ layout) and on the server (.pylibs/ layout).
# DeepSeek baseline is optional: it only runs when DEEPSEEK_API_KEY is exported.
#
#   bash scripts/reproduce_citebench.sh
#
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d ".pylibs" ]; then
  export PYTHONPATH=".pylibs:."
else
  export PYTHONPATH="src"
fi
echo "[env] PYTHONPATH=$PYTHONPATH"

echo "[1/4] build CiteBench-CN (seed=20261022; rebuild must keep the same SHA-256)"
python3 scripts/build_citebench.py

echo "[2/4] evaluate with the current verifier (v1.1) -> results.json + eval_predictions.csv"
python3 scripts/evaluate_citebench.py

echo "[3/4] verify dataset/results/baseline consistency"
python3 scripts/verify_artifacts.py

echo "[4/4] optional DeepSeek baseline (fair, frozen prompt)"
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  python3 scripts/deepseek_baseline.py
else
  echo "[skip] DEEPSEEK_API_KEY not set; deepseek_results.json / DeepSeek row left unchanged"
fi

echo "[done] data/citebench_cn/results.json is up to date"
