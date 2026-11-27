"""Known-work fixture for version-aware entity resolution.

These are real papers/versions (arXiv vs conference), not synthetic titles. The
candidates are hand-built from public bibliographic metadata because the frozen
verify_real.json rows store only the chosen candidate, not the alternative
versions. This fixture tests the resolver, not a model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.metadata_verify import Candidate  # noqa: E402
from citeguard.reference_parser import Reference  # noqa: E402
from citeguard.version_resolution import resolve_versions  # noqa: E402


def run_case(case: dict) -> dict:
    ref = Reference(raw="fixture", title=case["title"], year=case["year"], authors=case["authors"])
    candidates = [Candidate(**c) for c in case["candidates"]]
    res = resolve_versions(ref, candidates)
    return {
        "id": case["id"],
        "title": case["title"],
        "expected_status": case["expected_status"],
        "actual_status": res.status,
        "cited_year_supported": res.cited_year_supported,
        "conflicts": res.conflicts,
        "notes": res.notes,
        "chosen": res.chosen.doi if res.chosen else None,
        "provenance": res.provenance,
        "pass": res.status == case["expected_status"],
    }


CASES = [
    {
        "id": "attention-2017",
        "title": "Attention Is All You Need",
        "year": 2017,
        "authors": ["Vaswani, Ashish"],
        "expected_status": "version_family",
        "candidates": [
            {"source": "arxiv", "title": "Attention Is All You Need", "year": 2017, "authors": ["Vaswani, Ashish"], "url": "https://arxiv.org/abs/1706.03762"},
            {"source": "openalex", "title": "Attention Is All You Need", "doi": "10.5555/3295222", "year": 2017, "authors": ["Vaswani, Ashish"], "venue": "NeurIPS"},
        ],
    },
    {
        "id": "bert-2018",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "year": 2018,
        "authors": ["Devlin, Jacob"],
        "expected_status": "version_family",
        "candidates": [
            {"source": "arxiv", "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding", "year": 2018, "authors": ["Devlin, Jacob"], "url": "https://arxiv.org/abs/1810.04805"},
            {"source": "crossref", "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding", "doi": "10.18653/v1/N19-1423", "year": 2019, "authors": ["Devlin, Jacob"], "venue": "NAACL"},
        ],
    },
    {
        "id": "resnet-2015",
        "title": "Deep Residual Learning for Image Recognition",
        "year": 2015,
        "authors": ["He, Kaiming"],
        "expected_status": "version_family",
        "candidates": [
            {"source": "arxiv", "title": "Deep Residual Learning for Image Recognition", "year": 2015, "authors": ["He, Kaiming"], "url": "https://arxiv.org/abs/1512.03385"},
            {"source": "crossref", "title": "Deep Residual Learning for Image Recognition", "doi": "10.1109/CVPR.2016.90", "year": 2016, "authors": ["He, Kaiming"], "venue": "CVPR"},
        ],
    },
    {
        "id": "same-doi-two-indexes",
        "title": "Attention Is All You Need",
        "year": 2017,
        "authors": ["Vaswani, Ashish"],
        "expected_status": "same_version",
        "candidates": [
            {"source": "openalex", "title": "Attention Is All You Need", "doi": "10.5555/3295222", "year": 2017, "authors": ["Vaswani, Ashish"], "venue": "NeurIPS"},
            {"source": "crossref", "title": "Attention Is All You Need.", "doi": "https://doi.org/10.5555/3295222", "year": 2017, "authors": ["Vaswani, Ashish"], "venue": "NeurIPS"},
        ],
    },
    {
        "id": "different-author-same-title",
        "title": "Attention Is All You Need",
        "year": 2017,
        "authors": ["Vaswani, Ashish"],
        "expected_status": "conflict",
        "candidates": [
            {"source": "crossref", "title": "Attention Is All You Need", "doi": "10.1000/wrong", "year": 2017, "authors": ["Someone Else"], "venue": "Other"},
        ],
    },
    {
        "id": "no-close-match",
        "title": "Attention Is All You Need",
        "year": 2017,
        "authors": ["Vaswani, Ashish"],
        "expected_status": "insufficient",
        "candidates": [
            {"source": "crossref", "title": "Completely Different Paper", "doi": "10.1000/other", "year": 2017},
        ],
    },
]


def main() -> int:
    results = [run_case(c) for c in CASES]
    out = {
        "schema": "citeguard.version_resolution_cases.v1",
        "kind": "known_work_fixture_not_random_sample",
        "n": len(results),
        "passed": sum(1 for r in results if r["pass"]),
        "results": results,
    }
    path = ROOT / "data" / "experiments" / "opt_b0_version_cases_2026-11-27.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["passed"] == out["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
