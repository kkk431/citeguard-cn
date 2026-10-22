"""Heuristic Chinese / English reference-list parser.

This is a v0 parser: it targets the common GB/T 7714 styles used by Chinese
journals and theses. It is intentionally rule-based so that every parsed field
can be inspected and unit-tested.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional

TYPE_CODES = [
    "J", "M", "D", "C", "R", "S", "P", "EB", "A", "CM",
    "DS", "PP", "G", "CP", "DB", "Z", "N",
]
TYPE_RE = re.compile(r"\[([A-Z]{1,2})(/OL)?\]")
DOI_RE = re.compile(r"(10\.\d{4,9}/[^\s,;，；]+)", re.I)
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
URL_RE = re.compile(r"https?://[^\s，；;]+")
VOL_ISSUE_RE = re.compile(r"(\d+)\s*[（(]\s*(\d+)\s*[)）]")
PAGES_RE = re.compile(r":\s*(\d+)\s*[-–—~～]\s*(\d+)")
PAGE_RE = re.compile(r":\s*(\d+)")
INDEX_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[\.、)]|[（(](\d+)[)）])\s*")
ACCESS_DATE_RE = re.compile(r"[\[(]\s*((?:19|20)\d{2}-\d{2}-\d{2})\s*[\])]")
STANDARD_NO_RE = re.compile(r"^\s*((?:GB|GB/T|ISO|IEC|JJF|YY|QB|DB\d*)\s*[\d.\-—]+\s*[-—]\s*\d{2,4})")
PATENT_NO_RE = re.compile(r"(CN\d{6,}[A-Z]?)")
REPORT_NO_RE = re.compile(r"([A-Z]{1,6}\s*[-/]?\s*\d{2,}[-—]\d{2,})")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _clean(s: str) -> str:
    return (s or "").strip().strip(" .,;，；。:：、")


def _clean_doi(s: str) -> str:
    return re.sub(r"[)\].,;，；。]+$", "", s or "").strip()


@dataclass
class Reference:
    raw: str
    index: Optional[int] = None
    authors: list[str] = field(default_factory=list)
    title: str = ""
    doc_type: str = ""
    venue: str = ""
    year: Optional[int] = None
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    publisher: str = ""
    place: str = ""
    institution: str = ""
    version: str = ""
    access_date: str = ""
    standard_no: str = ""
    patent_no: str = ""
    report_no: str = ""
    archive_no: str = ""
    scale: str = ""
    platform: str = ""
    has_online_marker: bool = False
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InTextCitation:
    raw: str
    kind: str  # numeric / author_year
    numbers: list[int] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    position: int = 0


def split_entries(refs_text: str) -> list[str]:
    """Split a reference section into entries.

    Primary split: a new line starting with [n] / n. / (n).
    Fallback: blank-line-separated blocks, then line-by-line if no blank lines.
    """
    text = normalize_text(refs_text)
    if not text.strip():
        return []
    lines = text.splitlines()
    starts: list[int] = []
    for i, line in enumerate(lines):
        if INDEX_RE.match(line.strip()):
            starts.append(i)
    if starts:
        entries: list[str] = []
        for k, start in enumerate(starts):
            end = starts[k + 1] if k + 1 < len(starts) else len(lines)
            block = "\n".join(lines[start:end]).strip()
            if block:
                entries.append(re.sub(r"\s*\n\s*", " ", block))
        return entries
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) > 1:
        return [re.sub(r"\s*\n\s*", " ", b) for b in blocks]
    return [ln.strip() for ln in lines if len(ln.strip()) > 15]


def _looks_like_authors(seg: str) -> bool:
    if not seg or len(seg) > 80:
        return False
    if any(k in seg for k in ("等", "et al", "等人")):
        return True
    if re.search(r"[,，、;；]", seg):
        return True
    # Single Chinese author (2-4 chars) or institutional author (e.g., 中国疾病预防控制中心).
    if re.fullmatch(r"[\u4e00-\u9fff\s]{2,20}", seg.strip()):
        return True
    # Single English author / a short author string without a period.
    if re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{1,79}", seg.strip()) and len(seg.split()) <= 6:
        return True
    return False


def _split_authors(seg: str) -> list[str]:
    seg = seg.strip()
    seg = re.sub(r"(等|等人|et al\.?|and others)\.?$", "", seg, flags=re.I).strip()
    parts = re.split(r"[,，、;；]\s*", seg)
    out: list[str] = []
    for p in parts:
        p = _clean(p)
        # Drop trailing English initials that were split off: "Smith J A" stays one author.
        if p:
            out.append(p)
    return out


def _looks_like_initial_split(a: str, t: str) -> bool:
    """True for 'Joseph E. | Schwartz...' — a period after an initial, not the author/title boundary."""
    toks = a.split()
    if len(toks) > 3:
        return False
    first = ""
    parts = t.split()
    if parts:
        first = re.sub(r"[,，.．;；:：]", "", parts[0])
    return bool(re.fullmatch(r"[A-Z][a-z]+", first))


def _split_authors_title(left: str) -> tuple[list[str], str]:
    """Split the pre-[type] text into authors and title."""
    left = left.strip()
    if not left:
        return [], ""
    # Chinese references: the boundary is the *last* '. ' before a CJK title.
    # This handles English author initials such as "Joseph E. Schwartz, ... 等."
    cjk_cuts = [
        m
        for m in re.finditer(r"[\.．]\s+", left)
        if re.match(r"[\u4e00-\u9fff]", left[m.end() :])
    ]
    if cjk_cuts:
        m = cjk_cuts[-1]
        a = left[: m.start()].strip()
        t = left[m.end() :].strip()
        if _looks_like_authors(a):
            return _split_authors(a), _clean(t)
    # Prefer the first '. ' whose left side looks like an author list.
    for m in re.finditer(r"[\.．]\s+", left):
        a = left[: m.start()].strip()
        t = left[m.end() :].strip()
        if not t:
            continue
        if _looks_like_initial_split(a, t):
            continue
        if _looks_like_authors(a):
            return _split_authors(a), _clean(t)
    # Fallback: Chinese refs often use '．' without space; try first Chinese author run.
    m = re.match(r"^([\u4e00-\u9fff]{2,4}(?:[,，、][\u4e00-\u9fff]{2,4})*)\s*[\.．]\s*(.+)$", left)
    if m:
        return _split_authors(m.group(1)), _clean(m.group(2))
    return [], _clean(left)


def _first_segment(right: str) -> str:
    """First segment of the post-type text, e.g. journal name before ', 2020'."""
    right = re.sub(r"^[\.．,，。;；:：\s]+", "", right or "")
    m = re.search(r"[\.．]\s+|,\s*(?=(?:19|20)\d{2})|,\s*(?=\d+\s*[（(])", right)
    seg = right[: m.start()] if m else right
    return _clean(seg)


def parse_reference(raw: str, index: Optional[int] = None) -> Reference:
    text = normalize_text(raw)
    m = INDEX_RE.match(text)
    if m:
        if index is None:
            for g in m.groups():
                if g:
                    index = int(g)
                    break
        text = text[m.end() :].strip()

    ref = Reference(raw=raw.strip(), index=index)

    dm = DOI_RE.search(text)
    if dm:
        ref.doi = _clean_doi(dm.group(1))
    um = URL_RE.search(text)
    if um:
        ref.url = _clean_doi(um.group(0))
    ad = ACCESS_DATE_RE.search(text)
    if ad:
        ref.access_date = ad.group(1)

    tm = TYPE_RE.search(text)
    if tm:
        ref.doc_type = tm.group(1)
        ref.has_online_marker = tm.group(2) == "/OL"
        left = text[: tm.start()].strip()
        right = text[tm.end() :].strip()
        right = re.sub(r"^[\.．,，。;；:：\s]+", "", right)
    else:
        ref.doc_type = "J" if (ref.doi or ref.url) else ""
        left, right = text, text

    ref.authors, ref.title = _split_authors_title(left)

    ym = YEAR_RE.search(right) or YEAR_RE.search(text)
    if ym:
        ref.year = int(ym.group(1))

    vm = VOL_ISSUE_RE.search(right)
    if vm:
        ref.volume, ref.issue = vm.group(1), vm.group(2)
    # Do not let a DOI/NBN prefix be mistaken for a page range.
    right_no_id = DOI_RE.sub("", right)
    pm = PAGES_RE.search(right_no_id)
    if pm:
        ref.pages = f"{pm.group(1)}-{pm.group(2)}"
    else:
        # Only accept a single page if it appears as ": 123." near the end.
        pm2 = PAGE_RE.search(right_no_id)
        if pm2:
            ref.pages = pm2.group(1)

    ref.venue = _first_segment(right) if ref.doc_type in {"J", "C", "N"} else ""

    if ref.doc_type == "M":
        _parse_book_fields(ref, right)
    elif ref.doc_type == "D":
        _parse_thesis_fields(ref, right)
    elif ref.doc_type == "R":
        rm = REPORT_NO_RE.search(text)
        if rm:
            ref.report_no = rm.group(1)
    elif ref.doc_type == "S":
        sm = STANDARD_NO_RE.search(text)
        if sm:
            ref.standard_no = sm.group(1)
    elif ref.doc_type == "P":
        pm_ = PATENT_NO_RE.search(text)
        if pm_:
            ref.patent_no = pm_.group(1)
    elif ref.doc_type in {"DS", "PP"}:
        _parse_dataset_or_preprint(ref, right)
        if ref.doc_type == "DS":
            ref.platform = ref.extra.get("platform", "")
            ref.version = ref.extra.get("version", "")
        else:
            ref.platform = ref.extra.get("platform", "")
            ref.version = ref.extra.get("version", "")
    elif ref.doc_type == "CM":
        ref.scale = ref.extra.get("scale", "")

    if not ref.title and ref.venue:
        ref.title = ""
    return ref


def _parse_book_fields(ref: Reference, right: str) -> None:
    # 出版地: 出版者, 年
    m = re.search(r"([^:：.．]+)[:：]\s*([^,，.．]+)[,，]\s*((?:19|20)\d{2})", right)
    if m:
        ref.place = _clean(m.group(1))
        ref.publisher = _clean(m.group(2))
        if not ref.year:
            ref.year = int(m.group(3))
    else:
        # Fallback: 出版者, 年
        m2 = re.search(r"([^,，.．]+)[,，]\s*((?:19|20)\d{2})", right)
        if m2:
            ref.publisher = _clean(m2.group(1))


def _parse_thesis_fields(ref: Reference, right: str) -> None:
    m = re.search(r"([^:：.．]+)[:：]\s*([^,，.．]+)[,，]\s*((?:19|20)\d{2})", right)
    if m:
        ref.place = _clean(m.group(1))
        ref.institution = _clean(m.group(2))
        if not ref.year:
            ref.year = int(m.group(3))
    else:
        m2 = re.search(r"([^,，.．]+)[,，]\s*((?:19|20)\d{2})", right)
        if m2:
            ref.institution = _clean(m2.group(1))


def _parse_dataset_or_preprint(ref: Reference, right: str) -> None:
    # 版本. 平台（发布或修改日期）[引用日期]. 获取路径. 永久标识符.
    parts = [p.strip() for p in re.split(r"[\.．]\s+", right) if p.strip()]
    if parts:
        ref.extra["platform"] = _clean(parts[0])
    if len(parts) > 1:
        ref.extra["version"] = _clean(parts[1])
    m = re.search(r"[（(]\s*((?:19|20)\d{2}(?:-\d{2}-\d{2})?)\s*[)）]", right)
    if m:
        ref.extra["date"] = m.group(1)


def parse_reference_list(refs_text: str) -> list[Reference]:
    entries = split_entries(refs_text)
    return [parse_reference(e, i + 1) for i, e in enumerate(entries)]


# ---------------------------------------------------------------------------
# In-text citation parsing
# ---------------------------------------------------------------------------

NUMERIC_CITE_RE = re.compile(r"\[(\d+(?:\s*[-–—,，]\s*\d+)*)\]")
AUTHOR_YEAR_CITE_RE = re.compile(
    r"[（(]\s*([^（）()]{1,40}?)\s*[,，]\s*((?:19|20)\d{2}[a-z]?)\s*[)）]"
)


def _expand_numeric(spec: str) -> list[int]:
    out: list[int] = []
    for part in re.split(r"[,，]\s*", spec):
        part = part.strip()
        m = re.fullmatch(r"(\d+)\s*[-–—]\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < b - a <= 40:
                out.extend(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def parse_intext_citations(body: str) -> list[InTextCitation]:
    cites: list[InTextCitation] = []
    for m in NUMERIC_CITE_RE.finditer(body or ""):
        nums = _expand_numeric(m.group(1))
        if nums:
            cites.append(InTextCitation(raw=m.group(0), kind="numeric", numbers=nums, position=m.start()))
    for m in AUTHOR_YEAR_CITE_RE.finditer(body or ""):
        authors = [a.strip() for a in re.split(r"[、,，;；和与]\s*", m.group(1)) if a.strip()]
        ym = re.match(r"((?:19|20)\d{2})", m.group(2))
        cites.append(
            InTextCitation(
                raw=m.group(0),
                kind="author_year",
                authors=authors,
                year=int(ym.group(1)) if ym else None,
                position=m.start(),
            )
        )
    return cites
