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

echo "[1/4] CLI demo on the sample paper"
$PY -m citeguard.cli --input web/static/samples/sample_paper.txt --out out/demo

echo "[2/4] CiteBench-CN evaluation"
$PY scripts/evaluate_citebench.py --limit 0 --out data/citebench_cn/results.json

echo "[3/4] artifact consistency check"
$PY scripts/verify_artifacts.py || echo "[warn] verify_artifacts reported issues; inspect the output above"

echo "[4/4] offline test suite"
if $PY -c "import pytest" >/dev/null 2>&1; then
  $PY -m pytest tests -q
else
  echo "[skip] pytest not installed; pip install pytest"
fi

if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  echo "[optional] DeepSeek baseline (prompt v3)"
  $PY scripts/deepseek_baseline.py
else
  echo "[skip] DEEPSEEK_API_KEY not set; claim support / DeepSeek baseline not run"
fi

echo "evidence index for every reported number: data/experiments/README.md"
echo "done. open out/demo/report.html or run:"
echo "  PYTHONPATH=src:.pylibs $PY -m uvicorn web.app:app --port 8000"
