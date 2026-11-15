"""Conservative CiteMap evidence extraction (v2).

Differences from v1:
- one model call per (paper, claim), not per paper;
- explicit ``no_evidence`` is the default answer;
- a second, independent verification call must agree on the stance;
- quotes must be verbatim substrings of the abstract.

The output stays ``verified=false``: it is a machine suggestion, not a human
audit. The v1 output is kept for comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"
CACHE = DATA / "auto_cache_v2"
PROMPT_VERSION = "v2-perclaim-verify"

EXTRACT_SYSTEM = """You are building a strict evidence map from paper abstracts.
For the single claim you are given, decide whether the abstract contains a
sentence that DIRECTLY supports or contradicts the exact proposition.

Rules:
- Use only the abstract. Never use outside knowledge.
- The sentence must match the claim's population, intervention/concept,
  comparison, outcome and direction as stated.
- A sentence that merely shares keywords, is about a related topic, or is
  background/method description is NOT evidence.
- If the abstract does not directly address the claim, answer no_evidence.
- quote must be copied verbatim and be one contiguous substring of the abstract.
- Return JSON only, with no markdown fence.
"""

EXTRACT_TMPL = """Claim (Chinese):
{claim}

Paper title: {title}
Abstract:
{abstract}

Return one JSON object:
{{"decision": "support|contradict|no_evidence",
  "quote": "", "summary_zh": "", "method": "", "sample": "", "confidence": 0.0}}

If decision is no_evidence, keep quote/summary empty and confidence 0.
"""

VERIFY_SYSTEM = """You are a strict reviewer. You receive a claim and a candidate
quote from a paper abstract. Decide whether the quote ALONE directly supports or
contradicts the claim, without outside context.

Reject the candidate if the quote is about a different population, intervention,
comparison, outcome, or direction; if it merely mentions the topic; or if the
claim is stronger than what the quote says.

Return JSON only:
{"valid": true|false, "stance": "support|contradict", "reason": "..."}
"""

VERIFY_TMPL = """Claim:
{claim}

Candidate quote:
{quote}

Paper title: {title}
Abstract (for checking that the quote is verbatim):
{abstract}
"""


def _load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _endpoint() -> str:
    base = os.environ.get("CITEGUARD_EXTRACT_ENDPOINT", "").rstrip("/")
    if not base:
        base = os.environ.get("CITEGUARD_JUDGE_BASE_URL", "").rstrip("/")
    if not base:
        base = "https://api.deepseek.com/v1"
    if not base.endswith("/v1") and "deepseek.com" in base:
        base += "/v1"
    return base


def _model() -> str:
    return os.environ.get("CITEGUARD_EXTRACT_MODEL") or os.environ.get(
        "CITEGUARD_JUDGE_MODEL", "deepseek-chat"
    )


def _key() -> str:
    return os.environ.get("CITEGUARD_EXTRACT_API_KEY") or os.environ.get(
        "DEEPSEEK_API_KEY", ""
    )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _post(system: str, user: str, max_tokens: int = 600) -> dict:
    body = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    key = _key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        _endpoint() + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read())
    content = payload["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.S)
    return json.loads(content)


def _extract_claim(claim: dict, paper: dict, abstract: str) -> dict | None:
    prompt = EXTRACT_TMPL.format(
        claim=claim["text"], title=paper["title"], abstract=abstract
    )
    try:
        obj = _post(EXTRACT_SYSTEM, prompt, max_tokens=600)
    except Exception as exc:  # noqa: BLE001 - keep batch alive
        print(f"[extract] {paper['paper_id']} {claim['claim_id']} ERROR {exc}", flush=True)
        return None
    decision = str(obj.get("decision", "")).lower()
    quote = _norm(obj.get("quote", ""))
    if decision not in {"support", "contradict"} or not quote:
        return None
    if quote not in _norm(abstract):
        return None
    confidence = float(obj.get("confidence", 0.5) or 0.5)
    return {
        "claim_id": claim["claim_id"],
        "stance": decision,
        "quote": quote,
        "summary": str(obj.get("summary_zh", "")).strip(),
        "method": str(obj.get("method", "")).strip(),
        "sample": str(obj.get("sample", "")).strip(),
        "confidence": max(0.0, min(1.0, confidence)),
    }


def _verify(item: dict, claim: dict, paper: dict, abstract: str) -> bool:
    prompt = VERIFY_TMPL.format(
        claim=claim["text"], quote=item["quote"], title=paper["title"], abstract=abstract
    )
    try:
        obj = _post(VERIFY_SYSTEM, prompt, max_tokens=300)
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] {paper['paper_id']} {claim['claim_id']} ERROR {exc}", flush=True)
        return False
    valid = bool(obj.get("valid"))
    stance = str(obj.get("stance", "")).lower()
    return valid and stance == item["stance"]


def _work(topic_id: str, paper: dict, abstract: str, claims: list[dict]) -> list[dict]:
    out: list[dict] = []
    for claim in claims:
        started = time.time()
        item = _extract_claim(claim, paper, abstract)
        if not item:
            continue
        if not _verify(item, claim, paper, abstract):
            print(
                f"[{topic_id}] {paper['paper_id']} {claim['claim_id']} rejected by verifier",
                flush=True,
            )
            continue
        item["paper_id"] = paper["paper_id"]
        item["extractor"] = "auto:abstract-only:v2"
        out.append(item)
        print(
            f"[{topic_id}] {paper['paper_id']} {claim['claim_id']} kept "
            f"{item['stance']} {time.time() - started:.1f}s",
            flush=True,
        )
    return out


def main() -> int:
    _load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", action="append", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out-dir", default=str(DATA / "extractions_auto_v2"))
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

        jobs = []
        for paper in papers:
            rec = abstracts.get(paper["openalex_id"], {})
            abstract = _norm(rec.get("abstract", ""))
            if not abstract:
                continue
            for claim in claims:
                key = hashlib.sha256(
                    (PROMPT_VERSION + paper["paper_id"] + claim["claim_id"] + abstract).encode("utf-8")
                ).hexdigest()[:20]
                cache_file = CACHE / f"{topic_id}-{paper['paper_id']}-{claim['claim_id']}-{key}.json"
                jobs.append((paper, abstract, claim, cache_file))

        results: list[tuple[dict, dict | None]] = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            future_map = {}
            for paper, abstract, claim, cache_file in jobs:
                if cache_file.exists():
                    try:
                        cached = json.loads(cache_file.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        cached = None
                    results.append((paper, cached))
                    continue
                future = pool.submit(_work_one, topic_id, paper, abstract, claim, cache_file)
                future_map[future] = paper
            for future in as_completed(future_map):
                paper, item = future.result()
                results.append((paper, item))

        evidence: list[dict] = []
        per_paper: dict[str, list[dict]] = {}
        for paper, item in results:
            if item:
                per_paper.setdefault(paper["paper_id"], []).append(item)
        for paper in papers:
            for j, item in enumerate(per_paper.get(paper["paper_id"], []), 1):
                evidence.append(
                    {
                        "evidence_id": f"auto2-{paper['paper_id']}-{j:02d}",
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
                        "extractor": item["extractor"],
                    }
                )
        payload = {
            "schema_version": "1.0",
            "topic_id": topic_id,
            "extractor": f"auto:{_model()}:v2",
            "extracted_at": time.strftime("%Y-%m-%d"),
            "protocol": "Abstract-only, per-claim extraction with an independent verification call; verified=false.",
            "evidence": evidence,
        }
        (out_dir / f"{topic_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"{topic_id}: {len(evidence)} evidence over {len(papers)} papers", flush=True)
    return 0


def _work_one(topic_id: str, paper: dict, abstract: str, claim: dict, cache_file: Path):
    try:
        item = _extract_claim(claim, paper, abstract)
        if not item or not _verify(item, claim, paper, abstract):
            cache_file.write_text("null", encoding="utf-8")
            return paper, None
        item["paper_id"] = paper["paper_id"]
        item["extractor"] = "auto:abstract-only:v2"
        cache_file.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
        return paper, item
    except Exception as exc:  # noqa: BLE001
        print(f"[{topic_id}] {paper['paper_id']} {claim['claim_id']} ERROR {exc}", flush=True)
        return paper, None


if __name__ == "__main__":
    sys.exit(main())
