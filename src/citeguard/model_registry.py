"""Registry of support-judge models (hosted, local bf16/4-bit, LoRA adapter)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import config

DEFAULT_MODELS = [
    {"id": "hosted-deepseek", "label": "云端 DeepSeek", "base_url": "https://api.deepseek.com/v1",
     "model": "deepseek-chat", "source": "hosted", "license": "proprietary API",
     "audit_style": "v3", "note": "默认；无需本地 GPU"},
    {"id": "local-qwen3-14b", "label": "本地 Qwen3-14B（bf16）", "base_url": "http://127.0.0.1:8097/v1",
     "model": "qwen3-14b", "source": "local", "license": "Apache-2.0",
     "audit_style": "v2", "note": "需在 lmh 启动 14B 服务"},
    {"id": "local-qwen3-14b-4bit", "label": "本地 Qwen3-14B（4-bit）", "base_url": "http://127.0.0.1:8096/v1",
     "model": "qwen3-14b", "source": "local", "license": "Apache-2.0",
     "audit_style": "v2", "note": "显存约 11.7 GB"},
    {"id": "local-lora-1.7b", "label": "本地 LoRA Qwen3-1.7B adapter", "base_url": "http://127.0.0.1:8100/v1",
     "model": "support-lora", "source": "adapter", "license": "Apache-2.0（adapter）",
     "audit_style": "off", "note": "需要 adapter 服务；16 tokens 直接出 JSON"},
]


def registry_path() -> Path:
    override = os.environ.get("CITEGUARD_MODEL_REGISTRY")
    if override:
        return Path(override)
    return config.DATA_DIR / "judge_models.json"


def load_registry() -> dict:
    path = registry_path()
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    models = {m["id"]: dict(m) for m in DEFAULT_MODELS}
    for m in data.get("models") or []:
        if m.get("id"):
            models[m["id"]] = {**models.get(m["id"], {}), **m}
    active = data.get("active") or None
    if active not in models:
        active = None
    return {"models": list(models.values()), "active": active}


def save_registry(models: list[dict], active: str | None) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"models": models, "active": active}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def get_model(model_id: str) -> dict | None:
    for m in load_registry()["models"]:
        if m["id"] == model_id:
            return m
    return None


def active_model() -> dict | None:
    data = load_registry()
    return get_model(data["active"]) if data.get("active") else None


def set_active(model_id: str | None) -> dict:
    data = load_registry()
    ids = {m["id"] for m in data["models"]}
    if model_id and model_id not in ids:
        raise ValueError("unknown model: " + str(model_id))
    save_registry(data["models"], model_id)
    return load_registry()
