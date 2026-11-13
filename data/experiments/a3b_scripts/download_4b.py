import os
import sys

from huggingface_hub import snapshot_download

path = snapshot_download(
    "Qwen/Qwen3-4B",
    local_dir="/data1/GYX/citeguard/models/Qwen3-4B",
    max_workers=1,
    resume_download=True,
)
print("DONE", path, flush=True)
sys.exit(0 if os.path.exists(os.path.join(path, "config.json")) else 1)
