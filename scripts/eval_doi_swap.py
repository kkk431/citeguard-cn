"""DOI-swap test: pair one paper's title with another paper's DOI.

The verifier should never call such a reference "Exact". A high Exact rate would
mean a DOI pointing at the wrong paper goes unnoticed. This is a constructed
mismatch test, not a human-labelled benchmark.

Run: PYTHONPATH=src python scripts/eval_doi_swap.py [--n 100]
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import requests

from citeguard.metadata_verify import verify_many
from citeguard.reference_parser import Reference


def sample(n: int) -> list[dict]:
    resp = requests.get(
        "https://api.openalex.org/works",
        params={
            "filter": "has_doi:true,is_retracted:false",
            "per-page": min(100, n + 1),
            "select": "doi,title,publication_year",
        },
        timeout=30,
    )
    resp.raise_for_status()
    out = []
    for work in resp.json().get("results") or []:
        doi = (work.get("doi") or "").replace("https://doi.org/", "").strip()
        title = (work.get("title") or "").strip()
        if doi and title:
            out.append({"doi": doi, "title": title, "year": work.get("publication_year")})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--out", default="data/experiments/doi_swap_eval.json")
    args = parser.parse_args()

    works = sample(args.n + 1)
    pairs = []
    for i in range(min(args.n, len(works) - 1)):
        a, b = works[i], works[i + 1]
        if a["doi"] == b["doi"]:
            continue
        pairs.append({"title": a["title"], "year": a["year"], "doi": b["doi"]})

    refs = [
        Reference(
            raw=f"{p['title']}. DOI: {p['doi']}",
            index=i + 1,
            title=p["title"],
            year=p["year"],
            doi=p["doi"],
        )
        for i, p in enumerate(pairs)
    ]
    started = time.monotonic()
    results = verify_many(refs, use_arxiv=False)
    elapsed = round(time.monotonic() - started, 1)

    statuses = Counter(getattr(r, "status", "None") for r in results)
    exact = statuses.get("Exact", 0)
    mismatch_noted = sum(
        1
        for r in results
        if any("DOI 指向另一篇" in note for note in (getattr(r, "notes", None) or []))
    )
    report = {
        "pairs": len(pairs),
        "statuses": dict(statuses),
        "missed_exact": exact,
        "doi_mismatch_noted": mismatch_noted,
        "doi_mismatch_rate": round(mismatch_noted / max(len(pairs), 1), 4),
        "not_exact_rate": round(1 - exact / max(len(pairs), 1), 4),
        "elapsed_s": elapsed,
        "boundary": "Constructed swap: title from paper A, DOI from paper B. "
        "Any Exact is a missed DOI mismatch; this is not a human-labelled test.",
        "samples": [
            {
                "title": p["title"],
                "doi": p["doi"],
                "status": getattr(r, "status", ""),
                "notes": getattr(r, "notes", []),
            }
            for p, r in list(zip(pairs, results))[:10]
        ],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
