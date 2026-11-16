"""LongCite-llama3.1-8b spike: sentence-level citation generation on LongCite-45k samples.

This is a *research spike*, not product code. It runs the public LongCite model on a
small, fixed sample of LongCite-45k and reports:

- how many ``<statement>...</statement>`` blocks the model emits and how many carry
  ``<cite>[a-b]</cite>`` markers,
- a document-level citation P/R/F1 proxy against the dataset's reference response
  (the official LongCite metric uses a GPT-4o judge; we do not have that judge here,
  so this proxy is reported as a proxy, never as the official score),
- latency, generated tokens and throughput.

Output: JSON with per-sample rows and aggregate metrics.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = Path(r"D:\Temp\citeguard_e3\longcite\long_head.jsonl")
CITE_RE = re.compile(r"<cite>(.*?)</cite>", re.DOTALL)
SPAN_RE = re.compile(r"\[(\d+)-(\d+)\]")
STATEMENT_RE = re.compile(r"<statement>(.*?)</statement>", re.DOTALL)


def load_rows(path: Path, limit: int, max_prompt_chars: int) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # last line of a range download may be truncated
            if len(row.get("prompt", "")) <= max_prompt_chars:
                rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def doc_ids(text: str) -> tuple[set[int], int]:
    spans = []
    for block in CITE_RE.findall(text or ""):
        spans.extend((int(a), int(b)) for a, b in SPAN_RE.findall(block))
    ids = set()
    invalid = 0
    for a, b in spans:
        if a > b:
            invalid += 1
            continue
        ids.update(range(a, b + 1))
    return ids, invalid


def statement_stats(text: str) -> dict:
    statements = [s.strip() for s in STATEMENT_RE.findall(text or "") if s.strip()]
    with_cite = [s for s in statements if CITE_RE.search(s)]
    spans = []
    for s in statements:
        for block in CITE_RE.findall(s):
            spans.extend(SPAN_RE.findall(block))
    return {
        "n_statements": len(statements),
        "n_statements_with_cite": len(with_cite),
        "n_citation_spans": len(spans),
        "n_statements": len(statements),
    }


def pick_balanced(rows: list[dict], n: int) -> list[dict]:
    zh = [r for r in rows if re.search(r"[\u4e00-\u9fff]", r["prompt"][-400:])]
    en = [r for r in rows if not re.search(r"[\u4e00-\u9fff]", r["prompt"][-400:])]
    half = n // 2
    picked = zh[:half] + en[: n - half]
    if len(picked) < n:
        picked += [r for r in rows if r not in picked][: n - len(picked)]
    return picked[:n]


def generate_one(model, tok, prompt: str, max_input_tokens: int, max_new_tokens: int,
                 device: str) -> tuple[str, dict]:
    ids = tok.encode(prompt, add_special_tokens=True)
    truncated = False
    if len(ids) > max_input_tokens:
        # keep the instruction head and the question tail; the middle is document text
        head = ids[:512]
        tail = ids[-(max_input_tokens - 512):]
        ids = head + tail
        truncated = True
    input_ids = torch.tensor([ids], dtype=torch.long, device=device)
    t0 = time.perf_counter()
    with torch.inference_mode():
        out = model.generate(
            input_ids,
            attention_mask=torch.ones_like(input_ids),
            max_new_tokens=max_new_tokens,
            do_sample=False,
            use_cache=True,
            pad_token_id=tok.eos_token_id,
        )
    dt = time.perf_counter() - t0
    gen_ids = out[0, len(ids):].tolist()
    text = tok.decode(gen_ids, skip_special_tokens=True)
    return text, {
        "prompt_tokens": len(ids),
        "generated_tokens": len(gen_ids),
        "truncated_prompt": truncated,
        "latency_s": round(dt, 3),
        "tokens_per_s": round(len(gen_ids) / dt, 3) if dt > 0 else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--model", type=Path, default=Path(r"D:\Temp\citeguard_e3\longcite_llama"))
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--max-prompt-chars", type=int, default=6000)
    ap.add_argument("--max-input-tokens", type=int, default=3000)
    ap.add_argument("--max-new-tokens", type=int, default=220)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "experiments" / "longcite_spike.json")
    ap.add_argument("--threads", type=int, default=16)
    args = ap.parse_args()

    torch.set_num_threads(args.threads)
    device = "cpu"
    rows = load_rows(args.data, args.n * 4, args.max_prompt_chars)
    picked = pick_balanced(rows, args.n)
    if not picked:
        print("no usable samples", file=sys.stderr)
        return 2

    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(str(args.model), trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model), torch_dtype=torch.bfloat16, low_cpu_mem_usage=True,
        trust_remote_code=False,
    )
    model.eval()
    load_s = time.perf_counter() - t0
    n_params = sum(p.numel() for p in model.parameters())

    results = []
    for i, row in enumerate(picked, 1):
        text, stats = generate_one(model, tok, row["prompt"], args.max_input_tokens,
                                   args.max_new_tokens, device)
        gen_docs, gen_invalid = doc_ids(text)
        gold_docs, gold_invalid = doc_ids(row.get("response", ""))
        inter = gen_docs & gold_docs
        precision = len(inter) / len(gen_docs) if gen_docs else 0.0
        recall = len(inter) / len(gold_docs) if gold_docs else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        st = statement_stats(text)
        results.append({
            "i": i,
            "prompt_chars": len(row["prompt"]),
            "text": text[:4000],
            **stats,
            **st,
            "gold_docs": len(gold_docs),
            "gen_docs": len(gen_docs),
            "doc_hit": len(inter),
            "doc_precision_proxy": round(precision, 4),
            "doc_recall_proxy": round(recall, 4),
            "doc_f1_proxy": round(f1, 4),
            "invalid_spans": gen_invalid,
        })
        print(f"[{i}/{len(picked)}] stmts={st['n_statements']} cited={st['n_statements_with_cite']} "
              f"docs={len(gen_docs)} gold={len(gold_docs)} P={precision:.2f} R={recall:.2f} "
              f"{stats['latency_s']}s", flush=True)

    n = len(results)
    agg = {
        "n": n,
        "model": "zai-org/LongCite-llama3.1-8b",
        "params": n_params,
        "device": device,
        "dtype": "bfloat16",
        "load_s": round(load_s, 1),
        "mean_doc_precision_proxy": round(sum(r["doc_precision_proxy"] for r in results) / n, 4),
        "mean_doc_recall_proxy": round(sum(r["doc_recall_proxy"] for r in results) / n, 4),
        "mean_doc_f1_proxy": round(sum(r["doc_f1_proxy"] for r in results) / n, 4),
        "mean_latency_s": round(sum(r["latency_s"] for r in results) / n, 3),
        "p50_latency_s": round(sorted(r["latency_s"] for r in results)[n // 2], 3),
        "mean_tokens_per_s": round(sum(r["tokens_per_s"] for r in results) / n, 3),
        "cited_statement_ratio": round(
            sum(r["n_statements_with_cite"] for r in results) /
            max(1, sum(r["n_statements"] for r in results)), 4),
        "n_with_citation": sum(1 for r in results if r["doc_hit"] > 0),
        "metric_note": "doc-level P/R/F1 proxy against the reference response citations; "
                       "official LongCite metric uses a GPT-4o judge and is not computed here",
    }
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "aggregate": agg,
           "samples": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(agg, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
