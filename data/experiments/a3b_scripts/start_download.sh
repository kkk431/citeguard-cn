#!/usr/bin/env bash
# Resume the Qwen3-4B download (hf-mirror, plain HTTP, single worker) in the background.
BASE=/data1/GYX/citeguard
cd "$BASE/a3b" || exit 1
pkill -f "snapshot_download('Qwen/Qwen3-4B'" 2>/dev/null
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1
nohup "$BASE/venv/bin/python" "$BASE/a3b/scripts/download_4b.py" > "$BASE/a3b/logs/download_4b.log" 2>&1 &
echo "resume_pid=$!"
