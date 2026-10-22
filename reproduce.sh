#!/usr/bin/env bash
# One-command reproduction for CiteGuard-CN.
# Works locally (PYTHONPATH=src) and on the server (PYTHONPATH=src:.pylibs).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if [ -d .pylibs ]; then
  export PYTHONPATH="src:.pylibs"
else
  export PYTHONPATH="src"
fi

echo "[1/3] CLI demo on the sample paper"
$PY -m citeguard.cli --input web/static/samples/sample_paper.txt --out out/demo

echo "[2/3] CiteBench-CN evaluation"
$PY scripts/evaluate_citebench.py --limit 0 --out data/citebench_cn/results.json

echo "[3/3] artifact consistency check"
$PY scripts/verify_artifacts.py || echo "[warn] verify_artifacts reported issues; inspect the output above"

if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  echo "[optional] DeepSeek baseline (prompt v3)"
  $PY scripts/deepseek_baseline.py
else
  echo "[skip] DEEPSEEK_API_KEY not set; claim support / DeepSeek baseline not run"
fi

echo "done. open out/demo/report.html or run:"
echo "  PYTHONPATH=src${PWD:+.pylibs} $PY -m uvicorn web.app:app --port 8000"
