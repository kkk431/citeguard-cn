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
# English-style: "45(3)" handled above; also "Vol. 45, No. 3" / "vol 45 no 3"
VOL_NO_RE = re.compile(r"\bvol(?:ume)?\.?\s*(\d+)\b", re.I)
ISS_NO_RE = re.compile(r"\bno\.?\s*(\d+)\b", re.I)
PAGES_RE = re.compile(r":\s*(\d+)\s*[-–—~～]\s*(\d+)")
PP_PAGES_RE = re.compile(r"\bpp?\.?\s*(\d+)\s*[-–—~～]\s*(\d+)", re.I)
PAGE_RE = re.compile(r":\s*(\d+)")
EDITION_RE = re.compile(r"第\s*([0-9一二三四五六七八九十]+)\s*版")
IN_PREFIX_RE = re.compile(r"^(?:in|In|IN)\s*[:：]\s*")
INDEX_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[\.、)]|[（(](\d+)[)）])\s*")
ACCESS_DATE_RE = re.compile(r"[\[(]\s*((?:19|20)\d{2}-\d{2}-\d{2})\s*[\])]")
# 电子资源写法 "(更新日期)[引用日期]": the bracketed date is the access date.
ACCESS_DATE_BRACKET_RE = re.compile(r"[(（]?\s*\[((?:19|20)\d{2}-\d{2}-\d{2})\s*\]")
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


_APA_YEAR_MARK_RE = re.compile(r"[（(]((?:19|20)\d{2})[a-z]?[)）]\s*[.．]\s*")


_LEADING_ID_RE = re.compile(
    r"^(?:(?:https?://\S+|doi\s*[:：]\s*\S+|10\.\d{4,9}/\S+)\s+)+", re.I
)


def _strip_leading_ids(text: str) -> str:
    """Remove stray URLs/DOIs that PDF extraction glued to the next entry.

    A DOI printed at the end of one reference can land at the start of the next
    entry (column/page boundaries); left in place it hijacks that entry's DOI.
    """
    cleaned = _LEADING_ID_RE.sub("", (text or "").strip())
    return cleaned.strip()


def _split_apa_entries(text: str) -> list[str]:
    """Split an APA-style list where entries start with ``作者(年份).``."""
    marks = list(_APA_YEAR_MARK_RE.finditer(text))
    if len(marks) < 3:
        return []
    starts: list[int] = []
    for m in marks:
        # The entry starts right after the previous entry's final period. Author
        # initials also look like sentence ends ("..., J. D. (1978)."), so skip
        # boundaries that are immediately followed by the year itself.
        dots = list(re.finditer(r"[.．][ \t\n]+", text[: m.start()]))
        start = 0
        for dot in reversed(dots):
            if not re.match(r"[（(]\s*(?:19|20)\d{2}", text[dot.end() :]):
                start = dot.end()
                break
        starts.append(start)
    entries: list[str] = []
    unique = sorted(set(starts))
    for k, start in enumerate(unique):
        end = unique[k + 1] if k + 1 < len(unique) else len(text)
        block = _strip_leading_ids(text[start:end])
        if _looks_like_entry(block):
            entries.append(re.sub(r"\s*\n\s*", " ", block))
    return entries


_ENTRY_LETTER_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]")


def _looks_like_entry(block: str) -> bool:
    """Reject fragments such as a lone page number or a bare URL tail."""
    if len(block.strip()) < 8:
        return False
    if not _ENTRY_LETTER_RE.search(block):
        return False
    # A page number followed by nothing useful ("1177.") is not a reference.
    if re.fullmatch(r"\s*\d{1,5}\s*[.。]?\s*", block):
        return False
    return True


def split_entries(refs_text: str) -> list[str]:
    """Split a reference section into entries.

    Primary split: a new line starting with [n] / n. / (n).
    Fallback: inline ``[n]`` markers inside a single paragraph (common when the
    list is copy-pasted from Word), then blank-line blocks, then line-by-line.
    """
    text = normalize_text(refs_text)
    if not text.strip():
        return []
    lines = text.splitlines()
    starts: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not INDEX_RE.match(stripped):
            continue
        # "2025. https://..." is a wrapped continuation line, not entry number 2025.
        m = re.match(r"^(\d{1,5})[.、)]", stripped)
        if m and len(m.group(1)) == 4 and re.match(r"(?:19|20)\d{2}$", m.group(1)):
            continue
        starts.append(i)

    # APA-ish lists: every entry starts with authors followed by "(year).".
    # Computed before choosing a split because some PDFs have a couple of
    # numbered lines (page furniture) while the real list is author-date.
    apa = [e for e in _split_apa_entries(text) if _looks_like_entry(e)]

    if len(starts) >= 2 and len(apa) <= len(starts):
        entries: list[str] = []
        for k, start in enumerate(starts):
            end = starts[k + 1] if k + 1 < len(starts) else len(lines)
            block = _strip_leading_ids("\n".join(lines[start:end]).strip())
            if _looks_like_entry(block):
                entries.append(re.sub(r"\s*\n\s*", " ", block))
        return entries
    # One-paragraph lists: split wherever a bracketed index is followed by text.
    marks = list(re.finditer(r"\[(\d{1,3})\]\s*(?=\S)", text))
    if len(marks) >= 2 and len(apa) < len(marks):
        entries = []
        for k, m in enumerate(marks):
            end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
            block = _strip_leading_ids(text[m.start() : end].strip())
            if _looks_like_entry(block):
                entries.append(re.sub(r"\s*\n\s*", " ", block))
        if entries:
            return entries
    if len(apa) >= 3:
        return apa
    blocks = [
        _strip_leading_ids(b.strip())
        for b in re.split(r"\n\s*\n", text)
        if _looks_like_entry(_strip_leading_ids(b.strip()))
    ]
    if len(blocks) > 1:
        return [re.sub(r"\s*\n\s*", " ", b) for b in blocks]
    return [_strip_leading_ids(ln.strip()) for ln in lines if _looks_like_entry(ln)]


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
    # "宋玉茹, 题名[J]..." — a single author followed by a comma, no period.
    m = re.match(r"^([\u4e00-\u9fff]{2,4})\s*[,，]\s*(.+)$", left)
    if m and re.search(r"[\u4e00-\u9fff]", m.group(2)):
        return [m.group(1)], _clean(m.group(2))
    return [], _clean(left)


def _first_segment(right: str) -> str:
    """First segment of the post-type text, e.g. journal name before ', 2020'."""
    right = re.sub(r"^[\.．,，。;；:：\s]+", "", right or "")
    # Conference entries often read "In: Proceedings of ..." — drop the prefix.
    right = IN_PREFIX_RE.sub("", right)
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
    ad = ACCESS_DATE_BRACKET_RE.search(text) or ACCESS_DATE_RE.search(text)
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

    if not tm and _parse_apa(ref, text):
        return ref

    ref.authors, ref.title = _split_authors_title(left)

    ym = YEAR_RE.search(right) or YEAR_RE.search(text)
    if ym:
        ref.year = int(ym.group(1))

    vm = VOL_ISSUE_RE.search(right)
    if vm:
        ref.volume, ref.issue = vm.group(1), vm.group(2)
    else:
        # English style: "Vol. 45, No. 3"
        vol_m = VOL_NO_RE.search(right)
        if vol_m:
            ref.volume = vol_m.group(1)
        iss_m = ISS_NO_RE.search(right)
        if iss_m:
            ref.issue = iss_m.group(1)
    # Do not let a DOI/NBN prefix be mistaken for a page range.
    right_no_id = DOI_RE.sub("", right)
    pm = PAGES_RE.search(right_no_id)
    if pm:
        ref.pages = f"{pm.group(1)}-{pm.group(2)}"
    else:
        pp_m = PP_PAGES_RE.search(right_no_id)
        if pp_m:
            ref.pages = f"{pp_m.group(1)}-{pp_m.group(2)}"
        else:
            # Only accept a single page if it appears as ": 123." near the end.
            pm2 = PAGE_RE.search(right_no_id)
            if pm2:
                ref.pages = pm2.group(1)

    ed = EDITION_RE.search(text)
    if ed and ref.doc_type in {"M", "D", "R", "S"}:
        ref.version = f"第{ed.group(1)}版"

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


APA_HEAD_RE = re.compile(
    r"^(?P<authors>.+?)[（(](?P<year>(?:19|20)\d{2})[a-z]?[)）]\s*[.．]?\s*(?P<rest>.+)$"
)
BOOK_HINT_RE = re.compile(r"(出版社|出版公司|Press|Publish|Springer|Elsevier|Wiley|Book)", re.I)


def _parse_apa(ref: "Reference", text: str) -> bool:
    """Parse the APA-ish style used by many Chinese social-science journals.

    ``作者1, 作者2(2014). 题名. 刊名, 30(5), 482-495.``
    Returns True when the entry matched this style.
    """
    m = APA_HEAD_RE.match(text.strip())
    if not m:
        return False
    authors_raw = m.group("authors").strip().rstrip(",，、 ")
    rest = m.group("rest").strip()
    if not rest or len(authors_raw) > 120:
        return False
    ref.year = int(m.group("year"))
    ref.authors = [a for a in re.split(r"[,，、;；]|\s+and\s+|\s*&\s*", authors_raw) if a.strip()]
    if not ref.authors:
        ref.authors = [authors_raw]

    # Title: first sentence end that is followed by more text.
    title = rest
    tail = ""
    for dot in re.finditer(r"[.．]\s+", rest):
        candidate = rest[: dot.start()].strip()
        after = rest[dot.end() :].strip()
        if len(candidate) >= 4 and len(after) >= 4:
            title, tail = candidate, after
            break
    ref.title = _clean(title)
    if not tail:
        # "作者(年). 书名." — a standalone book/thesis-like entry.
        ref.doc_type = "M"
        return True

    # Venue: text before the volume/issue or the year-ish part.
    vm = VOL_ISSUE_RE.search(tail)
    head = tail[: vm.start()].strip() if vm else tail
    head = re.sub(r"[,，]\s*$", "", head).strip()
    ref.venue = _clean(head)
    if BOOK_HINT_RE.search(tail) and not vm:
        ref.doc_type = "M"
        ref.publisher = ref.venue
        ref.venue = ""
    else:
        ref.doc_type = "J"
    if vm:
        ref.volume, ref.issue = vm.group(1), vm.group(2)
    after_vol = tail[vm.end() :] if vm else tail
    pm = re.search(r"[,，:：]\s*(\d+)\s*[-–—~～]\s*(\d+)", after_vol)
    if pm:
        ref.pages = f"{pm.group(1)}-{pm.group(2)}"
    else:
        pm2 = re.search(r"[,，:：]\s*(\d+)\b", after_vol)
        if pm2:
            ref.pages = pm2.group(1)
    return True


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
