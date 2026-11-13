"""Extract CiteMap evidence from paper abstracts with an OpenAI-compatible model.

This is an *abstract-only, machine-extracted* layer. It never claims full-text
verification: quotes must be verbatim substrings of the abstract and every item
is marked verified=false. The manual 10-example extraction remains the gold
reference used by scripts/eval_citemap_auto.py.

Usage:
    set CITEGUARD_EXTRACT_ENDPOINT=http://127.0.0.1:8097/v1
    set CITEGUARD_EXTRACT_MODEL=qwen3-14b
    python scripts/extract_citemap_auto.py --topic ai_education
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"
CACHE = DATA / "auto_cache"

SYSTEM = """You extract evidence from a paper abstract for a structured evidence map.
Rules:
- Use ONLY the supplied abstract. Never use outside knowledge.
- For each claim decide: support, contradict, or neutral (no evidence).
- quote must be a verbatim contiguous substring of the abstract (copy exactly, no ellipsis).
- summary_zh is a short Chinese summary of what the quote shows.
- method/sample only if the abstract states it; otherwise empty strings.
- confidence is 0-1 and reflects how directly the quote bears on the claim.
- Return JSON only, no markdown fence, no commentary."""

USER_TMPL = """Topic question: {question}

Claims:
{claims}

Paper title: {title}
Abstract:
{abstract}

Return a JSON object:
{{"evidence": [{{"claim_id": "...", "stance": "support|contradict|neutral", "quote": "...", "summary_zh": "...", "method": "...", "sample": "...", "confidence": 0.0}}]}}
Only include entries whose quote appears verbatim in the abstract. It is fine to return an empty list."""


def _endpoint() -> str:
    base = os.environ.get("CITEGUARD_EXTRACT_ENDPOINT", "").rstrip("/")
    if not base:
        raise SystemExit("CITEGUARD_EXTRACT_ENDPOINT is not set")
    return base


def _model() -> str:
    return os.environ.get("CITEGUARD_EXTRACT_MODEL", "qwen3-14b")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_one(paper: dict, abstract: str, claims: list[dict], question: str) -> list[dict]:
    claim_lines = "\n".join(f"- {c['claim_id']}: {c['text']}" for c in claims)
    prompt = USER_TMPL.format(
        question=question,
        claims=claim_lines,
        title=paper["title"],
        abstract=abstract,
    )
    body = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 1400,
    }
    req = urllib.request.Request(
        _endpoint() + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        payload = json.loads(resp.read())
    content = payload["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.S)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    items = parsed.get("evidence") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    abstract_norm = _norm(abstract)
    valid: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = _norm(str(item.get("quote", "")))
        claim_id = str(item.get("claim_id", ""))
        stance = str(item.get("stance", "neutral")).lower()
        if not quote or stance not in {"support", "contradict", "neutral"}:
            continue
        if claim_id not in {c["claim_id"] for c in claims}:
            continue
        if quote not in abstract_norm:
            continue
        if stance == "neutral":
            continue
        valid.append(
            {
                "claim_id": claim_id,
                "stance": stance,
                "quote": quote,
                "summary": str(item.get("summary_zh", "")).strip(),
                "method": str(item.get("method", "")).strip(),
                "sample": str(item.get("sample", "")).strip(),
                "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
            }
        )
    return valid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", action="append", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out-dir", default=str(DATA / "extractions_auto"))
    args = ap.parse_args()

    abstracts = json.loads((DATA / "abstracts.json").read_text(encoding="utf-8"))
    topics = args.topic or ["ai_education", "medical_imaging"]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    for topic_id in topics:
        corpus = json.loads((DATA / "corpus" / f"{topic_id}.json").read_text(encoding="utf-8"))
        manual = json.loads((DATA / "extractions" / f"{topic_id}.json").read_text(encoding="utf-8"))
        claims = manual["claims"]
        papers = corpus["papers"]
        if args.limit:
            papers = papers[: args.limit]
        def work(paper: dict) -> tuple[dict, list[dict]]:
            rec = abstracts.get(paper["openalex_id"], {})
            abstract = _norm(rec.get("abstract", ""))
            if not abstract:
                return paper, []
            key = hashlib.sha256((paper["paper_id"] + abstract).encode("utf-8")).hexdigest()[:16]
            cache_file = CACHE / f"{topic_id}-{paper['paper_id']}-{key}.json"
            if cache_file.exists():
                return paper, json.loads(cache_file.read_text(encoding="utf-8"))
            started = time.time()
            try:
                items = _extract_one(paper, abstract, claims, corpus["topic"]["question"])
            except Exception as exc:  # noqa: BLE001 - keep batch alive
                print(f"[{topic_id}] {paper['paper_id']} ERROR {exc}", flush=True)
                return paper, []
            cache_file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            print(
                f"[{topic_id}] {paper['paper_id']} {len(items)} items {time.time() - started:.1f}s",
                flush=True,
            )
            return paper, items

        by_id: dict[str, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = [pool.submit(work, paper) for paper in papers]
            for fut in as_completed(futures):
                paper, items = fut.result()
                by_id[paper["paper_id"]] = items

        evidence: list[dict] = []
        for paper in papers:
            items = by_id.get(paper["paper_id"], [])
            for j, item in enumerate(items, 1):
                evidence.append(
                    {
                        "evidence_id": f"auto-{paper['paper_id']}-{j:02d}",
                        "claim_id": item["claim_id"],
                        "paper_id": paper["paper_id"],
                        "stance": item["stance"],
                        "summary": item["summary"],
                        "quote": item["quote"],
                        "locator": "Abstract",
                        "method": item["method"],
                        "sample": item["sample"],
                        "confidence": round(item["confidence"], 3),
                        "verified": False,
                        "extractor": "auto:abstract-only",
                    }
                )
        payload = {
            "schema_version": "1.0",
            "topic_id": topic_id,
            "extractor": f"auto:{_model()}",
            "extracted_at": time.strftime("%Y-%m-%d"),
            "protocol": "Abstract-only machine extraction; every quote is a verbatim substring; verified=false.",
            "evidence": evidence,
        }
        (out_dir / f"{topic_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"{topic_id}: {len(evidence)} evidence over {len(papers)} papers", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
