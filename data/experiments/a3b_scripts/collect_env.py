"""Record the exact environment of the A3b Qwen3-4B run as JSON (executed on the GPU host).

Writes data/experiments/support_lora_qwen3_4b_env.json next to the other evidence files.
Only measured facts: versions from the interpreter that trained the adapter, GPU from
nvidia-smi, and the trainable-parameter line parsed out of the real training log.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

BASE = Path("/data1/GYX/citeguard")
LOG = BASE / "a3b" / "logs" / "train_4b.log"
LAUNCHER = BASE / "a3b" / "scripts" / "train_4b.sh"
OUT = Path(__file__).resolve().parent / "support_lora_qwen3_4b_env.json"


def sh(cmd: str) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as exc:  # noqa: BLE001 - report, do not crash the evidence run
        return f"<error: {exc}>"


def version(mod: str) -> str:
    try:
        return __import__(mod).__version__
    except Exception as exc:  # noqa: BLE001
        return f"<missing: {exc}>"


def main() -> int:
    log_text = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
    trainable = re.search(
        r"trainable params: ([\d,]+) \|\| all params: ([\d,]+) \|\| trainable%: ([\d.]+)", log_text
    )
    seed = re.search(r"--seed\s+(\d+)", LAUNCHER.read_text(encoding="utf-8") if LAUNCHER.exists() else "")
    total_loss = re.search(r"'train_loss': ([0-9.]+)", log_text)
    runtime = re.search(r"'train_runtime': ([0-9.]+)", log_text)
    loss_points = re.findall(r"'loss': ([0-9.]+)", log_text)
    model_dir = BASE / "models" / "Qwen3-4B"
    env = {
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "container": {
            "in_docker": Path("/.dockerenv").exists(),
            "hostname": platform.node(),
            "image_hint": os.environ.get("IMAGE_NAME", ""),
        },
        "os": platform.platform(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "packages": {m: version(m) for m in ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "datasets")},
        "cuda": sh("nvcc --version | tail -1") if sh("which nvcc") else "<no nvcc>",
        "gpu": {
            "nvidia_smi": sh("nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader"),
            "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
        },
        "model": {
            "dir": str(model_dir),
            "bytes": int(sh(f"du -sb {model_dir} | cut -f1")) if model_dir.exists() else None,
            "hf_endpoint": os.environ.get("HF_ENDPOINT", ""),
        },
        "train": {
            "launcher": str(LAUNCHER),
            "seed_arg": int(seed.group(1)) if seed else None,
            "trainable_params": (
                f"{int(trainable.group(1).replace(',', '')):,} / {int(trainable.group(2).replace(',', '')):,}"
                f" ({trainable.group(3)}%)"
                if trainable
                else None
            ),
            "trainable_params_raw": (
                {
                    "trainable": int(trainable.group(1).replace(",", "")),
                    "total": int(trainable.group(2).replace(",", "")),
                    "percent": float(trainable.group(3)),
                }
                if trainable
                else None
            ),
            "log": str(LOG),
            "log_bytes": LOG.stat().st_size if LOG.exists() else None,
            "train_runtime_sec": float(runtime.group(1)) if runtime else None,
            "train_loss_mean": float(total_loss.group(1)) if total_loss else None,
            "loss_curve": [float(v) for v in loss_points],
            "loss_curve_first": loss_points[0] if loss_points else None,
            "loss_curve_last": loss_points[-1] if loss_points else None,
        },
    }
    OUT.write_bytes(json.dumps(env, ensure_ascii=False, indent=1).encode("utf-8"))
    print(json.dumps(env, ensure_ascii=False, indent=1)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
