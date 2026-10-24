"""Fill missing abstracts in the local library from public metadata.

Why this exists: the local library fixes Chinese-reference *coverage*, but CNKI
/ NoteExpress / EndNote exports usually carry no abstract, and the
claim-support judge needs the abstract text. Until now users had to run
``scripts/enrich_library_abstracts.py`` on the server. This module is the same
logic exposed to the web UI so the library page can offer a one-click, opt-in
"补摘要" action.

Safety rules (unchanged from the script):
- only entries without an abstract are touched;
- only close title matches (>= 0.92 in ``abstract_from_candidates``) with a
  compatible year are accepted;
- network failures never lose data: the entry keeps its old record and the
  result reports an error per entry.

Nothing here writes the library to disk; callers save it (the web route does).
"""
from __future__ import annotations

from .local_library import Library, LibraryEntry, abstract_from_candidates
from .metadata_verify import Candidate, lookup_doi, search_crossref, search_openalex

# A single web request enriches at most this many entries, so one click cannot
# block the request thread for minutes on a big library.
MAX_ENRICH_PER_REQUEST = 20


def candidates_for(entry: LibraryEntry, use_crossref: bool = True) -> list[Candidate]:
    """DOI lookup first (exact), then title search as a fallback."""
    cands: list[Candidate] = []
    if entry.doi:
        cands.extend(lookup_doi(entry.doi))
    if not any((c.abstract or "").strip() for c in cands):
        cands.extend(search_openalex(entry.title))
        if use_crossref:
            cands.extend(search_crossref(entry.title))
    return cands


def enrich_missing(
    library: Library,
    limit: int = 10,
    use_crossref: bool = True,
) -> dict:
    """Try to fill abstracts for up to ``limit`` entries; mutate them in place.

    Returns a JSON-friendly report: counts plus one detail row per entry.
    """
    todo = [e for e in library.entries if not (e.abstract or "").strip()]
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, MAX_ENRICH_PER_REQUEST))
    batch = todo[:limit]

    details: list[dict] = []
    enriched = 0
    errors = 0
    for entry in batch:
        try:
            abstract = abstract_from_candidates(entry, candidates_for(entry, use_crossref))
        except Exception as exc:  # noqa: BLE001 - one bad entry must not abort the batch
            errors += 1
            details.append(
                {
                    "title": entry.title,
                    "status": "error",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        if abstract:
            entry.abstract = abstract
            enriched += 1
            details.append(
                {"title": entry.title, "status": "enriched", "chars": len(abstract)}
            )
        else:
            details.append({"title": entry.title, "status": "missing"})

    remaining = sum(1 for e in library.entries if not (e.abstract or "").strip())
    return {
        "tried": len(batch),
        "enriched": enriched,
        "missing": len(batch) - enriched - errors,
        "errors": errors,
        "total_missing": len(todo),
        "remaining": remaining,
        "details": details,
    }
