"""Compare abstract-only machine extraction with the 10 manual CiteMap examples.

This is a *coverage/agreement* check, not a full accuracy estimate: only ten
paper-claim pairs have a manual gold label. We report:

- how many manual pairs the machine layer also found;
- stance agreement on those pairs;
- how many papers have at least one machine evidence item;
- how many machine items passed the verbatim-quote check (always 100% by
  construction, but kept visible so the data card cannot hide it).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    abstracts = _load(DATA / "abstracts.json")
    abstract_by_paper = {
        rec.get("paper_id"): _norm(rec.get("abstract", "")) for rec in abstracts.values()
    }
    result = {"topics": {}, "totals": {}}
    manual_total = auto_hit = agree = 0
    papers_total = papers_with = 0
    items_total = bad_quote = 0

    for topic_id in ("ai_education", "medical_imaging"):
        corpus = _load(DATA / "corpus" / f"{topic_id}.json")
        manual = _load(DATA / "extractions" / f"{topic_id}.json")
        auto_path = DATA / "extractions_auto" / f"{topic_id}.json"
        auto = _load(auto_path) if auto_path.exists() else {"evidence": []}
        manual_pairs = {(e["paper_id"], e["claim_id"]): e for e in manual["evidence"]}
        auto_pairs = {(e["paper_id"], e["claim_id"]): e for e in auto["evidence"]}
        matched = sorted(set(manual_pairs) & set(auto_pairs))
        topic_agree = sum(1 for p in matched if manual_pairs[p]["stance"] == auto_pairs[p]["stance"])
        topic_papers = {p["paper_id"] for p in corpus["papers"]}
        auto_papers = {e["paper_id"] for e in auto["evidence"]}
        missing_quote = 0
        for e in auto["evidence"]:
            items_total += 1
            if e["quote"] not in abstract_by_paper.get(e["paper_id"], ""):
                missing_quote += 1
                bad_quote += 1
        result["topics"][topic_id] = {
            "manual_items": len(manual["evidence"]),
            "manual_pairs_found": len(matched),
            "stance_agree": topic_agree,
            "papers": len(topic_papers),
            "papers_with_auto_evidence": len(topic_papers & auto_papers),
            "auto_items": len(auto["evidence"]),
            "missing_quote": missing_quote,
            "missing_pairs": len(set(manual_pairs) - set(auto_pairs)),
        }
        manual_total += len(manual["evidence"])
        auto_hit += len(matched)
        agree += topic_agree
        papers_total += len(topic_papers)
        papers_with += len(topic_papers & auto_papers)

    result["totals"] = {
        "manual_items": manual_total,
        "manual_pairs_found": auto_hit,
        "manual_pair_coverage": round(auto_hit / manual_total, 4) if manual_total else 0.0,
        "stance_agreement": round(agree / auto_hit, 4) if auto_hit else 0.0,
        "papers": papers_total,
        "papers_with_auto_evidence": papers_with,
        "auto_items": items_total,
        "missing_quote": bad_quote,
        "note": "Agreement is measured only on the 10 manual pairs; it is not a full accuracy estimate.",
    }
    out = ROOT / "data" / "experiments" / "citemap_auto_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
