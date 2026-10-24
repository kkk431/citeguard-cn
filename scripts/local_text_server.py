"""Minimal OpenAI-compatible server for one local Hugging Face text model.

Used to measure open-source judges (Qwen2.5/Qwen3) on ClaimSupport-CN without
a hosted API. One model in memory, one request at a time (lab/demo server).

Environment:
    MODEL_PATH=/data1/GYX/citeguard/models/Qwen3-8B
    PORT=8098
    CUDA_VISIBLE_DEVICES=1
    THINKING=0            # Qwen3 hybrid reasoning; 0 for fast JSON judging
    MAX_NEW_TOKENS=400

Endpoints: GET /health, GET /v1/models, POST /v1/chat/completions
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_PATH = os.environ.get("MODEL_PATH", "/data1/GYX/citeguard/models/Qwen3-8B")
PORT = int(os.environ.get("PORT", "8098"))
THINKING = os.environ.get("THINKING", "0") == "1"
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "400"))
DEVICE_MAP = os.environ.get("DEVICE_MAP", "cuda")

app = FastAPI(title="local text judge", version="0.1")
_lock = threading.Lock()
_model = None
_tokenizer = None


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "local"
    messages: list[Message]
    temperature: float = 0.0
    max_tokens: int = MAX_NEW_TOKENS
    top_p: float = 1.0


def _load() -> None:
    global _model, _tokenizer
    if _model is not None:
        return
    print(f"[server] loading {MODEL_PATH} thinking={THINKING}", flush=True)
    started = time.time()
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map=DEVICE_MAP,
        trust_remote_code=True,
    )
    _model.eval()
    print(f"[server] loaded in {time.time() - started:.1f}s", flush=True)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": MODEL_PATH, "loaded": _model is not None, "thinking": THINKING}


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {"data": [{"id": MODEL_PATH, "object": "model"}]}


@app.post("/v1/chat/completions")
def chat(req: ChatRequest) -> dict[str, Any]:
    _load()
    started = time.perf_counter()
    messages = [m.model_dump() for m in req.messages]
    kwargs: dict[str, Any] = {"tokenize": False, "add_generation_prompt": True}
    try:
        text = _tokenizer.apply_chat_template(messages, enable_thinking=THINKING, **kwargs)
    except TypeError:
        text = _tokenizer.apply_chat_template(messages, **kwargs)
    inputs = _tokenizer([text], return_tensors="pt").to(_model.device)
    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": int(req.max_tokens),
        "do_sample": req.temperature > 0,
        "top_p": req.top_p,
    }
    if req.temperature > 0:
        gen_kwargs["temperature"] = req.temperature
    with _lock, torch.inference_mode():
        output = _model.generate(**inputs, **gen_kwargs)
    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    content = _tokenizer.decode(new_tokens, skip_special_tokens=True)
    elapsed = time.perf_counter() - started
    return {
        "id": "local-" + str(int(time.time() * 1000)),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_PATH,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": int(inputs["input_ids"].shape[1]), "completion_tokens": int(new_tokens.shape[0])},
        "elapsed_s": round(elapsed, 2),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
