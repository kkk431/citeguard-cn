"""LongCite GPU spike (t31): the 20 t29 samples, 512 tokens, llama.cpp CUDA backend.

This is a *controlled* rerun of the t29 CPU spike: identical samples, identical
Q4_K_M GGUF weights, temperature 0, only the device and ``n_predict`` change
(256 on CPU -> 512 on one RTX 4090). It answers one question: on a GPU, does
LongCite reach a level that could be kept as an *offline* citation draft?

Metric definitions (all **proxy**, matching t29 口径):

* doc-level: per sample, the chunk ids cited by the generated
  ``<cite>[a-b]</cite>`` spans vs. the ids cited by the reference response.
  Spans are clamped to the prompt's chunk count, out-of-range spans count as
  invalid; precision/recall/F1 per sample, then the mean over samples.
* statement-level: greedy alignment of each generated ``<statement>`` to an
  unused reference statement by 3-gram Jaccard >= 0.25, then chunk-id overlap
  inside each matched pair (same code as t29's post-processing).
* truncation: ``generated_tokens >= n_predict`` (hit the cap) or an unclosed
  ``<statement>`` tag.

The official LongCite metric (GPT-4o judge on citation recall/precision) is
NOT run: no API key on the GPU host and it would not be comparable to t29.

Usage (GPU host):
    python scripts/longcite_spike_gpu.py \
        --data /data1/GYX/citeguard/longcite_gpu/data/longcite_gpu_20.jsonl \
        --server http://127.0.0.1:8099 --n-predict 512 \
        --gguf /data1/GYX/citeguard/longcite_gpu/models/longcite-q4km.gguf \
        --out /data1/GYX/citeguard/longcite_gpu/out/longcite_spike_gpu.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import requests

CITE_RE = re.compile(r"<cite>(.*?)</cite>", re.DOTALL)
SPAN_RE = re.compile(r"\[(\d+)-(\d+)\]")
STATEMENT_RE = re.compile(r"<statement>(.*?)</statement>", re.DOTALL)
OPEN_STATEMENT_RE = re.compile(r"<statement>")
DOC_RE = re.compile(r"<C(\d+)>")

THRESHOLDS = {
    "p50_wall_s_max": 5.0,
    "p95_wall_s_max": 15.0,
    "doc_f1_min": 0.65,
    "statement_f1_min": 0.75,
    "truncation_rate_max": 0.20,
}


def clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def grams(text: str, k: int = 3) -> set[str]:
    text = re.sub(r"\s+", "", clean(text))
    return {text[i : i + k] for i in range(max(0, len(text) - k + 1))}


def jac(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def count_docs(prompt: str) -> int:
    """Citeable chunk count of a LongCite prompt (t29 口径: distinct ``<C{n}>``)."""
    return len({int(x) for x in DOC_RE.findall(prompt)})


def doc_ids(text: str, n_docs: int | None = None) -> tuple[set[int], int, int]:
    """Chunk ids cited by ``text``; returns (ids, invalid spans, span count)."""
    spans: list[tuple[int, int]] = []
    for block in CITE_RE.findall(text or ""):
        spans.extend((int(a), int(b)) for a, b in SPAN_RE.findall(block))
    ids: set[int] = set()
    invalid = 0
    for a, b in spans:
        if a > b or (n_docs is not None and a >= n_docs):
            invalid += 1
            continue
        ids.update(range(a, min(b, n_docs - 1) + 1 if n_docs else b + 1))
    return ids, invalid, len(spans)


def docs_loose(text: str) -> set[int]:
    """Chunk ids without clamping (exact t29 post-processing for statement alignment)."""
    ids: set[int] = set()
    for block in CITE_RE.findall(text or ""):
        for a, b in SPAN_RE.findall(block):
            a, b = int(a), int(b)
            if a <= b:
                ids.update(range(a, b + 1))
    return ids


def statements(text: str) -> list[str]:
    return [x for x in STATEMENT_RE.findall(text or "") if clean(x)]


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in (0, 100])."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return ordered[rank - 1]


def complete(server: str, prompt: str, n_predict: int, timeout: float) -> dict:
    payload = {
        "prompt": prompt,
        "n_predict": n_predict,
        "temperature": 0.0,
        "top_p": 1.0,
        "stream": False,
        "cache_prompt": False,
    }
    resp = requests.post(server.rstrip("/") + "/completion", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def timings_of(resp: dict) -> dict:
    timings = resp.get("timings") or {}
    prompt_n = timings.get("prompt_n") or resp.get("tokens_evaluated") or 0
    predicted_n = timings.get("predicted_n") or resp.get("tokens_predicted") or 0
    prompt_ms = timings.get("prompt_ms") or resp.get("prompt_ms") or 0.0
    predicted_ms = timings.get("predicted_ms") or resp.get("predicted_ms") or 0.0
    per_s = timings.get("predicted_per_second") or resp.get("predicted_per_second") or 0.0
    if not per_s and predicted_ms:
        per_s = predicted_n / (predicted_ms / 1000.0)
    return {
        "prompt_tokens": int(prompt_n),
        "generated_tokens": int(predicted_n),
        "prompt_ms": round(float(prompt_ms), 1),
        "predicted_ms": round(float(predicted_ms), 1),
        "decode_tokens_per_s": round(float(per_s), 2),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def statement_level(samples: list[dict]) -> dict:
    """Exact t29 post-processing: greedy 3-gram Jaccard alignment, chunk overlap."""
    pairs = 0
    gen_total = 0
    gold_total = 0
    p_num = p_den = r_num = r_den = 0
    for sample in samples:
        gs = statements(sample["text"])
        hs = statements(sample["gold_text"])
        gen_total += len(gs)
        gold_total += len(hs)
        used: set[int] = set()
        for gen in gs:
            gd = docs_loose(gen)
            bg = grams(gen)
            best, best_j = None, 0.0
            for idx, gold in enumerate(hs):
                if idx in used:
                    continue
                score = jac(bg, grams(gold))
                if score > best_j:
                    best, best_j = idx, score
            if best is None or best_j < 0.25:
                continue
            used.add(best)
            hd = docs_loose(hs[best])
            pairs += 1
            if gd:
                p_den += len(gd)
                p_num += len(gd & hd)
            if hd:
                r_den += len(hd)
                r_num += len(gd & hd)
    precision = p_num / p_den if p_den else 0.0
    recall = r_num / r_den if r_den else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "n_generated_statements": gen_total,
        "n_gold_statements": gold_total,
        "n_matched_pairs": pairs,
        "statement_match_rate": round(pairs / max(1, gen_total), 4),
        "matched_citation_precision_proxy": round(precision, 4),
        "matched_citation_recall_proxy": round(recall, 4),
        "matched_citation_f1_proxy": round(f1, 4),
        "note": "greedy 3-gram Jaccard>=0.25 alignment between generated and reference "
        "statements; chunk-id overlap inside matched pairs; proxy only, not the "
        "official LongCite GPT-4o judge metric",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="20-sample JSONL from t29 selection")
    ap.add_argument("--server", default="http://127.0.0.1:8099")
    ap.add_argument("--n-predict", type=int, default=512)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--gguf", default=None, help="GGUF path (recorded + hashed)")
    ap.add_argument("--model", default="zai-org/LongCite-llama3.1-8b (GGUF Q4_K_M)")
    ap.add_argument("--device", default="NVIDIA GeForce RTX 4090 (CUDA_VISIBLE_DEVICES=3)")
    ap.add_argument("--backend", default="llama.cpp llama-server, CUDA, GIN")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = load_rows(Path(args.data))
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("no samples")

    gguf_meta = {}
    if args.gguf:
        gguf_path = Path(args.gguf)
        gguf_meta = {
            "path": str(gguf_path),
            "bytes": gguf_path.stat().st_size,
            "sha256": sha256_file(gguf_path) if gguf_path.exists() else None,
            "quantization": "Q4_K_M",
        }

    started = dt.datetime.now(dt.timezone.utc)
    samples = []
    server_model = None
    for row in rows:
        n_docs = count_docs(row["prompt"])
        record = {
            "i": row.get("i"),
            "lang": row.get("lang"),
            "prompt_chars": len(row["prompt"]),
            "n_docs": n_docs,
            "prompt_sha256": hashlib.sha256(row["prompt"].encode("utf-8")).hexdigest()[:16],
        }
        t0 = time.perf_counter()
        try:
            resp = complete(args.server, row["prompt"], args.n_predict, args.timeout)
            wall = time.perf_counter() - t0
            text = resp.get("content", "")
            timing = timings_of(resp)
            if server_model is None:
                server_model = resp.get("model")
        except Exception as exc:  # noqa: BLE001 - record the failure, keep going
            record.update(
                {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "wall_s": round(time.perf_counter() - t0, 3),
                }
            )
            samples.append(record)
            print(f"[{record['i']}] ERROR {record['error']}", flush=True)
            continue

        gen_docs, gen_invalid, gen_spans = doc_ids(text, n_docs)
        gold_docs, gold_invalid, _ = doc_ids(row["response"], n_docs)
        overlap = len(gen_docs & gold_docs)
        precision = overlap / len(gen_docs) if gen_docs else 0.0
        recall = overlap / len(gold_docs) if gold_docs else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        gen_states = statements(text)
        cited = [s for s in gen_states if CITE_RE.search(s)]
        unclosed = len(OPEN_STATEMENT_RE.findall(text)) > len(gen_states)
        truncated = timing["generated_tokens"] >= args.n_predict or unclosed

        record.update(
            {
                "status": "ok",
                "wall_s": round(wall, 3),
                "n_statements": len(gen_states),
                "n_statements_with_cite": len(cited),
                "n_statements_without_cite": len(gen_states) - len(cited),
                "n_citation_spans": gen_spans,
                "invalid_spans": gen_invalid + gold_invalid,
                "hit_token_cap": timing["generated_tokens"] >= args.n_predict,
                "unclosed_statement": unclosed,
                "truncated": truncated,
                "gen_docs": sorted(gen_docs),
                "gold_docs": sorted(gold_docs),
                "doc_overlap": overlap,
                "doc_precision_proxy": round(precision, 4),
                "doc_recall_proxy": round(recall, 4),
                "doc_f1_proxy": round(f1, 4),
                **timing,
                "text": text[:4000],
                "gold_text": row["response"][:1000],
            }
        )
        samples.append(record)
        print(
            f"[{record['i']}] {record['lang']} wall={record['wall_s']:.2f}s "
            f"gen_tok={record['generated_tokens']} tok/s={record['decode_tokens_per_s']:.1f} "
            f"docF1={record['doc_f1_proxy']:.3f} trunc={record['truncated']}",
            flush=True,
        )

    ok = [s for s in samples if s["status"] == "ok"]
    walls = [s["wall_s"] for s in ok]
    doc_p = [s["doc_precision_proxy"] for s in ok]
    doc_r = [s["doc_recall_proxy"] for s in ok]
    doc_f = [s["doc_f1_proxy"] for s in ok]
    prompt_tokens = [s["prompt_tokens"] for s in ok]
    gen_tokens = [s["generated_tokens"] for s in ok]
    decode = [s["decode_tokens_per_s"] for s in ok]

    def mean(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    truncation_rate = round(sum(1 for s in ok if s["truncated"]) / len(ok), 4) if ok else 1.0
    stmt = statement_level(ok)

    aggregates = {
        "n": len(samples),
        "n_ok": len(ok),
        "n_errors": len(samples) - len(ok),
        "mean_doc_precision_proxy": mean(doc_p),
        "mean_doc_recall_proxy": mean(doc_r),
        "mean_doc_f1_proxy": mean(doc_f),
        "mean_prompt_tokens": mean(prompt_tokens),
        "mean_generated_tokens": mean(gen_tokens),
        "mean_decode_tokens_per_s": mean(decode),
        "mean_wall_s": mean(walls),
        "p50_wall_s": round(percentile(walls, 50), 3) if walls else 0.0,
        "p95_wall_s": round(percentile(walls, 95), 3) if walls else 0.0,
        "min_wall_s": round(min(walls), 3) if walls else 0.0,
        "max_wall_s": round(max(walls), 3) if walls else 0.0,
        "total_wall_s": round(sum(walls), 3) if walls else 0.0,
        "n_truncated": sum(1 for s in ok if s["truncated"]),
        "truncation_rate": truncation_rate,
        "n_hit_token_cap": sum(1 for s in ok if s.get("hit_token_cap")),
        "n_unclosed_statement": sum(1 for s in ok if s.get("unclosed_statement")),
        "n_statements": sum(s["n_statements"] for s in ok),
        "n_statements_without_cite": sum(s["n_statements_without_cite"] for s in ok),
        "n_invalid_spans": sum(s["invalid_spans"] for s in ok),
        "n_zero_hit_samples": sum(1 for s in ok if s["doc_f1_proxy"] == 0.0),
        "metric_note": "doc-level = per-sample cited-chunk set vs reference, mean over "
        "samples (t29 口径, chunk ids are called docs in the t29 report); "
        "statement-level = t29 greedy alignment proxy; proxy only",
    }

    thresholds = {
        "p50_wall_s": {
            "value": aggregates["p50_wall_s"],
            "max": THRESHOLDS["p50_wall_s_max"],
            "pass": aggregates["p50_wall_s"] <= THRESHOLDS["p50_wall_s_max"],
        },
        "p95_wall_s": {
            "value": aggregates["p95_wall_s"],
            "max": THRESHOLDS["p95_wall_s_max"],
            "pass": aggregates["p95_wall_s"] <= THRESHOLDS["p95_wall_s_max"],
        },
        "doc_f1_proxy": {
            "value": aggregates["mean_doc_f1_proxy"],
            "min": THRESHOLDS["doc_f1_min"],
            "pass": aggregates["mean_doc_f1_proxy"] >= THRESHOLDS["doc_f1_min"],
        },
        "statement_f1_proxy": {
            "value": stmt["matched_citation_f1_proxy"],
            "min": THRESHOLDS["statement_f1_min"],
            "pass": stmt["matched_citation_f1_proxy"] >= THRESHOLDS["statement_f1_min"],
        },
        "truncation_rate": {
            "value": truncation_rate,
            "max": THRESHOLDS["truncation_rate_max"],
            "pass": truncation_rate < THRESHOLDS["truncation_rate_max"],
        },
    }
    failed = [name for name, row in thresholds.items() if not row["pass"]]
    verdict = "pass" if not failed else "reject"

    worst = sorted(ok, key=lambda s: (s["doc_f1_proxy"], s["n_statements_with_cite"]))
    failures = [
        {
            "i": s["i"],
            "lang": s["lang"],
            "wall_s": s["wall_s"],
            "doc_f1_proxy": s["doc_f1_proxy"],
            "gen_docs": s["gen_docs"],
            "gold_docs": s["gold_docs"],
            "n_statements": s["n_statements"],
            "n_statements_without_cite": s["n_statements_without_cite"],
            "truncated": s["truncated"],
            "text_excerpt": s["text"][:600],
            "gold_excerpt": s["gold_text"][:400],
        }
        for s in worst[:4]
    ]

    payload = {
        "task": "t31",
        "run": "A3c LongCite 20-sample GPU rerun, 512 tokens",
        "built_at": started.isoformat(),
        "environment": {
            "device": args.device,
            "backend": args.backend,
            "host": "222.20.126.148 (lmh, 4x RTX 4090)",
            "cpu": "host CPU (data prep only)",
            "python": sys.version.split()[0],
            "server_model_field": server_model,
        },
        "model": {
            "name": args.model,
            "license": "Llama 3.1 Community License",
            "params": "8.03B",
            "gguf": gguf_meta,
            "dataset": "LongCite-45k (Apache-2.0)",
            "official_metric": "NOT run: official LongCite citation recall/precision needs a "
            "GPT-4o judge; this run reports proxy metrics only",
        },
        "config": {
            "samples": len(rows),
            "n_predict": args.n_predict,
            "temperature": 0.0,
            "top_p": 1.0,
            "server": args.server,
            "data_file": args.data,
            "data_sha256": sha256_file(Path(args.data)),
        },
        "samples": samples,
        "aggregates": aggregates,
        "statement_level": stmt,
        "thresholds": thresholds,
        "failed_thresholds": failed,
        "verdict": verdict,
        "failures": failures,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(
        json.dumps(
            {
                "verdict": verdict,
                "failed": failed,
                "aggregates": aggregates,
                "statement_level": stmt,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    print(f"[done] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
