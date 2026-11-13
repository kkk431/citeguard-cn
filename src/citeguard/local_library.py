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

LIBRARY_VERSION = 2  # version 2 added per-entry tags

MAX_TAGS = 8
MAX_TAG_LENGTH = 24


class LibraryError(ValueError):
    """Invalid library operation (unknown entry, bad tag, illegal merge)."""


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
    tags: list[str] = field(default_factory=list)

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


_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)


def _doi_key(value: str) -> str:
    """Normalise a DOI for equality checks (prefix/case insensitive)."""
    text = _DOI_PREFIX_RE.sub("", (value or "").strip())
    return text.strip().lower()


def _clean_tag(value: str) -> str:
    """Collapse whitespace inside a tag but keep its punctuation/case."""
    return re.sub(r"\s+", " ", (value or "").strip()).strip()


def _normalize_tags(tags, *, strict: bool = True) -> list[str]:
    """Validate/dedupe tags (first spelling wins, max 8, each <= 24 chars)."""
    if tags is None:
        return []
    if isinstance(tags, (str, bytes, dict)) or not isinstance(tags, Iterable):
        raise LibraryError("tags 必须是字符串列表")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        if not isinstance(raw, str):
            raise LibraryError("标签必须是字符串")
        tag = _clean_tag(raw)
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            if strict:
                raise LibraryError(
                    f"标签「{tag[:12]}…」超过 {MAX_TAG_LENGTH} 个字符"
                )
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(tag)
    if len(cleaned) > MAX_TAGS:
        if strict:
            raise LibraryError(f"标签最多 {MAX_TAGS} 个，当前 {len(cleaned)} 个")
        cleaned = cleaned[:MAX_TAGS]
    return cleaned


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

# Fields copied from a dropped duplicate when the kept entry has them empty.
_MERGE_FIELDS = (
    "title",
    "venue",
    "volume",
    "issue",
    "pages",
    "doi",
    "url",
    "abstract",
    "doc_type",
    "source",
    "raw",
)


class Library:
    """A searchable set of user-supplied reference records."""

    def __init__(self, entries: Iterable[LibraryEntry] = ()) -> None:
        self.entries: list[LibraryEntry] = list(entries)
        self._path: Optional[Path] = None

    def __len__(self) -> int:
        return len(self.entries)

    def __bool__(self) -> bool:
        return bool(self.entries)

    def add(self, entries: Iterable[LibraryEntry]) -> None:
        seen = {norm_title(e.title) for e in self.entries}
        seen_dois = {(e.doi or "").strip().lower() for e in self.entries if e.doi}
        for entry in entries:
            key = norm_title(entry.title)
            doi = (entry.doi or "").strip().lower()
            if doi and doi in seen_dois:
                continue
            if key and key not in seen:
                self.entries.append(entry)
                seen.add(key)
                if doi:
                    seen_dois.add(doi)

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

    # -- tags ------------------------------------------------------------
    #
    # "id" below is the 0-based position in ``Library.entries``, matching the
    # index used by the existing web API (/api/library/{index}).  It is only
    # stable until the next add/merge, so callers should resolve and use it in
    # the same request.

    def _resolve_entry(self, key_or_doi_or_id) -> LibraryEntry:
        """Find one entry by id, DOI, or exact (normalised) title."""
        if isinstance(key_or_doi_or_id, bool):
            raise LibraryError("条目 id 必须是非负整数")
        if isinstance(key_or_doi_or_id, int):
            index = key_or_doi_or_id
            if index < 0 or index >= len(self.entries):
                raise LibraryError(f"条目 id 越界：{index}（共 {len(self.entries)} 条）")
            return self.entries[index]
        if not isinstance(key_or_doi_or_id, str) or not key_or_doi_or_id.strip():
            raise LibraryError("请提供条目 id、DOI 或题名")
        needle = key_or_doi_or_id.strip()
        if needle.isdigit():
            return self._resolve_entry(int(needle))
        doi = _doi_key(needle)
        if doi:
            matches = [e for e in self.entries if _doi_key(e.doi) == doi]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise LibraryError(f"DOI「{needle}」对应 {len(matches)} 条记录，请改用 id")
        title_key = norm_title(needle)
        matches = [e for e in self.entries if title_key and norm_title(e.title) == title_key]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise LibraryError(f"题名「{needle[:32]}」对应 {len(matches)} 条记录，请改用 id")
        raise LibraryError(f"找不到题录：{needle[:32]}")

    def set_tags(self, key_or_doi_or_id, tags: Iterable[str]) -> LibraryEntry:
        """Replace an entry's tags; returns the updated entry."""
        entry = self._resolve_entry(key_or_doi_or_id)
        entry.tags = _normalize_tags(tags)
        return entry

    def add_tags(self, key_or_doi_or_id, tags: Iterable[str]) -> LibraryEntry:
        """Append tags (deduplicated case-insensitively); returns the entry."""
        entry = self._resolve_entry(key_or_doi_or_id)
        entry.tags = _normalize_tags([*entry.tags, *_normalize_tags(tags)])
        return entry

    def remove_tags(self, key_or_doi_or_id, tags: Iterable[str]) -> LibraryEntry:
        """Remove tags case-insensitively; unknown tags are ignored."""
        entry = self._resolve_entry(key_or_doi_or_id)
        removing = {tag.casefold() for tag in _normalize_tags(tags)}
        if removing:
            entry.tags = [tag for tag in entry.tags if tag.casefold() not in removing]
        return entry

    # -- duplicates ------------------------------------------------------

    def find_duplicates(self) -> list[dict]:
        """Group likely duplicates by shared DOI or normalised title + year.

        Returns ``[{"ids": [...], "entries": [...], "reason": ...}]`` with
        0-based ids (stable until the library is mutated).  Nothing is deleted
        or merged; call :meth:`merge_duplicates` after the user confirms.
        """
        count = len(self.entries)
        parent = list(range(count))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: int, b: int) -> None:
            root_a, root_b = find(a), find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        doi_groups: dict[str, list[int]] = {}
        title_groups: dict[tuple[str, int], list[int]] = {}
        for i, entry in enumerate(self.entries):
            doi = _doi_key(entry.doi)
            if doi:
                doi_groups.setdefault(doi, []).append(i)
            title_key = norm_title(entry.title)
            if title_key and entry.year is not None:
                title_groups.setdefault((title_key, entry.year), []).append(i)
        for group in (*doi_groups.values(), *title_groups.values()):
            for other in group[1:]:
                union(group[0], other)

        buckets: dict[int, list[int]] = {}
        for i in range(count):
            buckets.setdefault(find(i), []).append(i)

        groups: list[dict] = []
        for ids in buckets.values():
            if len(ids) < 2:
                continue
            doi_counts: dict[str, int] = {}
            title_counts: dict[tuple[str, int], int] = {}
            for i in ids:
                entry = self.entries[i]
                doi = _doi_key(entry.doi)
                if doi:
                    doi_counts[doi] = doi_counts.get(doi, 0) + 1
                title_key = norm_title(entry.title)
                if title_key and entry.year is not None:
                    key = (title_key, entry.year)
                    title_counts[key] = title_counts.get(key, 0) + 1
            has_doi = any(n > 1 for n in doi_counts.values())
            has_title = any(n > 1 for n in title_counts.values())
            if has_doi and has_title:
                reason = "doi+title_year"
            elif has_doi:
                reason = "doi"
            else:
                reason = "title_year"
            groups.append(
                {
                    "ids": ids,
                    "entries": [self.entries[i].to_dict() for i in ids],
                    "reason": reason,
                }
            )
        groups.sort(key=lambda group: group["ids"][0])
        return groups

    def merge_duplicates(self, keep_id, drop_ids: Iterable) -> int:
        """Merge ``drop_ids`` into ``keep_id`` and return the number merged.

        The kept record wins every non-empty field; empty fields are filled
        from the dropped records in the given order.  Tags are unioned.  The
        operation is rejected (``LibraryError``) when an id is unknown, the
        kept id is also listed for deletion, no drops were given, or the
        merged tag list would exceed ``MAX_TAGS``.  The library is saved when
        it knows its JSON path (i.e. after ``load``/``save``).
        """
        keep = self._resolve_entry(keep_id)
        if isinstance(drop_ids, (str, bytes)) or not isinstance(drop_ids, Iterable):
            raise LibraryError("drop_ids 必须是条目 id 列表")
        drops: list[LibraryEntry] = []
        for raw in drop_ids:
            entry = self._resolve_entry(raw)
            if entry is keep:
                raise LibraryError("保留条目不能同时出现在待删除列表中")
            if all(entry is not seen for seen in drops):
                drops.append(entry)
        if not drops:
            raise LibraryError("没有需要合并的条目")

        # Validate tags before mutating, so a failure never leaves a half merge.
        merged_tags = _normalize_tags([*keep.tags, *(tag for drop in drops for tag in drop.tags)])
        for drop in drops:
            for name in _MERGE_FIELDS:
                if not getattr(keep, name) and getattr(drop, name):
                    setattr(keep, name, getattr(drop, name))
            if keep.year is None and drop.year is not None:
                keep.year = drop.year
            if not keep.authors and drop.authors:
                keep.authors = list(drop.authors)
        keep.tags = merged_tags

        dropped = {id(drop) for drop in drops}
        self.entries = [entry for entry in self.entries if entry is keep or id(entry) not in dropped]
        if self._path is not None:
            self.save(self._path)
        return len(drops)

    def to_dict(self) -> dict:
        return {
            "version": LIBRARY_VERSION,
            "count": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Library":
        entries: list[LibraryEntry] = []
        for raw in data.get("entries", []):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            # Old libraries have no tags; malformed values must not break load.
            try:
                item["tags"] = _normalize_tags(item.get("tags", []), strict=False)
            except LibraryError:
                item["tags"] = []
            entries.append(LibraryEntry(**item))
        return cls(entries)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._path = path
        # Secondary SQLite index; JSON stays authoritative. A failed index write
        # must never lose a library the user just imported.
        try:
            from .library_db import db_path_for, write_library

            write_library(self, db_path_for(path))
        except Exception:
            pass

    @classmethod
    def load(cls, path: str | Path) -> "Library":
        path = Path(path)
        if path.exists():
            try:
                library = cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
                library._path = path
                return library
            except Exception:
                pass
        # JSON missing or unreadable: fall back to the SQLite sidecar.
        try:
            from .library_db import db_path_for, read_library

            db_path = db_path_for(path)
            if db_path.exists():
                library = read_library(db_path)
                library._path = path
                return library
        except Exception:
            pass
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


def abstract_from_candidates(entry: LibraryEntry, candidates: Iterable[Candidate]) -> str:
    """Pick an abstract for a library entry from online metadata candidates.

    CNKI/EndNote/Zotero exports often carry no abstract. The claim-support judge
    needs one, so when the user opts in we fill it from OpenAlex/Crossref data.
    Only very close title matches (>= 0.92) with a compatible year are accepted:
    a wrong abstract would make the support verdict worse than "not checked".
    """
    best_sim = 0.0
    best_abstract = ""
    for cand in candidates:
        abstract = (cand.abstract or "").strip()
        if not abstract:
            continue
        sim = title_sim(entry.title, cand.title)
        if sim < 0.92:
            continue
        if entry.year and cand.year and entry.year != cand.year:
            continue
        if sim > best_sim:
            best_sim = sim
            best_abstract = abstract
    return best_abstract


# ---------------------------------------------------------------------------
# Export (backup / migration between tools)
# ---------------------------------------------------------------------------

def _bibtex_key(entry: LibraryEntry, index: int) -> str:
    surname = (entry.authors[0] if entry.authors else "anon").split(",")[0].split()[0]
    slug = re.sub(r"[^A-Za-z0-9]", "", surname).lower() or "anon"
    return f"{slug}{entry.year or 'nd'}{index}"


def to_bibtex(library: "Library") -> str:
    chunks: list[str] = []
    for index, entry in enumerate(library.entries, 1):
        fields = [
            ("title", entry.title),
            ("author", " and ".join(entry.authors)),
            ("journal", entry.venue),
            ("year", str(entry.year) if entry.year else ""),
            ("volume", entry.volume),
            ("number", entry.issue),
            ("pages", entry.pages.replace("-", "--")),
            ("doi", entry.doi),
            ("url", entry.url),
            ("abstract", entry.abstract),
        ]
        body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields if value)
        chunks.append(f"@article{{{_bibtex_key(entry, index)},\n{body}\n}}")
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def to_ris(library: "Library") -> str:
    lines: list[str] = []
    for entry in library.entries:
        lines.append("TY  - JOUR")
        lines.append(f"TI  - {entry.title}")
        for author in entry.authors:
            lines.append(f"AU  - {author}")
        if entry.venue:
            lines.append(f"JO  - {entry.venue}")
        if entry.year:
            lines.append(f"PY  - {entry.year}")
        if entry.volume:
            lines.append(f"VL  - {entry.volume}")
        if entry.issue:
            lines.append(f"IS  - {entry.issue}")
        pages = entry.pages.split("-") if entry.pages else []
        if pages:
            lines.append(f"SP  - {pages[0]}")
            if len(pages) > 1:
                lines.append(f"EP  - {pages[-1]}")
        if entry.doi:
            lines.append(f"DO  - {entry.doi}")
        if entry.url:
            lines.append(f"UR  - {entry.url}")
        if entry.abstract:
            lines.append(f"AB  - {entry.abstract}")
        lines.append("ER  - ")
        lines.append("")
    return "\n".join(lines)
