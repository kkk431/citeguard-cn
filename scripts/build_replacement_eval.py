"""Build a citation-context retrieval benchmark from the 22-paper corpus.

Each citation with a resolvable reference is one query; candidates are every
reference in the corpus (deduped by title) plus no external distractors — the
other 21 papers already act as distractors. Ground truth is the reference the
author actually cited, not a human judgement of "best support".

Output: data/experiments/replacement_eval_dataset.json
"""

from __future__ import annotations

import json
from pathlib import Path

from citeguard.citation_anchor import _citation_author_year, extract_citations
from citeguard.pdf_extract import extract_text_with_meta, split_references
from citeguard.reference_parser import parse_reference_list

CORPUS = Path("data/real_corpus")


def norm_title(title: str) -> str:
    return "".join(ch.lower() for ch in (title or "") if ch.isalnum())


def surname(author: str) -> str:
    parts = [p for p in (author or "").replace(",", " ").split() if p]
    return parts[-1].lower() if parts else ""


def resolve(citation, refs) -> int | None:
    if citation.ref_numbers:
        n = citation.ref_numbers[0]
        if 1 <= n <= len(refs):
            return n
        return None
    parsed = _citation_author_year(citation.key)
    if not parsed:
        return None
    wanted, year = parsed
    for ref in refs:
        if str(ref.year or "") != year:
            continue
        authors = ref.authors or []
        if authors and surname(authors[0]) == wanted:
            return ref.index
    return None


def main() -> None:
    queries = []
    pool: dict[str, dict] = {}
    papers = []
    for pdf in sorted(CORPUS.glob("*.pdf")):
        text, meta = extract_text_with_meta(str(pdf))
        body, ref_text = split_references(text)
        refs = parse_reference_list(ref_text)
        citations = extract_citations(body)
        if not refs or not citations:
            continue
        papers.append({"file": pdf.name, "refs": len(refs), "citations": len(citations)})
        for ref in refs:
            key = norm_title(ref.title)
            if key and key not in pool:
                pool[key] = {
                    "title": ref.title,
                    "venue": ref.venue,
                    "year": ref.year,
                    "doi": ref.doi,
                }
        for citation in citations:
            target = resolve(citation, refs)
            if not target:
                continue
            ref = refs[target - 1]
            key = norm_title(ref.title)
            if not key or key not in pool:
                continue
            queries.append(
                {
                    "paper": pdf.name,
                    "query": citation.sentence,
                    "target": key,
                    "key": citation.key,
                    "style": citation.style,
                }
            )

    data = {
        "papers": papers,
        "pool": pool,
        "queries": queries,
        "summary": {
            "papers": len(papers),
            "pool": len(pool),
            "queries": len(queries),
            "boundary": "Ground truth is the cited reference; candidate pool is the "
            "22-paper corpus. This measures context-to-reference retrieval, not whether "
            "the reference actually supports the claim.",
        },
    }
    out = Path("data/experiments/replacement_eval_dataset.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
