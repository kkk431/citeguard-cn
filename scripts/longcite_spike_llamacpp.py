"""LongCite-llama3.1-8b spike driver (llama.cpp server backend).

Runs a fixed sample of LongCite-45k prompts through a local llama-server built from
the public LongCite-llama3.1-8b weights (GGUF Q4_K_M, CPU) and reports:

- statement / citation counts,
- a document-level citation P/R/F1 **proxy** against the dataset reference response
  (the official LongCite metric needs a GPT-4o judge and is NOT computed here),
- prefill/decode latency and throughput from llama-server timings.

Requires a running server, e.g.:
  llama-server.exe -m longcite-q4km.gguf --ctx-size 8192 -t 16 --port 8099 --no-webui
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = Path(r"D:\Temp\citeguard_e3\longcite\long_head.jsonl")
CITE_RE = re.compile(r"<cite>(.*?)</cite>", re.DOTALL)
SPAN_RE = re.compile(r"\[(\d+)-(\d+)\]")
STATEMENT_RE = re.compile(r"<statement>(.*?)</statement>", re.DOTALL)
DOC_RE = re.compile(r"<C(\d+)>")


def load_rows(path: Path, max_prompt_chars: int, scan: int = 6000) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if len(row.get("prompt", "")) <= max_prompt_chars:
                rows.append(row)
            if len(rows) >= scan:
                break
    return rows


def lang_of(row: dict) -> str:
    question = row["prompt"].split("[Document End]")[-1]
    return "zh" if re.search(r"[\u4e00-\u9fff]", question) else "en"


def pick(rows: list[dict], n: int) -> list[dict]:
    """Take the first half from each language, then fill from whatever is left."""
    zh = [r for r in rows if lang_of(r) == "zh"]
    en = [r for r in rows if lang_of(r) == "en"]
    half = n // 2
    picked = zh[:half] + en[: n - half]
    if len(picked) < n:
        seen = {id(r) for r in picked}
        picked += [r for r in rows if id(r) not in seen][: n - len(picked)]
    return picked[:n]


def doc_ids(text: str, n_docs: int | None = None) -> tuple[set[int], int, int]:
    spans = []
    for block in CITE_RE.findall(text or ""):
        spans.extend((int(a), int(b)) for a, b in SPAN_RE.findall(block))
    ids, invalid = set(), 0
    for a, b in spans:
        if a > b or (n_docs is not None and a >= n_docs):
            invalid += 1
            continue
        ids.update(range(a, min(b, n_docs - 1) + 1 if n_docs else b + 1))
    return ids, invalid, len(spans)


def statements(text: str) -> tuple[int, int]:
    st = [s for s in STATEMENT_RE.findall(text or "") if s.strip()]
    return len(st), sum(1 for s in st if CITE_RE.search(s))


def complete(server: str, prompt: str, n_predict: int, timeout: int) -> dict:
    body = json.dumps({
        "prompt": prompt,
        "n_predict": n_predict,
        "temperature": 0.0,
        "top_p": 1.0,
        "stream": False,
        "cache_prompt": False,
    }).encode()
    req = urllib.request.Request(server.rstrip("/") + "/completion", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.load(r)
    out["_wall_s"] = time.perf_counter() - t0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--server", default="http://127.0.0.1:8099")
    ap.add_argument("--model", default="LongCite-llama3.1-8b Q4_K_M (GGUF, local)")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--max-prompt-chars", type=int, default=6000)
    ap.add_argument("--n-predict", type=int, default=256)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data" / "experiments" / "longcite_spike.json")
    args = ap.parse_args()

    rows = pick(load_rows(args.data, args.max_prompt_chars), args.n)
    if not rows:
        print("no usable samples", file=sys.stderr)
        return 2

    results = []
    for i, row in enumerate(rows, 1):
        out = complete(args.server, row["prompt"], args.n_predict, args.timeout)
        text = out.get("content", "")
        n_docs = len({int(x) for x in DOC_RE.findall(row["prompt"])})
        gen_docs, gen_invalid, gen_spans = doc_ids(text, n_docs)
        gold_docs, gold_invalid, gold_spans = doc_ids(row.get("response", ""), n_docs)
        inter = gen_docs & gold_docs
        p = len(inter) / len(gen_docs) if gen_docs else 0.0
        r = len(inter) / len(gold_docs) if gold_docs else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        n_st, n_cited = statements(text)
        timings = out.get("timings", {}) or {}
        rec = {
            "i": i,
            "lang": lang_of(row),
            "prompt_chars": len(row["prompt"]),
            "n_docs": n_docs,
            "n_statements": n_st,
            "n_statements_with_cite": n_cited,
            "n_citation_spans": gen_spans,
            "invalid_spans": gen_invalid,
            "gen_docs": len(gen_docs),
            "gold_docs": len(gold_docs),
            "doc_hit": len(inter),
            "doc_precision_proxy": round(p, 4),
            "doc_recall_proxy": round(r, 4),
            "doc_f1_proxy": round(f1, 4),
            "prompt_tokens": timings.get("prompt_n"),
            "prompt_ms": timings.get("prompt_ms"),
            "generated_tokens": timings.get("predicted_n"),
            "predicted_ms": timings.get("predicted_ms"),
            "predicted_per_s": timings.get("predicted_per_second"),
            "wall_s": round(out.get("_wall_s", 0.0), 3),
            "text": text[:4000],
            "gold_text": row.get("response", "")[:1000],
        }
        results.append(rec)
        print(f"[{i}/{len(rows)}] {rec['lang']} stmts={n_st} cited={n_cited} "
              f"docs={len(gen_docs)} gold={len(gold_docs)} P={p:.2f} R={r:.2f} "
              f"{rec['generated_tokens']}tok {rec['wall_s']}s", flush=True)

    n = len(results)
    agg = {
        "n": n,
        "model": args.model,
        "backend": "llama.cpp llama-server, CPU, Q4_K_M",
        "device": "CPU (AMD Ryzen 7 8845H, 8C/16T)",
        "mean_doc_precision_proxy": round(sum(r["doc_precision_proxy"] for r in results) / n, 4),
        "mean_doc_recall_proxy": round(sum(r["doc_recall_proxy"] for r in results) / n, 4),
        "mean_doc_f1_proxy": round(sum(r["doc_f1_proxy"] for r in results) / n, 4),
        "mean_statement_recall_of_gold_docs": round(sum(r["doc_recall_proxy"] for r in results) / n, 4),
        "n_samples_with_any_cite": sum(1 for r in results if r["n_statements_with_cite"] > 0),
        "mean_statements": round(sum(r["n_statements"] for r in results) / n, 2),
        "cited_statement_ratio": round(
            sum(r["n_statements_with_cite"] for r in results) /
            max(1, sum(r["n_statements"] for r in results)), 4),
        "mean_prompt_tokens": round(sum((r["prompt_tokens"] or 0) for r in results) / n, 1),
        "mean_prompt_ms": round(sum((r["prompt_ms"] or 0) for r in results) / n, 1),
        "mean_generated_tokens": round(sum((r["generated_tokens"] or 0) for r in results) / n, 1),
        "mean_predicted_per_s": round(
            sum((r["predicted_per_s"] or 0) for r in results) / n, 2),
        "mean_wall_s": round(sum(r["wall_s"] for r in results) / n, 2),
        "metric_note": "doc-level P/R/F1 proxy against the dataset reference response citations; "
                       "official LongCite citation recall/precision use a GPT-4o judge and are NOT computed.",
    }
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "aggregate": agg,
           "samples": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(agg, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
