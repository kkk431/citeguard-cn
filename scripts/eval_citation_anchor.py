"""Measure in-text citation extraction on the 22-paper real corpus.

What this does *not* claim: it is not a human-annotated accuracy test. It reports
(a) how many papers yield citations at all, (b) how many reference entries are
cited from the body, and (c) a self-consistency check — the extracted key must
literally occur in the extracted sentence. A 40-row sample is written for manual
spot-checking, but the JSON only labels itself as automated checks.

Run:  PYTHONPATH=src python scripts/eval_citation_anchor.py
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from citeguard import pdf_extract
from citeguard.citation_anchor import coverage, extract_citations, summarize
from citeguard.reference_parser import parse_reference_list

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "real_corpus"
OUT = ROOT / "data" / "experiments" / "citation_anchor_real.json"
SAMPLE = ROOT / "data" / "experiments" / "citation_anchor_sample.csv"


def _self_consistent(key: str, sentence: str) -> bool:
    key = (key or "").strip()
    return bool(key) and key in sentence


def main() -> None:
    papers = sorted(CORPUS.glob("*.pdf"))
    rows = []
    samples = []
    for path in papers:
        text, meta = pdf_extract.extract_text_with_meta(path)
        body, refs_text = pdf_extract.split_references(text)
        refs = parse_reference_list(refs_text) if refs_text.strip() else []
        citations = extract_citations(body)
        cov = coverage(citations, refs)
        consistent = sum(1 for c in citations if _self_consistent(c.key, c.sentence))
        rows.append(
            {
                "paper": path.name,
                "pages": meta.get("pages") or 0,
                "refs": len(refs),
                "citations": len(citations),
                "style": summarize(citations)["by_style"],
                "coverage": cov,
                "self_consistent": consistent,
                "self_consistent_ratio": round(consistent / len(citations), 4) if citations else 0.0,
            }
        )
        for c in citations:
            samples.append(
                {
                    "paper": path.name,
                    "key": c.key,
                    "style": c.style,
                    "ref_numbers": " ".join(str(n) for n in c.ref_numbers),
                    "sentence": c.sentence,
                    "self_consistent": int(_self_consistent(c.key, c.sentence)),
                }
            )

    total_cites = sum(r["citations"] for r in rows)
    total_refs = sum(r["refs"] for r in rows)
    cited_refs = sum(r["coverage"]["cited"] for r in rows)
    with_citations = sum(1 for r in rows if r["citations"] > 0)
    consistent = sum(r["self_consistent"] for r in rows)
    summary = {
        "papers": len(rows),
        "papers_with_citations": with_citations,
        "paper_coverage": round(with_citations / len(rows), 4) if rows else 0.0,
        "total_references": total_refs,
        "total_citations": total_cites,
        "cited_reference_entries": cited_refs,
        "reference_coverage": round(cited_refs / total_refs, 4) if total_refs else 0.0,
        "self_consistent": consistent,
        "self_consistent_ratio": round(consistent / total_cites, 4) if total_cites else 0.0,
        "auto_check_note": "self-consistency only; not human-annotated accuracy",
        "papers": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    random.seed(20261111)
    picked = random.sample(samples, min(40, len(samples)))
    with SAMPLE.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["paper", "key", "style", "ref_numbers", "sentence", "self_consistent"])
        writer.writeheader()
        writer.writerows(picked)

    print(json.dumps({k: v for k, v in summary.items() if k != "papers"}, ensure_ascii=False, indent=1))
    print(f"paper coverage {with_citations}/{len(rows)}; citations {total_cites}; refs {total_refs}")
    print(f"wrote {OUT.relative_to(ROOT)} and {SAMPLE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
