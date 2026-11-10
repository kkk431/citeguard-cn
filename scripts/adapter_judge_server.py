"""OpenAI-compatible judge server backed by the Qwen3-1.7B support LoRA adapter.

The product judge sends a long v10 prompt with ``【引用句】...【证据片段】...`` at
the end. The adapter was fine-tuned on a much shorter instruction, so this
server extracts the two fields and re-wraps them in the SFT prompt before
generating. It is a *format adapter*, not a new model.

Usage on lmh:
    CUDA_VISIBLE_DEVICES=3 venv/bin/python scripts/adapter_judge_server.py \
        --model models/Qwen3-1.7B --adapter out/support_lora/adapter --port 8101
"""
from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

LABELS = ["support", "partial", "contradict", "no_evidence"]
SYS = (
    "你是学术引文核验员。判断【证据片段】是否支持【引用句】，四选一："
    "support（完全支持）、partial（部分支持）、contradict（矛盾）、no_evidence（证据不足）。"
    '只输出 JSON：{"label": "..."}。'
)

_model = None
_tok = None
_lock = threading.Lock()


def load(model_path: str, adapter_path: str) -> None:
    global _model, _tok
    _tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.bfloat16, trust_remote_code=True)
    _model = PeftModel.from_pretrained(base, adapter_path).to("cuda").eval()


def parse_fields(content: str) -> tuple[str, str] | None:
    """Pull claim/evidence out of the product prompt (fields are at the end)."""
    tail = content.rsplit("【引用句】", 1)
    if len(tail) != 2:
        return None
    rest = tail[1]
    if "【证据片段】" not in rest:
        return None
    claim, evidence = rest.split("【证据片段】", 1)
    claim = claim.strip().split("\n")[0].strip()
    evidence = evidence.strip()
    if not claim or not evidence:
        return None
    return claim, evidence


def classify(claim: str, evidence: str) -> str:
    messages = [{"role": "system", "content": SYS}, {"role": "user", "content": f"【引用句】{claim}\n【证据片段】{evidence}"}]
    text = _tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    ids = _tok(text, return_tensors="pt").to("cuda")
    with _lock, torch.inference_mode():
        out = _model.generate(**ids, max_new_tokens=16, do_sample=False)
    reply = _tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    m = re.search(r'"label"\s*:\s*"(support|partial|contradict|no_evidence)"', reply)
    if m:
        return m.group(1)
    for label in LABELS:
        if label in reply:
            return label
    return "no_evidence"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter logs
        pass

    def _send(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/v1/models":
            self._send({"object": "list", "data": [{"id": "qwen3-1.7b-support-lora", "object": "model"}]})
        else:
            self._send({"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
            content = ""
            for msg in reversed(payload.get("messages") or []):
                if msg.get("role") == "user":
                    content = msg.get("content") or ""
                    break
            fields = parse_fields(content)
            if not fields:
                reply = json.dumps({"label": "no_evidence", "reason": "字段未解析"})
            else:
                label = classify(*fields)
                reply = json.dumps({"label": label, "confidence": 0.8, "reason": "SFT adapter verdict", "evidence_quote": ""}, ensure_ascii=False)
            self._send({"object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}]})
        except Exception as exc:  # noqa: BLE001 - keep the server alive for batch evals
            self._send({"error": str(exc), "choices": [{"message": {"content": '{"label":"no_evidence"}'}}]})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/Qwen3-1.7B")
    ap.add_argument("--adapter", default="out/support_lora/adapter")
    ap.add_argument("--port", type=int, default=8101)
    args = ap.parse_args()
    load(args.model, args.adapter)
    print("ready on", args.port, flush=True)
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
