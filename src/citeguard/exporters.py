"""Reference export formats that Chinese reference managers accept.

Wanfang / CNKI / NoteExpress / EndNote all import RIS (``.ris``) and EndNote
(``.enw``).  Keeping the mapping here -- rather than in the web layer -- lets
the CLI and the report bundle reuse it, and makes the mapping unit-testable.

We map the GB/T document-type marker (``[J]``/``[M]``/``[D]`` ...) to the RIS
``TY`` tag.  Unknown or missing markers fall back to ``GEN`` (generic), which
every manager accepts; we never guess ``JOUR`` for, say, a thesis.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from citeguard.reference_parser import Reference

# GB/T 7714-2025 document-type codes -> (RIS TY, EndNote %0, human label).
_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    "J": ("JOUR", "Journal Article", "期刊"),
    "M": ("BOOK", "Book", "专著"),
    "D": ("THES", "Thesis", "学位论文"),
    "C": ("CPAPER", "Conference Paper", "会议论文"),
    "G": ("GEN", "Generic", "汇编"),
    "N": ("NEWS", "Newspaper Article", "报纸"),
    "R": ("RPRT", "Report", "报告"),
    "S": ("STAND", "Standard", "标准"),
    "P": ("PAT", "Patent", "专利"),
    "DB": ("DATA", "Dataset", "数据集"),
    "CP": ("PAT", "Patent", "专利"),
    "EB": ("ELEC", "Web Page", "电子资源"),
    "A": ("GEN", "Generic", "析出文献"),
    "Z": ("GEN", "Generic", "其他"),
}

# ``[J]``, ``[EB/OL]``, ``[D]`` ... anywhere in doc_type or the raw line.
_MARKER_RE = re.compile(r"\[\s*(EB|CP|DB|J|M|D|C|G|N|R|S|P|A|Z)\s*(?:/\s*(?:OL|CD|DK))?\s*\]", re.I)


def _type_code(ref: Reference) -> str:
    """Best-effort GB/T type code for one reference."""
    for candidate in (ref.doc_type or "", ref.raw or ""):
        m = _MARKER_RE.search(candidate)
        if m:
            return m.group(1).upper()
        # Older parsers stored the bare letter (``"J"``) in doc_type.
        if len(candidate.strip()) <= 2 and candidate.strip().upper() in _TYPE_MAP:
            return candidate.strip().upper()
    return ""


def _clean(value: str | None) -> str:
    """Collapse line breaks so one field cannot break the record layout."""
    return re.sub(r"\s+", " ", (value or "")).strip()


def _pages(ref: Reference) -> tuple[str, str]:
    pages = _clean(ref.pages)
    if not pages:
        return "", ""
    parts = re.split(r"\s*[-–—]\s*", pages, maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], ""


def _ris_authors(ref: Reference) -> list[str]:
    authors = [a for a in (_clean(x) for x in ref.authors) if a]
    return authors


def ref_to_ris(ref: Reference) -> str:
    code = _type_code(ref)
    ty = _TYPE_MAP.get(code, ("GEN", "Generic", "其他"))[0]
    lines = [f"TY  - {ty}"]
    lines.append(f"TI  - {_clean(ref.title) or _clean(ref.raw)[:300]}")
    for author in _ris_authors(ref):
        lines.append(f"AU  - {author}")
    if ref.venue:
        tag = "T2" if ty in {"CPAPER", "CHAP"} else "JO"
        lines.append(f"{tag}  - {_clean(ref.venue)}")
    if ref.year:
        lines.append(f"PY  - {ref.year}")
    if ref.volume:
        lines.append(f"VL  - {_clean(ref.volume)}")
    if ref.issue:
        lines.append(f"IS  - {_clean(ref.issue)}")
    sp, ep = _pages(ref)
    if sp:
        lines.append(f"SP  - {sp}")
    if ep:
        lines.append(f"EP  - {ep}")
    if ref.publisher:
        lines.append(f"PB  - {_clean(ref.publisher)}")
    if ref.place:
        lines.append(f"CY  - {_clean(ref.place)}")
    if ref.institution:
        lines.append(f"PB  - {_clean(ref.institution)}")
    if ref.doi:
        lines.append(f"DO  - {_clean(ref.doi)}")
    if ref.url:
        lines.append(f"UR  - {_clean(ref.url)}")
    if ref.standard_no:
        lines.append(f"SN  - {_clean(ref.standard_no)}")
    if ref.patent_no:
        lines.append(f"M1  - {_clean(ref.patent_no)}")
    if ref.access_date:
        lines.append(f"Y2  - {_clean(ref.access_date)}")
    # Keep the original citation text so a user can trace an odd record back
    # to the line the parser saw -- without it, RIS re-imports silently hide
    # parsing mistakes.
    raw = _clean(ref.raw)
    if raw:
        lines.append(f"N1  - raw: {raw[:500]}")
    lines.append("ER  - ")
    return "\n".join(lines)


def ref_to_enw(ref: Reference) -> str:
    code = _type_code(ref)
    label = _TYPE_MAP.get(code, ("GEN", "Generic", "其他"))[1]
    lines = [f"%0 {label}"]
    lines.append(f"%T {_clean(ref.title) or _clean(ref.raw)[:300]}")
    for author in _ris_authors(ref):
        lines.append(f"%A {author}")
    if ref.venue:
        tag = "%J" if label in {"Journal Article", "Newspaper Article"} else "%B"
        lines.append(f"{tag} {_clean(ref.venue)}")
    if ref.year:
        lines.append(f"%D {ref.year}")
    if ref.volume:
        lines.append(f"%V {_clean(ref.volume)}")
    if ref.issue:
        lines.append(f"%N {_clean(ref.issue)}")
    if ref.pages:
        lines.append(f"%P {_clean(ref.pages)}")
    if ref.publisher:
        lines.append(f"%I {_clean(ref.publisher)}")
    if ref.place:
        lines.append(f"%C {_clean(ref.place)}")
    if ref.institution:
        lines.append(f"%I {_clean(ref.institution)}")
    if ref.doi:
        lines.append(f"%R {_clean(ref.doi)}")
    if ref.url:
        lines.append(f"%U {_clean(ref.url)}")
    if ref.standard_no:
        lines.append(f"%@ {_clean(ref.standard_no)}")
    return "\n".join(lines)


def refs_to_ris(refs: Iterable[Reference]) -> str:
    chunks = [ref_to_ris(ref) for ref in refs]
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def refs_to_enw(refs: Iterable[Reference]) -> str:
    # EndNote on Windows expects a UTF-8 BOM for non-ASCII author names.
    chunks = [ref_to_enw(ref) for ref in refs]
    return "\ufeff" + "\n\n".join(chunks) + ("\n" if chunks else "")


def refs_from_parsed(items: Iterable[dict]) -> list[Reference]:
    """Rebuild :class:`Reference` objects from a saved report's ``parsed`` dicts."""
    out: list[Reference] = []
    for item in items or []:
        parsed = (item or {}).get("parsed") if isinstance(item, dict) else None
        if not isinstance(parsed, dict):
            continue
        known = {f for f in Reference.__dataclass_fields__}  # type: ignore[attr-defined]
        payload = {k: v for k, v in parsed.items() if k in known}
        try:
            out.append(Reference(**payload))
        except TypeError:
            continue
    return out
