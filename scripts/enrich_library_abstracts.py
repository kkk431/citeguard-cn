"""Fill missing abstracts in the local reference library from OpenAlex/Crossref.

Why: the local library fixes Chinese-reference *coverage*, but exported records
often carry no abstract, and the claim-support judge needs the abstract text.
This one-off command enriches the library in place (data stays local; only
public metadata is fetched). Entries keep their abstract if they already have
one, and only very close title matches are accepted (see
``local_library.abstract_from_candidates``).

Usage:
    PYTHONPATH=src python3 scripts/enrich_library_abstracts.py            # enrich
    PYTHONPATH=src python3 scripts/enrich_library_abstracts.py --dry-run  # preview
    PYTHONPATH=src python3 scripts/enrich_library_abstracts.py --limit 50
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard import config  # noqa: E402
from citeguard.local_library import Library, abstract_from_candidates  # noqa: E402
from citeguard.metadata_verify import (  # noqa: E402
    Candidate,
    lookup_doi,
    search_crossref,
    search_openalex,
)


def candidates_for(entry, use_crossref: bool = True) -> list[Candidate]:
    """DOI lookup first (exact), then title search as a fallback."""
    cands: list[Candidate] = []
    if entry.doi:
        cands.extend(lookup_doi(entry.doi))
    if not any((c.abstract or "").strip() for c in cands):
        cands.extend(search_openalex(entry.title))
        if use_crossref:
            cands.extend(search_crossref(entry.title))
    return cands


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default=str(config.LIBRARY_FILE))
    ap.add_argument("--limit", type=int, default=0, help="max entries to try (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change")
    ap.add_argument("--no-crossref", action="store_true", help="skip Crossref title search")
    args = ap.parse_args(argv)

    path = Path(args.library)
    library = Library.load(path)
    if not len(library):
        print(f"library is empty: {path}")
        return 1

    todo = [e for e in library.entries if not (e.abstract or "").strip()]
    if args.limit:
        todo = todo[: args.limit]
    print(f"library: {len(library)} entries, {len(todo)} without abstract")

    enriched = 0
    for i, entry in enumerate(todo, 1):
        try:
            abstract = abstract_from_candidates(entry, candidates_for(entry, not args.no_crossref))
        except Exception as exc:  # noqa: BLE001 - network failures must not lose data
            print(f"[{i}/{len(todo)}] error: {type(exc).__name__}: {exc}")
            continue
        if abstract:
            enriched += 1
            if not args.dry_run:
                entry.abstract = abstract
            print(f"[{i}/{len(todo)}] + abstract ({len(abstract)} chars) {entry.title[:48]}")
        else:
            print(f"[{i}/{len(todo)}] - no abstract found          {entry.title[:48]}")

    if not args.dry_run:
        library.save(path)
    still_missing = sum(1 for e in library.entries if not (e.abstract or "").strip())
    print(
        f"\n{'(dry run) would enrich' if args.dry_run else 'enriched'} {enriched} entries; "
        f"{still_missing} still without abstract"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
