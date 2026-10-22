"""Measure what a user-supplied local library changes for Chinese references.

Setup mirrors real use:
- the library is built from the *published* reference lists of 10 real papers
  (the kind of export users get from CNKI / NoteExpress), and
- the input is the same papers' *PDF-extracted* references.

So this answers: "if the user imports their own records, can CiteGuard verify
the Chinese references that open indexes miss?"
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.local_library import Library, parse_plain_references  # noqa: E402
from citeguard.metadata_verify import verify_many  # noqa: E402
from citeguard.pdf_extract import extract_text, split_references  # noqa: E402
from citeguard.reference_parser import parse_reference_list  # noqa: E402

CORPUS = ROOT / "data" / "real_corpus"
OUT = ROOT / "data" / "experiments" / "library_real.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)

    manifest = json.loads((CORPUS / "hanspub_manifest.json").read_text(encoding="utf-8"))
    library = Library()
    papers: list[dict] = []
    for item in manifest:
        refs_file = item.get("refs_file")
        if not refs_file or not Path(refs_file).exists():
            continue
        library.add(parse_plain_references(Path(refs_file).read_text(encoding="utf-8")))
        papers.append(item)
    print(f"library built from published lists: {len(library)} entries / {len(papers)} papers")

    rows: list[dict] = []
    for item in papers:
        pdf_file = item.get("pdf_file")
        if not pdf_file or not Path(pdf_file).exists():
            continue
        text = extract_text(pdf_file)
        _body, refs_text = split_references(text)
        refs = parse_reference_list(refs_text or text)
        results = verify_many(refs, progress=False, workers=args.workers, library=library)
        for ref, res in zip(refs, results):
            rows.append(
                {
                    "paper": item["title"][:36],
                    "title": ref.title[:80],
                    "status": res.status,
                    "from_library": "local" in (res.sources or []),
                    "mismatches": res.mismatches,
                }
            )
        print(f"  {len(refs):3d} refs  {item['title'][:34]}")

    status = Counter(r["status"] for r in rows)
    library_hits = sum(1 for r in rows if r["from_library"])
    definite = status["Exact"] + status["Minor"]
    summary = {
        "papers": len(papers),
        "refs": len(rows),
        "library_entries": len(library),
        "library_hits": library_hits,
        "status": dict(status),
        "definite_verdicts": definite,
        "definite_rate": round(definite / (len(rows) or 1), 4),
        "field_mismatch_detected": sum(
            1 for r in rows if r["from_library"] and r["status"] == "Minor"
        ),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n== verification with a local library ==")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nreport -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
