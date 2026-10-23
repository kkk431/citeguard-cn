"""Measure reference-parsing quality on real published Chinese papers.

Two inputs per paper are used when available:
- the reference list as published on the article page (clean text), and
- the PDF, run through the production extraction path (``extract_text`` →
  ``split_references`` → ``parse_reference_list``), which is what users get.

The script does not need ground-truth labels: it reports field coverage plus the
entries the parser most likely got wrong (empty/oversized title, missing year,
missing type code), and dumps examples for manual review.

Usage:
    python scripts/eval_parse_real.py [--examples 25]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.pdf_extract import extract_text, split_references  # noqa: E402
from citeguard.reference_parser import parse_reference_list, split_entries  # noqa: E402

CORPUS = ROOT / "data" / "real_corpus"
OUT = ROOT / "data" / "experiments" / "parse_real.json"


def _is_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def _suspicious(ref) -> list[str]:
    problems: list[str] = []
    is_web = ref.doc_type == "EB"
    title = (ref.title or "").strip()
    if not title:
        problems.append("title_empty")
    elif len(title) < 4:
        problems.append("title_short")
    elif len(title) > 200:
        problems.append("title_long")
    elif re.search(r"https?://", title):
        problems.append("title_contains_url")
    # A web citation may legally lead with the title (GB/T 7714-2025) and its
    # publication year is optional, so only field rules for non-web types apply.
    if not ref.authors and not is_web:
        problems.append("authors_empty")
    elif len(ref.authors) > 12:
        problems.append("authors_many")
    if ref.year is None and not is_web:
        problems.append("year_missing")
    if not ref.doc_type:
        problems.append("type_missing")
    if ref.doc_type in {"J", "C", "N"} and not ref.venue:
        problems.append("venue_missing")
    if re.search(r"\[\d+\]", title):
        problems.append("title_contains_index")
    return problems


def _coverage(refs) -> dict:
    n = len(refs) or 1
    web = [r for r in refs if r.doc_type == "EB"]
    return {
        "title": round(sum(1 for r in refs if r.title) / n, 3),
        "authors": round(sum(1 for r in refs if r.authors) / n, 3),
        "year": round(sum(1 for r in refs if r.year) / n, 3),
        "doc_type": round(sum(1 for r in refs if r.doc_type) / n, 3),
        "venue": round(sum(1 for r in refs if r.venue) / n, 3),
        "doi": round(sum(1 for r in refs if r.doi) / n, 3),
        "pages": round(sum(1 for r in refs if r.pages) / n, 3),
        # Informational: web citations where no author was recognised at all.
        "web_refs": len(web),
        "web_no_author": sum(1 for r in web if not r.authors),
    }


def _analyze(refs, label: str, examples: list[dict], source: str) -> dict:
    problems: dict[str, int] = {}
    for ref in refs:
        for p in _suspicious(ref):
            problems[p] = problems.get(p, 0) + 1
            if len(examples) < 400:
                examples.append({"source": source, "kind": label, "problem": p, "raw": ref.raw[:240]})
    return {
        "count": len(refs),
        "coverage": _coverage(refs),
        "problems": problems,
        "clean_ratio": round(
            sum(1 for r in refs if not _suspicious(r)) / (len(refs) or 1), 3
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=25)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    items: list[dict] = []
    hans = CORPUS / "hanspub_manifest.json"
    if hans.exists():
        items += json.loads(hans.read_text(encoding="utf-8"))
    oa = CORPUS / "manifest.json"
    if oa.exists():
        items += json.loads(oa.read_text(encoding="utf-8"))

    examples: list[dict] = []
    report: list[dict] = []
    for item in items:
        source = item.get("url") or item.get("file") or item.get("title", "")
        entry = {"title": (item.get("title") or "")[:60], "source": source}
        refs_file = item.get("refs_file")
        if refs_file and Path(refs_file).exists():
            text = Path(refs_file).read_text(encoding="utf-8")
            html_refs = parse_reference_list(text)
            entry["published_list"] = _analyze(html_refs, "published", examples, source)
        pdf_file = item.get("pdf_file") or item.get("file")
        if pdf_file and Path(pdf_file).exists():
            try:
                pdf_text = extract_text(pdf_file)
                body, refs_text = split_references(pdf_text)
                pdf_refs = parse_reference_list(refs_text or pdf_text)
                entry["pdf_path"] = _analyze(pdf_refs, "pdf", examples, source)
                entry["pdf_path"]["split_found_heading"] = bool(refs_text)
                entry["pdf_path"]["entries_by_marks"] = len(
                    re.findall(r"\[\d+\]", refs_text or "")
                )
            except Exception as exc:  # noqa: BLE001 - report the failure
                entry["pdf_error"] = f"{type(exc).__name__}: {exc}"
        report.append(entry)

    summary = {
        "papers": len(report),
        "published_refs": sum(e.get("published_list", {}).get("count", 0) for e in report),
        "pdf_refs": sum(e.get("pdf_path", {}).get("count", 0) for e in report),
        "published_clean_ratio": round(
            statistics.mean(
                [e["published_list"]["clean_ratio"] for e in report if "published_list" in e]
            ),
            3,
        )
        if any("published_list" in e for e in report)
        else None,
        "pdf_clean_ratio": round(
            statistics.mean([e["pdf_path"]["clean_ratio"] for e in report if "pdf_path" in e]), 3
        )
        if any("pdf_path" in e for e in report)
        else None,
        "pdf_heading_found": sum(
            1 for e in report if e.get("pdf_path", {}).get("split_found_heading")
        ),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "papers": report, "examples": examples[: args.examples * 8]}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("== real-corpus parsing ==")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nworst examples ({min(args.examples, len(examples))}):")
    for ex in examples[: args.examples]:
        print(f"  [{ex['kind']}/{ex['problem']}] {ex['raw'][:150]}")
    print(f"\nreport -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
