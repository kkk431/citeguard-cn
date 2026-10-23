"""Render a GB/T 7714-style reference entry from database metadata.

This turns the verifier's best candidate into a string the user can paste back
into their paper: authors (first three + 等 / et al), title, type mark, source,
year, volume(issue), pages and the persistent identifier.

It is a *suggestion* built from OpenAlex/Crossref metadata; the UI labels it as
such so nobody mistakes it for an authoritative transcription of the standard.
"""
from __future__ import annotations

from typing import Optional

TYPE_LABELS = {
    "J": "J",
    "M": "M",
    "C": "C",
    "D": "D",
    "R": "R",
    "S": "S",
    "P": "P",
    "EB": "EB/OL",
    "N": "N",
}

MAX_AUTHORS = 3


def _format_authors(authors: list[str], is_cjk: bool) -> str:
    names = [a.strip() for a in (authors or []) if a and a.strip()]
    if not names:
        return ""
    if len(names) > MAX_AUTHORS:
        tail = "等" if is_cjk else "et al"
        return ", ".join(names[:MAX_AUTHORS]) + f", {tail}"
    return ", ".join(names)


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def format_gbt_entry(
    *,
    title: str,
    authors: list[str],
    doc_type: str,
    venue: str = "",
    year: Optional[int] = None,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    publisher: str = "",
    place: str = "",
    doi: str = "",
    url: str = "",
) -> str:
    """Return a single GB/T 7714-style entry (without the leading ``[n]``)."""
    type_code = TYPE_LABELS.get((doc_type or "J").upper(), "J")
    kind = (doc_type or "J").upper()
    cjk = _has_cjk(title)
    parts: list[str] = []

    author_text = _format_authors(authors, cjk)
    if author_text:
        # Initials already end with a period ("Carayannis, E.G.") — avoid "..".
        parts.append(author_text.rstrip(".．。") + ". ")

    clean_title = (title or "").strip().rstrip(".．。")
    if clean_title:
        parts.append(f"{clean_title}[{type_code}]. ")

    if kind == "M":
        # GB/T: 出版地: 出版者, 出版年
        source = f"{place}: {publisher}" if place and publisher else (place or publisher)
        if source:
            parts.append(source + ", ")
    elif kind == "EB":
        # A web page has no volume/issue/pages field; PDF parsing often invents
        # one from a course number or a URL fragment ("…: 15-619"), so drop them.
        volume = issue = pages = ""
    else:
        if venue:
            parts.append(venue.strip().rstrip(".．。") + ", ")

    if year:
        parts.append(f"{year}")
        if volume:
            parts.append(f", {volume}")
            if issue:
                parts.append(f"({issue})")
        parts.append(": " if pages else ". ")
    elif volume:
        parts.append(f"{volume}")
        if issue:
            parts.append(f"({issue})")
        parts.append(": " if pages else ". ")

    if pages:
        parts.append(f"{pages}.")

    entry = "".join(parts).strip()
    if not entry:
        return ""
    # A dangling separator happens when a later field is missing.
    entry = entry.rstrip(" ,;:、")
    entry = entry.rstrip() if entry.endswith(".") else entry + "."
    if doi:
        entry += f" DOI: {doi}."
    elif url:
        entry += f" {url}."
    return entry


def format_from_candidate(ref, cand) -> str:
    """Build the suggested entry for a parsed reference plus its best candidate."""
    if cand is None:
        return ""
    doc_type = (getattr(ref, "doc_type", "") or "J").upper()
    return format_gbt_entry(
        title=getattr(cand, "title", "") or getattr(ref, "title", ""),
        authors=list(getattr(cand, "authors", []) or getattr(ref, "authors", []) or []),
        doc_type=doc_type,
        venue=getattr(cand, "venue", "") or getattr(ref, "venue", ""),
        year=getattr(cand, "year", None) or getattr(ref, "year", None),
        volume=getattr(cand, "volume", "") or "",
        issue=getattr(cand, "issue", "") or "",
        pages=getattr(cand, "pages", "") or "",
        publisher=getattr(ref, "publisher", "") or "",
        place=getattr(ref, "place", "") or "",
        doi=getattr(cand, "doi", "") or getattr(ref, "doi", "") or "",
        url=getattr(cand, "url", "") or "",
    )


def format_from_reference(ref) -> str:
    """Re-typeset one parsed reference as GB/T 7714-2025 style.

    This is a *reformatting* of what the paper already cites (no online lookup):
    it normalises author separators, the type code, year/volume(issue)/pages
    separators and the trailing period. Fields the parser could not recover stay
    missing, so the result must still be checked against the original.
    """
    return format_gbt_entry(
        title=getattr(ref, "title", "") or "",
        authors=list(getattr(ref, "authors", []) or []),
        doc_type=(getattr(ref, "doc_type", "") or "J").upper(),
        venue=getattr(ref, "venue", "") or "",
        year=getattr(ref, "year", None),
        volume=getattr(ref, "volume", "") or "",
        issue=getattr(ref, "issue", "") or "",
        pages=getattr(ref, "pages", "") or "",
        publisher=getattr(ref, "publisher", "") or "",
        place=getattr(ref, "place", "") or "",
        doi=getattr(ref, "doi", "") or "",
        url=getattr(ref, "url", "") or "",
    )


def format_reference_list(refs) -> list[dict]:
    """Return ``[{"index": n, "entry": "..."}]`` for a whole reference list."""
    out: list[dict] = []
    for ref in refs:
        entry = format_from_reference(ref)
        out.append({"index": getattr(ref, "index", None), "entry": entry})
    return out
