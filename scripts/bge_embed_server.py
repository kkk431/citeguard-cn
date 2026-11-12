"""Minimal OpenAI-compatible embedding server for BAAI/bge-m3.

Run on the GPU host:
  BGE_MODEL_PATH=/path/to/bge-m3 CUDA_VISIBLE_DEVICES=3   python scripts/bge_embed_server.py --port 8090
"""
import argparse
import os
from typing import List, Optional, Union

import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8090)
ap.add_argument("--model", default=os.environ.get("BGE_MODEL_PATH", "BAAI/bge-m3"))
args = ap.parse_args()

model = SentenceTransformer(args.model, device="cuda")
app = FastAPI()


class EmbeddingRequest(BaseModel):
    input: Union[List[str], str]
    model: Optional[str] = None


@app.get("/health")
def health():
    return {"ok": True, "model": args.model, "cuda": torch.cuda.is_available()}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "bge-m3", "object": "model"}]}


@app.post("/v1/embeddings")
def embeddings(req: EmbeddingRequest):
    texts = [req.input] if isinstance(req.input, str) else req.input
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=16).tolist()
    return {
        "object": "list",
        "model": req.model or "bge-m3",
        "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vecs)],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
