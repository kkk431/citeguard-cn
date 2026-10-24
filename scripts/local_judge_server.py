"""Local OpenAI-compatible chat-completions server for the support judge.

Run an open-source model on a local GPU and point CiteGuard at it::

    python scripts/local_judge_server.py \
        --model-path /path/to/Qwen2.5-3B-Instruct \
        --device cuda:0 --port 8099

    export CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8099/v1
    export CITEGUARD_JUDGE_MODEL=qwen2.5-3b-instruct
    PYTHONPATH=src python scripts/evaluate_support.py --limit 100

This is a minimal server (one request at a time, greedy decoding) meant for
evaluation and small deployments; for production throughput use vLLM / Ollama
and keep the same ``/v1`` contract.
"""
from __future__ import annotations

import argparse
import os
import threading
import time
import uuid
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="CiteGuard local judge", version="0.1.0")

_state: dict = {"model": None, "tok": None, "name": "", "lock": threading.Lock()}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: list[ChatMessage]
    temperature: Optional[float] = 0.0
    max_tokens: Optional[int] = 400
    top_p: Optional[float] = None
    stream: Optional[bool] = False


@app.get("/health")
def health():
    return {
        "ok": _state["model"] is not None,
        "model": _state["name"],
        "device": os.environ.get("CITEGUARD_LOCAL_DEVICE", "cuda:0"),
    }


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": _state["name"] or "local", "object": "model"}]}


@app.post("/v1/chat/completions")
def chat(req: ChatRequest):
    model, tok = _state["model"], _state["tok"]
    if model is None or tok is None:
        return {"error": "model not loaded"}, 503
    prompt = tok.apply_chat_template(
        [m.model_dump() for m in req.messages], tokenize=False, add_generation_prompt=True
    )
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    max_new = int(req.max_tokens or 400)
    with _state["lock"]:
        out = model.generate(
            **inputs,
            max_new_tokens=max_new,
            do_sample=False,
            temperature=None,
            top_p=None,
        )
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    text = tok.decode(new_tokens, skip_special_tokens=True)
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model or _state["name"],
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": int(inputs["input_ids"].shape[1]),
            "completion_tokens": int(new_tokens.shape[0]),
            "total_tokens": int(inputs["input_ids"].shape[1] + new_tokens.shape[0]),
        },
    }


def load_model(path: str, device: str, dtype: str) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"[local-judge] loading {path} on {device} ({dtype})", flush=True)
    tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        path, torch_dtype=getattr(torch, dtype), local_files_only=True
    )
    model = model.to(device).eval()
    _state.update(
        {
            "model": model,
            "tok": tok,
            "name": os.environ.get("CITEGUARD_LOCAL_MODEL_NAME") or os.path.basename(path.rstrip("/")),
        }
    )
    print(f"[local-judge] ready on {next(model.parameters()).device}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-path", default=os.environ.get("CITEGUARD_LOCAL_MODEL_PATH", ""))
    ap.add_argument("--device", default=os.environ.get("CITEGUARD_LOCAL_DEVICE", "cuda:0"))
    ap.add_argument("--dtype", default=os.environ.get("CITEGUARD_LOCAL_DTYPE", "float16"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()
    if not args.model_path:
        ap.error("--model-path (or CITEGUARD_LOCAL_MODEL_PATH) is required")
    os.environ.setdefault("CITEGUARD_LOCAL_DEVICE", args.device)
    load_model(args.model_path, args.device, args.dtype)
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
