"""Minimal OpenAI-compatible vision server for Qwen2.5-VL (runs on the GPU host).

Endpoints:
  GET /health
  GET /v1/models
  POST /v1/chat/completions   (content parts: {"type":"text","text":...} and
                               {"type":"image_url","image_url":{"url":"data:image/png;base64,..."}})

This is a lab/demo server: one model in memory, one request at a time.
"""

from __future__ import annotations

import base64
import io
import os
import threading

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel
from transformers import AutoConfig, AutoProcessor

MODEL_PATH = os.environ.get("VL_MODEL_PATH", "/data1/GYX/citeguard/models/Qwen2.5-VL-7B-Instruct")
MODEL_NAME = os.environ.get("VL_MODEL_NAME", "qwen2.5-vl-7b")
PORT = int(os.environ.get("PORT", "8099"))
app = FastAPI(title="citeguard-vl", version="0.1.0")
_lock = threading.Lock()
_model = None
_processor = None


class ChatRequest(BaseModel):
    model: str = "qwen2.5-vl-7b"
    messages: list[dict]
    max_tokens: int = 256
    temperature: float = 0.0


def _load() -> None:
    global _model, _processor
    if _model is not None:
        return
    arch = (AutoConfig.from_pretrained(MODEL_PATH).architectures or [""])[0]
    if "Qwen3VL" in arch:
        from transformers import Qwen3VLForConditionalGeneration as ModelCls
    else:
        from transformers import Qwen2_5_VLForConditionalGeneration as ModelCls
    _model = ModelCls.from_pretrained(
        MODEL_PATH, torch_dtype=torch.bfloat16, device_map="cuda"
    ).eval()
    _processor = AutoProcessor.from_pretrained(MODEL_PATH)


def _image_from_data_url(url: str) -> Image.Image:
    if not url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="only data:image/* URLs are supported")
    _, b64 = url.split(",", 1)
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


def _build_messages(messages: list[dict]) -> list[dict]:
    out = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": msg.get("role", "user"), "content": [{"type": "text", "text": content}]})
            continue
        parts = []
        for part in content or []:
            if part.get("type") == "text":
                parts.append({"type": "text", "text": part.get("text", "")})
            elif part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                parts.append({"type": "image", "image": _image_from_data_url(url)})
            else:
                raise HTTPException(status_code=400, detail=f"unsupported part: {part.get('type')}")
        out.append({"role": msg.get("role", "user"), "content": parts})
    return out


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": MODEL_PATH, "loaded": _model is not None}


@app.get("/v1/models")
def models() -> dict:
    return {"data": [{"id": "qwen2.5-vl-7b", "object": "model"}]}


@app.post("/v1/chat/completions")
def chat(req: ChatRequest) -> dict:
    _load()
    messages = _build_messages(req.messages)
    if not any(c["type"] == "image" for m in messages for c in m["content"]):
        raise HTTPException(status_code=400, detail="an image is required")
    text = _processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs = [c["image"] for m in messages for c in m["content"] if c["type"] == "image"]
    inputs = _processor(text=[text], images=image_inputs, padding=True, return_tensors="pt").to(_model.device)
    with _lock, torch.no_grad():
        generated = _model.generate(**inputs, max_new_tokens=min(req.max_tokens, 512), do_sample=False)
    trimmed = generated[:, inputs.input_ids.shape[1]:]
    answer = _processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
    return {
        "id": "chatcmpl-vl",
        "object": "chat.completion",
        "model": MODEL_NAME,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
