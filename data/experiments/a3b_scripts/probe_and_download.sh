#!/usr/bin/env bash
# A3b step 1: environment probe + start Qwen3-4B download in the background.
set -u
BASE=/data1/GYX/citeguard
mkdir -p "$BASE/a3b/data" "$BASE/a3b/scripts" "$BASE/a3b/src" "$BASE/a3b/out" "$BASE/a3b/logs"
echo "== python stack =="
"$BASE/venv/bin/python" - <<'PY'
import bitsandbytes, huggingface_hub, torch, transformers, peft
print("torch", torch.__version__, "cuda", torch.version.cuda)
print("transformers", transformers.__version__, "peft", peft.__version__)
print("bitsandbytes", bitsandbytes.__version__, "hf_hub", huggingface_hub.__version__)
PY
echo "== gpu =="
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader
echo "== existing 4B? =="
ls "$BASE/models" | grep -i 4b || echo "no 4B dir"
echo "== start download (hf-mirror) =="
cd "$BASE/a3b"
HF_ENDPOINT=https://hf-mirror.com nohup "$BASE/venv/bin/python" -c "from huggingface_hub import snapshot_download; p=snapshot_download('Qwen/Qwen3-4B', local_dir='$BASE/models/Qwen3-4B'); print('DONE', p, flush=True)" > "$BASE/a3b/logs/download_4b.log" 2>&1 &
echo "download_pid=$!"
