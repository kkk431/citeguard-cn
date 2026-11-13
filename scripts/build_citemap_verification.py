"""Build the 60-cell CiteMap verification packet.

The packet is a *sample*, not an exhaustive audit: 30 cells per topic. Cells
with machine evidence ask the reviewer to check quote+stance; cells without
machine evidence ask whether the abstract really contains no evidence for the
claim. Deterministic seed so the packet can be regenerated.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"
TOPICS = ("ai_education", "medical_imaging")
SEED = 20261114
PER_TOPIC = 30


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DATA / "verification_packet.json"))
    args = ap.parse_args()
    rng = random.Random(SEED)
    cells: list[dict] = []
    for topic_id in TOPICS:
        corpus = json.loads((DATA / "corpus" / f"{topic_id}.json").read_text(encoding="utf-8"))
        manual = json.loads((DATA / "extractions" / f"{topic_id}.json").read_text(encoding="utf-8"))
        auto_path = DATA / "extractions_auto" / f"{topic_id}.json"
        auto = json.loads(auto_path.read_text(encoding="utf-8")) if auto_path.exists() else {"evidence": []}
        claims = [c["claim_id"] for c in manual["claims"]]
        papers = [p["paper_id"] for p in corpus["papers"]]
        auto_by_pair = {(e["paper_id"], e["claim_id"]): e for e in auto["evidence"]}
        evidence_pairs = list(auto_by_pair)
        # one evidence cell per paper first, then remaining evidence pairs
        by_paper: dict[str, list[tuple[str, str]]] = {}
        for pair in evidence_pairs:
            by_paper.setdefault(pair[0], []).append(pair)
        chosen: list[tuple[str, str]] = []
        for paper in papers:
            pairs = sorted(by_paper.get(paper, []))
            if pairs:
                chosen.append(pairs[0])
        rest = sorted(set(evidence_pairs) - set(chosen))
        rng.shuffle(rest)
        chosen.extend(rest[: max(0, PER_TOPIC - 10 - len(chosen))])
        chosen = chosen[: PER_TOPIC - 10]
        used = set(chosen)
        no_evidence = [(p, c) for p in papers for c in claims if (p, c) not in auto_by_pair and (p, c) not in used]
        rng.shuffle(no_evidence)
        chosen.extend(no_evidence[: PER_TOPIC - len(chosen)])
        for paper_id, claim_id in chosen:
            ev = auto_by_pair.get((paper_id, claim_id))
            cells.append(
                {
                    "cell_id": f"{topic_id}-{paper_id}-{claim_id}",
                    "topic_id": topic_id,
                    "paper_id": paper_id,
                    "claim_id": claim_id,
                    "kind": "evidence" if ev else "no_evidence",
                    "evidence_id": ev.get("evidence_id") if ev else None,
                    "stance": ev.get("stance") if ev else None,
                    "quote": ev.get("quote") if ev else None,
                }
            )
    payload = {
        "schema_version": "1.0",
        "seed": SEED,
        "per_topic": PER_TOPIC,
        "protocol": "30 cells/topic: quote+stance check for machine-evidence cells; no-evidence check otherwise. Fill with scripts? UI POST /api/citemap/{topic}/verify.",
        "cells": cells,
    }
    out = Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"cells={len(cells)} topics={ {t: sum(1 for c in cells if c['topic_id']==t) for t in TOPICS} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
