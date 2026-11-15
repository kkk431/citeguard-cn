"""Evaluate atomic CiteMap claims against the full texts we actually have.

The public evidence map ships abstracts only.  This script is the honest
next step: for papers whose OA full text was successfully fetched, retrieve
and judge sentence-level evidence for the 21 atomic claims.  It reports
``full/partial/none/error`` rather than treating "related sentence" as proof.

Usage:
    python scripts/eval_citemap_atomic_fulltext.py --limit-claims 2 --workers 2
    python scripts/eval_citemap_atomic_fulltext.py --out data/experiments/citemap_atomic_fulltext.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# The judge endpoint is read lazily, but config imports happen below; load
# the local key first so CLI runs match the running product.
_ENV_PATH = ROOT / ".env"
if _ENV_PATH.exists():
    for _line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from citeguard import citemap_verify  # noqa: E402

MAP_DIR = ROOT / "data" / "evidence_map"
FULLTEXT_DIR = ROOT / "data" / "cache" / "citemap_fulltext"
DEFAULT_OUT = ROOT / "data" / "experiments" / "citemap_atomic_fulltext.json"


def load_env() -> None:
    """Load the local .env without adding a dependency."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_titles(topic: str) -> dict[str, str]:
    corpus = load_json(MAP_DIR / "corpus" / f"{topic}.json")
    return {paper["paper_id"]: paper.get("title", "") for paper in corpus["papers"]}


def load_claims(topic: str, limit: int | None) -> list[dict]:
    payload = load_json(MAP_DIR / "claims_atomic.json")
    claims = payload["topics"][topic]["claims"]
    if limit:
        claims = claims[:limit]
    return claims


def load_texts(topic: str, limit: int | None) -> dict[str, str]:
    # Full-text files are named after paper ids and are cached outside the
    # evidence map on purpose (copyright / data-policy boundary).
    want = set(load_titles(topic))
    texts: dict[str, str] = {}
    for path in sorted(FULLTEXT_DIR.glob("*.txt")):
        paper_id = path.stem
        if paper_id not in want:
            continue  # another topic's paper
        text = path.read_text(encoding="utf-8", errors="ignore")
        if len(text) < 1000:
            continue
        texts[paper_id] = text
        if limit and len(texts) >= limit:
            break
    return texts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", choices=["ai_education", "medical_imaging"])
    parser.add_argument("--limit-claims", type=int, default=None)
    parser.add_argument("--limit-papers", type=int, default=None)
    parser.add_argument("--top", type=int, default=6)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    load_env()
    topics = [args.topic] if args.topic else ["ai_education", "medical_imaging"]
    started = time.time()
    all_results: list[dict] = []
    for topic in topics:
        claims = load_claims(topic, args.limit_claims)
        texts = load_texts(topic, args.limit_papers)
        if not texts:
            print(f"[{topic}] no full text found", file=sys.stderr)
            continue
        titles = load_titles(topic)
        print(f"[{topic}] {len(claims)} atomic claims × {len(texts)} full texts", file=sys.stderr)
        all_results.extend(citemap_verify.verify_topic(topic, claims, texts, titles, top=args.top, workers=args.workers))

    summary = citemap_verify.summarize(all_results)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data_source": "OpenAlex OA full texts fetched by scripts/fetch_citemap_fulltext.py",
        "claim_source": "data/evidence_map/claims_atomic.json (21 atomic claims; not human-ratified)",
        "judge": os.environ.get("CITEGUARD_JUDGE_MODEL", ""),
        "summary": summary,
        "results": all_results,
        "elapsed_s": round(time.time() - started, 1),
        "boundary": "Only full texts available locally are covered; claims not supported are reported as none, not hidden.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"wrote {args.out} ({len(all_results)} claim-paper rows) in {payload['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
