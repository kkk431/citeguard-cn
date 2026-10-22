"""Local reference library: verify against metadata the user already owns.

Chinese theses mostly cite Chinese journal articles that OpenAlex/Crossref do
not index. Users usually *do* have those records, exported from CNKI /
NoteExpress / EndNote / Zotero. This module reads those exports and turns them
into a local verification source:

    RIS        (CNKI / NoteExpress / Zotero "RefMan/RIS")
    EndNote    (%0 Journal Article, %T title, %A author, ...)
    BibTeX     (@article{...})
    CSL-JSON   ([{"type": "article-journal", "title": ...}])
    plain text (a GB/T 7714 reference list, parsed with the normal parser)

Nothing here performs network I/O; the library is just data the user supplied.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .metadata_verify import Candidate, norm_title, title_sim
from .reference_parser import parse_reference_list

LIBRARY_VERSION = 1


@dataclass
class LibraryEntry:
    title: str
    authors: list[str] = field(default_factory=list)
    venue: str = ""
    year: Optional[int] = None
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    abstract: str = ""
    doc_type: str = ""
    source: str = "local"
    raw: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).strip(" .;，；")


def _split_authors(value: str) -> list[str]:
    value = re.sub(r"^(?:and|和)\s+", "", (value or "").strip())
    parts = re.split(r"\s*(?:;|；|、|\band\b|&\s)\s*", value)
    return [_clean(p) for p in parts if _clean(p)]


def _year(value: str) -> Optional[int]:
    m = re.search(r"((?:19|20)\d{2})", value or "")
    return int(m.group(1)) if m else None


def _pages(first: str, last: str) -> str:
    first, last = _clean(first), _clean(last)
    if first and last and first != last:
        return f"{first}-{last}"
    return first or last


# ---------------------------------------------------------------------------
# Format parsers
# ---------------------------------------------------------------------------

_RIS_TAGS = {"TY", "TI", "T1", "AU", "A1", "JO", "JF", "T2", "PY", "Y1", "VL", "IS", "SP", "EP", "DO", "UR", "AB", "N2", "ER"}


def parse_ris(text: str) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    current: dict[str, list[str]] = {}

    def flush() -> None:
        if not current:
            return
        get = lambda *tags: next((current[t][0] for t in tags if current.get(t)), "")
        title = _clean(get("TI", "T1"))
        if not title:
            current.clear()
            return
        entry = LibraryEntry(
            title=title,
            authors=[a for tag in ("AU", "A1") for a in _split_authors(";".join(current.get(tag, [])))],
            venue=_clean(get("JO", "JF", "T2")),
            year=_year(get("PY", "Y1")),
            volume=_clean(get("VL")),
            issue=_clean(get("IS")),
            pages=_pages(get("SP"), get("EP")),
            doi=_clean(get("DO")),
            url=_clean(get("UR")),
            abstract=_clean(get("AB", "N2")),
            source="local:ris",
            raw="RIS",
        )
        entries.append(entry)
        current.clear()

    for line in (text or "").splitlines():
        m = re.match(r"^\s*([A-Z][A-Z0-9])\s{1,2}-\s?(.*)$", line)
        if not m:
            continue
        tag, value = m.group(1), m.group(2).strip()
        if tag == "TY":
            flush()
            current.clear()
            current.setdefault(tag, []).append(value)
            continue
        if tag == "ER":
            flush()
            continue
        if tag in _RIS_TAGS and value:
            current.setdefault(tag, []).append(value)
    flush()
    return entries


def parse_endnote(text: str) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    current: dict[str, list[str]] = {}

    def flush() -> None:
        if not current:
            return
        title = _clean((current.get("%T") or [""])[0])
        if title:
            entries.append(
                LibraryEntry(
                    title=title,
                    authors=[_clean(a) for a in current.get("%A", []) if _clean(a)],
                    venue=_clean((current.get("%J", current.get("%B", [""])))[0]),
                    year=_year((current.get("%D") or [""])[0]),
                    volume=_clean((current.get("%V") or [""])[0]),
                    issue=_clean((current.get("%N") or [""])[0]),
                    pages=_clean((current.get("%P") or [""])[0]),
                    doi=_clean((current.get("%R") or [""])[0]),
                    url=_clean((current.get("%U") or [""])[0]),
                    abstract=_clean((current.get("%X") or [""])[0]),
                    source="local:endnote",
                    raw="ENDNOTE",
                )
            )
        current.clear()

    for line in (text or "").splitlines():
        m = re.match(r"^\s*(%[0-9A-Z@])\s+(.*)$", line)
        if not m:
            continue
        tag, value = m.group(1), m.group(2).strip()
        if tag in {"%0", "%T"} and current and tag == "%0":
            flush()
        current.setdefault(tag, []).append(value)
    flush()
    return entries


_BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)", re.S)


def _iter_bibtex_entries(text: str):
    """Yield (type, key, body) for each @type{...} block, honouring braces."""
    i = 0
    while True:
        at = text.find("@", i)
        if at < 0:
            return
        brace = text.find("{", at)
        if brace < 0:
            return
        depth = 0
        end = -1
        for j in range(brace, len(text)):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end < 0:
            return
        head = text[at + 1 : brace].strip()
        inner = text[brace + 1 : end]
        key, _, body = inner.partition(",")
        yield head, key.strip(), body
        i = end + 1


def parse_bibtex(text: str) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    for _type, _key, body in _iter_bibtex_entries(text or ""):
        fields: dict[str, str] = {}
        for fm in _BIB_FIELD_RE.finditer(body):
            value = fm.group(2).strip()
            if value.startswith("{") and value.endswith("}"):
                value = value[1:-1]
            elif value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            fields[fm.group(1).lower()] = _clean(re.sub(r"[{}]", "", value))
        title = fields.get("title", "")
        if not title:
            continue
        entries.append(
            LibraryEntry(
                title=title,
                authors=[a for a in re.split(r"\s+and\s+", fields.get("author", "")) if a],
                venue=fields.get("journal", fields.get("booktitle", "")),
                year=_year(fields.get("year", "")),
                volume=fields.get("volume", ""),
                issue=fields.get("number", fields.get("issue", "")),
                pages=_clean(fields.get("pages", "")).replace("--", "-"),
                doi=fields.get("doi", ""),
                url=fields.get("url", ""),
                abstract=fields.get("abstract", ""),
                source="local:bibtex",
                raw="BIBTEX",
            )
        )
    return entries


def parse_csl_json(text: str) -> list[LibraryEntry]:
    try:
        data = json.loads(text)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    entries: list[LibraryEntry] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = _clean(str(item.get("title", "")))
        if not title:
            continue
        authors = []
        for a in item.get("author") or []:
            if isinstance(a, dict):
                family, given = a.get("family", ""), a.get("given", "")
                authors.append(_clean(f"{family} {given}".strip()))
            elif isinstance(a, str):
                authors.append(_clean(a))
        issued = item.get("issued") or {}
        year = None
        parts = issued.get("date-parts") if isinstance(issued, dict) else None
        if parts and isinstance(parts[0], list) and parts[0]:
            year = int(parts[0][0])
        entries.append(
            LibraryEntry(
                title=title,
                authors=authors,
                venue=_clean(str(item.get("container-title", ""))),
                year=year,
                volume=_clean(str(item.get("volume", ""))),
                issue=_clean(str(item.get("issue", ""))),
                pages=_clean(str(item.get("page", ""))),
                doi=_clean(str(item.get("DOI", ""))),
                url=_clean(str(item.get("URL", ""))),
                abstract=_clean(str(item.get("abstract", ""))),
                source="local:csl",
                raw="CSL-JSON",
            )
        )
    return entries


def parse_plain_references(text: str) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    for ref in parse_reference_list(text or ""):
        if not ref.title:
            continue
        entries.append(
            LibraryEntry(
                title=_clean(ref.title),
                authors=[_clean(a) for a in ref.authors],
                venue=_clean(ref.venue),
                year=ref.year,
                volume=ref.volume,
                issue=ref.issue,
                pages=ref.pages,
                doi=ref.doi,
                url=ref.url,
                doc_type=ref.doc_type,
                source="local:text",
                raw=ref.raw,
            )
        )
    return entries


def detect_format(text: str, filename: str = "") -> str:
    suffix = Path(filename).suffix.lower()
    head = (text or "")[:2000]
    if suffix == ".ris" or re.search(r"^\s*TY\s{1,2}-", head, re.M):
        return "ris"
    if suffix == ".bib" or re.search(r"^@\w+\s*\{", head, re.M):
        return "bibtex"
    if suffix in {".json", ".csl"} or head.lstrip().startswith(("[", "{")):
        return "csl"
    if re.search(r"^\s*%[0TAJDRVNPU]\s+", head, re.M):
        return "endnote"
    return "text"


def parse_library_text(text: str, filename: str = "") -> list[LibraryEntry]:
    fmt = detect_format(text, filename)
    parser = {
        "ris": parse_ris,
        "bibtex": parse_bibtex,
        "csl": parse_csl_json,
        "endnote": parse_endnote,
        "text": parse_plain_references,
    }[fmt]
    entries = parser(text)
    # Drop duplicates by normalized title, keeping the richer record.
    seen: dict[str, LibraryEntry] = {}
    for entry in entries:
        key = norm_title(entry.title)
        if not key:
            continue
        old = seen.get(key)
        if old is None or (len(entry.doi) + len(entry.venue) > len(old.doi) + len(old.venue)):
            seen[key] = entry
    return list(seen.values())


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

class Library:
    """A searchable set of user-supplied reference records."""

    def __init__(self, entries: Iterable[LibraryEntry] = ()) -> None:
        self.entries: list[LibraryEntry] = list(entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __bool__(self) -> bool:
        return bool(self.entries)

    def add(self, entries: Iterable[LibraryEntry]) -> None:
        seen = {norm_title(e.title) for e in self.entries}
        for entry in entries:
            key = norm_title(entry.title)
            if key and key not in seen:
                self.entries.append(entry)
                seen.add(key)

    def search(self, title: str, year: Optional[int] = None, limit: int = 5) -> list[tuple[float, LibraryEntry]]:
        if not title:
            return []
        target = norm_title(title)
        scored: list[tuple[float, int, LibraryEntry]] = []
        for entry in self.entries:
            sim = title_sim(title, entry.title)
            if sim < 0.55:
                continue
            year_bonus = 1 if (year and entry.year and year == entry.year) else 0
            scored.append((sim, year_bonus, entry))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [(sim, entry) for sim, _, entry in scored[:limit]]

    def to_dict(self) -> dict:
        return {
            "version": LIBRARY_VERSION,
            "count": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Library":
        entries = [LibraryEntry(**e) for e in data.get("entries", []) if isinstance(e, dict)]
        return cls(entries)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Library":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return cls()


def entry_to_candidate(entry: LibraryEntry) -> Candidate:
    return Candidate(
        source="local",
        title=entry.title,
        doi=entry.doi,
        year=entry.year,
        authors=list(entry.authors),
        venue=entry.venue,
        volume=entry.volume,
        issue=entry.issue,
        pages=entry.pages,
        url=entry.url,
        abstract=entry.abstract,
    )
