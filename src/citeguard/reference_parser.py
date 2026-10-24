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

_LOST_TYPE_HINTS = (
    ("D", re.compile(r"(学位论文|硕士|博士|[Dd]issertation|[Tt]hesis)")),
    ("C", re.compile(r"(会议|论文集|[Pp]roceedings|[Cc]onference|[Ss]ymposium)")),
    ("M", re.compile(r"(出版社|出版公司|[Pp]ress|[Pp]ublish|[Ss]pringer|[Ee]lsevier|[Ww]iley)")),
    ("S", re.compile(r"(标准|\[S\]|\bISO\b|\bGB/?T\b)")),
    ("P", re.compile(r"(专利|[Pp]atent)")),
)


def _infer_doc_type(right: str) -> str:
    """Guess the document type when the type marker was lost (OCR / copy-paste)."""
    text = right or ""
    for code, pattern in _LOST_TYPE_HINTS:
        if pattern.search(text):
            return code
    return "J"
# OCR often reads the closing "]" of a type marker as "." ("[J. 地理学报"):
# accept a period/full stop as the closing delimiter too, but only right after
# an uppercase type code, so ordinary bracketed text is not affected.
TYPE_RE = re.compile(r"\[([A-Z]{1,2})(/OL)?[\]\.．]")
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


def _split_volume_issue(volume: str, issue: str) -> tuple[str, str]:
    """Treat a bare year followed by "(n)" as the year+issue, not a volume.

    Chinese journals that do not use volume numbers write "刊名, 2022(4): 1-8";
    without this guard the parser reports volume="2022", which then shows up as
    a false metadata mismatch against the database record.
    """
    vol = (volume or "").strip()
    if re.fullmatch(r"(?:19|20)\d{2}", vol):
        return "", (issue or "").strip()
    return vol, (issue or "").strip()


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
# A bare URL/DOI line (e.g. a PDF that prints references as links only) is not a
# citable reference; keeping it would create a bogus "Major" verdict downstream.
# PDF page furniture also glues a page number to the link ("550. https://…").
_URL_ONLY_RE = re.compile(
    r"^(?:(?:\[\s*\d{1,3}\s*\]|\d{1,7}[.、)])\s*)*"
    r"(?:https?://|www\.|doi\s*[:：]?\s*|10\.\d{4,9}/)\S+$",
    re.I,
)
# "J. (2017)." — an APA author-initials fragment with no title (split noise).
_INITIALS_YEAR_RE = re.compile(r"^(?:[A-Z]\.\s*){1,4}(?:[（(]\s*(?:19|20)\d{2}\s*[)）]\.?)?$")

# OCR sometimes mangles the type marker itself: "[J]." can come back as "[刀."
# or "[." and "[]"; the marker still marks the author/title → source boundary.
_GARBLED_TYPE_TAIL_RE = re.compile(r"([^\]］A-Za-z0-9\n]{0,2})([\]］][\.．]?|[\.．])")
_DATE_ONLY_RE = re.compile(
    r"\s*(?:19|20)\d{2}\s*[-/.年]\s*\d{1,2}(?:\s*[-/.月]\s*\d{1,2}\s*日?)?\s*\.?\s*"
)
# OCR can drop the type code *and* the closing bracket, leaving the venue glued
# to the title: "…区域发展模式[地理学报,2026,81(4):1157-1177."  The brackets look
# like a title/venue boundary only when a venue is followed by a year and the
# entry has no valid marker at all (checked in the repair function).
_MERGED_TYPE_VENUE_RE = re.compile(
    r"(?P<body>[\u4e00-\u9fffA-Za-z0-9，,、.．。：:；;（）()《》“”\"'\s\-—–]{8,300}?)"
    r"[\[［](?P<venue>[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9（）()·\-—]{1,25})\s*[,，]\s*"
    r"(?P<year>(?:19|20)\d{2})"
)


def _repair_merged_type_marker(text: str) -> tuple[str, bool]:
    """Recover a type marker that OCR merged into the following venue name."""
    if TYPE_RE.search(text):
        return text, False
    for m in _MERGED_TYPE_VENUE_RE.finditer(text):
        body = m.group("body")
        if not re.search(r"(?:[,，、]|等)", body):
            return text, False
        if not re.search(r"[.．。]\s*[\u4e00-\u9fff]", body):
            return text, False
        bracket = m.start("venue") - 1
        return text[:bracket] + "[J]. " + text[bracket + 1 :], True
    return text, False



def _repair_garbled_type_marker(text: str) -> tuple[str, bool]:
    """Restore a lost/garbled type marker so the entry keeps its title boundary.

    RapidOCR reads a small "[J]" as "[刀." surprisingly often; without this a
    whole entry ends up with an empty type and the source text inside the title.
    """
    if TYPE_RE.search(text):
        # A valid marker already exists (e.g. the title contains "[图像]" but
        # the real type code follows later); never "repair" over it.
        return text, False
    for m in re.finditer(r"[\[［]", text):
        start = m.start()
        tail = text[start + 1 : start + 6]
        if tail.startswith(("]", "］")):
            # "[]" is handled by the empty-marker path, which also infers a type.
            continue
        if re.match(r"[A-Z]{1,2}(?:/OL)?[\]］][\.．]?", tail):
            continue  # a valid marker; nothing to repair
        gm = _GARBLED_TYPE_TAIL_RE.match(tail)
        if not gm:
            continue
        after = text[start + 1 + gm.end() : start + 1 + gm.end() + 40]
        if not re.search(r"(?:19|20)\d{2}|[，,]\s*\d|\d+\s*[（(]\s*\d", after):
            continue
        if not re.search(r"[\u4e00-\u9fffA-Za-z]", text[:start]):
            continue
        return text[:start] + "[J]. " + text[start + 1 + gm.end() :], True
    return text, False


def _looks_like_entry(block: str) -> bool:
    """Reject fragments such as a lone page number or a bare URL tail."""
    stripped = block.strip()
    if len(stripped) < 8:
        return False
    if not _ENTRY_LETTER_RE.search(block):
        return False
    # A page number followed by nothing useful ("1177.") is not a reference.
    if re.fullmatch(r"\s*\d{1,5}\s*[.。]?\s*", block):
        return False
    if _INITIALS_YEAR_RE.match(stripped):
        return False
    if _URL_ONLY_RE.match(re.sub(r"\s+", " ", stripped).rstrip(" .,;，；。")):
        return False
    # A wrapped news entry can become "[10] 2025-06-25. https://…" on its own.
    # It is the tail of the previous entry, not a new reference.
    core = INDEX_RE.sub("", stripped, count=1).strip()
    dm = _DATE_ONLY_RE.match(core)
    if dm and (re.match(r"^\s*https?://", core[dm.end() :]) or len(core) < 40):
        return False
    return True


def _looks_like_leading_entry(block: str) -> bool:
    """A genuine unnumbered first reference before the numeric markers start.

    OCR often loses only the first "[1]". Accept the block only when it looks
    like a journal entry (year + volume/issue) or carries a valid type marker,
    so page furniture / body text before the list is not swallowed.
    """
    text = block.strip()
    if not (30 <= len(text) <= 1200):
        return False
    if re.search(r"参考文献|^\s*References?\s*$", text, re.I | re.M):
        return False
    if not re.search(r"[,，、]", text):
        return False
    if not TYPE_RE.search(text) and not re.search(
        r"(?:19|20)\d{2}\s*[,，]\s*\d+\s*[（(]\s*\d+\s*[)）]", text
    ):
        return False
    return _looks_like_entry(text)


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
        if starts[0] > 0:
            leading = "\n".join(lines[: starts[0]]).strip()
            if _looks_like_leading_entry(leading):
                entries.append(re.sub(r"\s*\n\s*", " ", leading))
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
    # Interpuncts are part of transliterated names ("拉尔夫·泰勒").
    if re.fullmatch(r"[\u4e00-\u9fff·・∙•\s]{2,20}", seg.strip()):
        return True
    # Single English author / a short author string without a period.
    if re.fullmatch(r"[A-Za-z][A-Za-z .'\-]{1,79}", seg.strip()) and len(seg.split()) <= 6:
        return True
    return False


# Initials are frequently written without the final period ("Meyer, A.R"),
# especially in web references copied from a page; accept both forms.
_INITIALS_RE = re.compile(r"^(?:[A-Z]\.?(?:\s*[A-Z]\.?)*)$")
_LATIN_SURNAME_RE = re.compile(r"^[A-Za-z][A-Za-z'’\-]*$")
_ET_AL_RE = re.compile(r"^(?:et\s*al\.?|等|等人)$", re.I)

# Corporate authors are common in web/report references ("Stanford University.",
# "National Academies of Sciences, Engineering, and Medicine"). Splitting those on
# commas or "and" invents authors and hides the real title, so they are kept whole.
_ORG_WORD_RE = re.compile(
    r"\b(?:Universit(?:y|ies|ät|é)|Institute|Institution|College|School|Academ(?:y|ies)|"
    r"Association|Council|Committee|Ministry|Department|Centre|Center|Foundation|Society|"
    r"Laborator(?:y|ies)|Agency|Bureau|Commission|Organi[sz]ation|Office|Board|Union|"
    r"Network|Consortium|Alliance|Federation|Assembly|Library|Museum|Hospital)\b",
    re.I,
)
# A list ending in ", I." / ", I. N." is a complete author entry, not an
# author/title boundary in the middle of a given name ("Joseph E. | Schwartz").
_COMPLETE_AUTHOR_END_RE = re.compile(r"(?:^|[,，、]\s*)[A-Z](?:\.[A-Z])*\.?$")
_AUTHOR_CONTINUATION_RE = re.compile(r"^(?:and|&|et\s+al\.?|等|等人)\b", re.I)


def _is_et_al(token: str) -> bool:
    return bool(_ET_AL_RE.match((token or "").strip().strip(".,;，；")))


def _is_author_continuation(text: str) -> bool:
    """'and Goldstein, S.C. …' continues the author list, so it is not the title."""
    return bool(_AUTHOR_CONTINUATION_RE.match((text or "").strip()))


def _is_complete_author_list(text: str) -> bool:
    return bool(_COMPLETE_AUTHOR_END_RE.search((text or "").strip()))


def _looks_like_org(text: str) -> bool:
    """A corporate author (no sentence colon, name-like length)."""
    seg = (text or "").strip()
    if not seg or len(seg) > 130:
        return False
    if re.search(r"[:：]", seg):
        return False
    return bool(_ORG_WORD_RE.search(seg))


def _split_authors(seg: str) -> list[str]:
    seg = seg.strip()
    seg = re.sub(r"(等|等人|et al\.?|and others)\.?$", "", seg, flags=re.I).strip()
    seg = re.sub(r"^[&＆]\s*", "", seg)
    # "A and B", "A & B": each side is one author (keeps "Surname, Given" intact).
    units = [u for u in re.split(r"\s+(?:and|&)\s+|\s*&\s*", seg) if u.strip()]
    if len(units) >= 2:
        return [_clean(u) for u in units if _clean(u) and not _is_et_al(_clean(u))]
    # Chinese enumeration separators.
    units = [u for u in re.split(r"[、;；，]", seg) if u.strip()]
    if len(units) >= 2:
        return [_clean(u) for u in units if _clean(u) and not _is_et_al(_clean(u))]
    # Comma-separated: re-join "Surname, I. N." pairs that the split broke apart.
    parts = [
        _clean(p)
        for p in re.split(r"[,，]\s*", seg)
        if _clean(p) and not _is_et_al(_clean(p))
    ]
    out: list[str] = []
    i = 0
    while i < len(parts):
        current = parts[i]
        if (
            i + 1 < len(parts)
            and _LATIN_SURNAME_RE.match(current)
            and _INITIALS_RE.match(parts[i + 1])
        ):
            out.append(f"{current}, {parts[i + 1]}")
            i += 2
            continue
        out.append(current)
        i += 1
    return out


def _split_apa_authors(raw: str) -> list[str]:
    """Split a bare APA author list into whole names.

    "Brehm, S. S., Miller, R. S., & Campbell, S. M." must become three authors;
    splitting naively on every comma turns each set of initials into a separate
    "author" and makes the verifier invent author mismatches.
    """
    raw = (raw or "").strip().rstrip(",，、;； ")
    if not raw:
        return []
    # Corporate authors read like "National Academies of Sciences, Engineering,
    # and Medicine" — the commas are part of the name, not author separators.
    if _looks_like_org(raw):
        return [re.sub(r"\s+", " ", raw)]
    # "and" / "&" join the last author, so they are author separators too.
    raw = re.sub(r"\s+(?:and|&)\s+|\s*&\s*", ", ", raw, flags=re.I)
    parts = [p.strip() for p in re.split(r"[,，、;；]", raw) if p.strip()]
    out: list[str] = []
    i = 0
    while i < len(parts):
        token = parts[i].strip().strip("&＆ ").strip()
        if not token:
            i += 1
            continue
        if _is_et_al(token):
            i += 1
            continue
        if (
            i + 1 < len(parts)
            and _LATIN_SURNAME_RE.match(token)
            and _INITIALS_RE.match(parts[i + 1].strip())
        ):
            out.append(f"{token}, {parts[i + 1].strip()}")
            i += 2
            continue
        if out and re.match(r"^(?:Jr\.?|Sr\.?|II|III|IV)$", token):
            out[-1] = f"{out[-1]}, {token}"
            i += 1
            continue
        out.append(token)
        i += 1
    return out


def _looks_like_initial_split(a: str, t: str) -> bool:
    """True for 'Joseph E. | Schwartz...' — a period after an initial, not the author/title boundary."""
    if _is_complete_author_list(a):
        return False
    toks = a.split()
    if len(toks) > 3:
        return False
    first = ""
    parts = t.split()
    if parts:
        first = re.sub(r"[,，.．;；:：]", "", parts[0])
    return bool(re.fullmatch(r"[A-Z][a-z]+", first))


def _split_authors_title(left: str, ocr_hint: bool = False) -> tuple[list[str], str]:
    """Split the pre-[type] text into authors and title."""
    left = left.strip()
    if not left:
        return [], ""
    if ocr_hint and "。" in left:
        # OCR sometimes turns the author/title period into a Chinese full stop
        # ("钱皓宇。短视频营销…"). Only do this for entries whose type marker was
        # already lost, so clean references never risk a title split.
        left = left.replace("。", ". ", 1)
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
        if _is_author_continuation(t):
            continue
        if _looks_like_initial_split(a, t):
            continue
        if re.search(r"[:：]", a):
            # "Wang, L. Machine Learning: A Review" — a colon means a title.
            continue
        if _looks_like_org(a):
            return [a], _clean(t)
        if _looks_like_authors(a):
            return _split_authors(a), _clean(t)
    # Fallback: Chinese refs often use '．' without space; try first Chinese author run.
    m = re.match(
        r"^([\u4e00-\u9fff·・∙•]{2,12}(?:[,，、](?:[\u4e00-\u9fff·・∙•]{2,12}|等|等人))*)\s*[\.．]\s*(.+)$",
        left,
    )
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
    # A venue is never a link/DOI; those are appended by some journal styles.
    seg = URL_RE.sub(" ", seg)
    dm = DOI_RE.search(seg)
    if dm:
        seg = seg[: dm.start()]
    return _clean(seg)


def _clean_title_ids(title: str, url: str = "", doi: str = "") -> str:
    """Drop links / DOIs / access dates that leak into the title field."""
    out = title or ""
    for token in (url, doi):
        if token:
            out = out.replace(token, " ")
    out = re.sub(r"https?://\S+", " ", out)
    out = re.sub(r"\s*[\[(（]\s*(?:19|20)\d{2}-\d{2}-\d{2}\s*[\])）]\s*$", "", out)
    return _clean(re.sub(r"\s+", " ", out))


def _looks_like_webpage(text: str) -> bool:
    """A pure web citation: a URL, no publication year and no volume/issue.

    Chinese journals often append a URL to an otherwise normal journal entry;
    those keep their inferred ``J`` type because they have a year.
    """
    if not URL_RE.search(text or ""):
        return False
    stripped = URL_RE.sub(" ", text or "")
    if YEAR_RE.search(stripped):
        return False
    if VOL_ISSUE_RE.search(stripped):
        return False
    return True


def _merge_web_segments(segs: list[str]) -> list[str]:
    """Join segments that belong to the corporate author, not the title.

    "Harvard John A." + "Paulson School …" is one name (initial, not a full
    stop); "and Goldstein, S.C." continues the author list.
    """
    merged: list[str] = []
    for seg in segs:
        if merged and _is_author_continuation(seg):
            merged[-1] = f"{merged[-1]}. {seg}"
            continue
        if merged and re.search(r"\b[A-Z]$", merged[-1]):
            merged[-1] = f"{merged[-1]}. {seg}"
            continue
        merged.append(seg)
    return merged


def _split_webpage(text: str) -> tuple[list[str], str]:
    """Split ``机构/作者. 题名. 链接`` (type marker lost) into author and title.

    The URL is never part of the title and the leading segment is the (often
    corporate) author.  Returns ``([], "")`` when the layout is not that clear,
    so the generic splitter can decide.
    """
    without_url = _clean(URL_RE.sub(" ", text or ""))
    segs = [s.strip() for s in re.split(r"[\.．]\s+", without_url) if s.strip()]
    segs = _merge_web_segments(segs)
    if len(segs) < 2:
        return [], ""
    # "Harvard Medical School. Department of Biomedical Informatics. <title>"
    # — a sub-unit belongs to the corporate author, not to the title.
    while len(segs) > 2 and re.match(
        r"^(?:Department|Division|Institute|Centre|Center|School|College|Faculty|"
        r"Office|Programme|Program|Graduate School)\b",
        segs[1],
        re.I,
    ):
        segs[0] = f"{segs[0]}. {segs[1]}"
        segs.pop(1)
    head = _clean(segs[0])
    if not head or len(head) > 130:
        return [], ""
    if not (_looks_like_org(head) or _looks_like_authors(head)):
        return [], ""
    if _is_author_continuation(head):
        return [], ""
    title = _clean(". ".join(segs[1:]))
    if not title or _URL_ONLY_RE.match(title):
        return [], ""
    # Keep a corporate author whole: splitting it on commas / "and" invents
    # authors ("National Academies of Sciences, Engineering, and Medicine").
    authors = [head] if _looks_like_org(head) else _split_authors(head)
    return authors, title


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

    text, merged_repaired = _repair_merged_type_marker(text)
    text, marker_repaired = _repair_garbled_type_marker(text)
    if merged_repaired or marker_repaired:
        ref.extra["type_marker_lost"] = True

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
        em = re.search(r"\[\s*\]", text)
        if em:
            # OCR frequently loses the type code but keeps an empty marker
            # ("题名[]. 刊名, 2020"): treat it as the title/source boundary and
            # leave the type unknown instead of swallowing the whole entry.
            left = text[: em.start()].strip()
            right = text[em.end() :].strip()
            right = re.sub(r"^[\.．,，。;；:：\s]+", "", right)
            ref.extra["type_marker_lost"] = True
            # Infer the type from the surrounding text so the field rules can
            # still run; the inference is flagged so nothing is presented as
            # if the type code were present.
            inferred = _infer_doc_type(right)
            if inferred:
                ref.doc_type = inferred
                ref.extra["type_inferred"] = inferred
        else:
            if ref.doi:
                ref.doc_type = "J"
            elif ref.url:
                # A URL without a year/volume and without a type code is a web
                # citation (GB/T 7714 type EB), not a journal article.
                ref.doc_type = "EB" if _looks_like_webpage(text) else "J"
            else:
                ref.doc_type = ""
            left, right = text, text
            if ref.doc_type == "EB":
                authors, title = _split_webpage(text)
                if title:
                    ref.authors, ref.title = authors, title

    if not tm and _parse_apa(ref, text):
        ref.title = _clean_title_ids(ref.title, ref.url, ref.doi)
        return ref

    if not ref.title:
        ref.authors, ref.title = _split_authors_title(
            left, ocr_hint=bool(ref.extra.get("type_marker_lost"))
        )
    ref.title = _clean_title_ids(ref.title, ref.url, ref.doi)

    # DOIs/URLs carry 4-digit runs and "/" that look like years, volume or pages
    # ("10.1007/978-1-4614-2062-0" has neither a 2062 year nor a page "29").
    right_fields = URL_RE.sub(" ", DOI_RE.sub(" ", right or ""))
    text_fields = URL_RE.sub(" ", DOI_RE.sub(" ", text))

    ym = YEAR_RE.search(right_fields) or YEAR_RE.search(text_fields)
    if ym:
        ref.year = int(ym.group(1))

    vm = VOL_ISSUE_RE.search(right_fields)
    if vm:
        ref.volume, ref.issue = _split_volume_issue(vm.group(1), vm.group(2))
    else:
        # English style: "Vol. 45, No. 3"
        vol_m = VOL_NO_RE.search(right_fields)
        if vol_m:
            ref.volume = vol_m.group(1)
        iss_m = ISS_NO_RE.search(right_fields)
        if iss_m:
            ref.issue = iss_m.group(1)
    # Do not let a DOI/NBN prefix be mistaken for a page range.
    right_no_id = right_fields
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

    # Unknown type (e.g. the [J] marker was lost in OCR) still needs a source;
    # books/theses keep the venue empty because their source is the publisher.
    ref.venue = _first_segment(right) if ref.doc_type in {"J", "C", "N"} or not ref.doc_type else ""

    if ref.doc_type == "M":
        _parse_book_fields(ref, right_fields)
    elif ref.doc_type == "D":
        _parse_thesis_fields(ref, right_fields)
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


def _is_clean_field(text: str) -> bool:
    """A publisher/institution field is not a URL or a DOI fragment."""
    if not text or URL_RE.search(text) or DOI_RE.search(text):
        return False
    return not re.search(r"\d{4,9}/", text)


def _parse_book_fields(ref: Reference, right: str) -> None:
    # 出版地: 出版者, 年
    m = re.search(r"([^:：.．]+)[:：]\s*([^,，.．]+)[,，]\s*((?:19|20)\d{2})", right)
    if m:
        if _is_clean_field(m.group(1)):
            ref.place = _clean(m.group(1))
        if _is_clean_field(m.group(2)):
            ref.publisher = _clean(m.group(2))
        if not ref.year:
            ref.year = int(m.group(3))
    else:
        # Fallback: 出版者, 年
        m2 = re.search(r"([^,，.．]+)[,，]\s*((?:19|20)\d{2})", right)
        if m2 and _is_clean_field(m2.group(1)):
            ref.publisher = _clean(m2.group(1))


def _parse_thesis_fields(ref: Reference, right: str) -> None:
    m = re.search(r"([^:：.．]+)[:：]\s*([^,，.．]+)[,，]\s*((?:19|20)\d{2})", right)
    if m:
        if _is_clean_field(m.group(1)):
            ref.place = _clean(m.group(1))
        if _is_clean_field(m.group(2)):
            ref.institution = _clean(m.group(2))
        if not ref.year:
            ref.year = int(m.group(3))
    else:
        m2 = re.search(r"([^,，.．]+)[,，]\s*((?:19|20)\d{2})", right)
        if m2 and _is_clean_field(m2.group(1)):
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
    ref.authors = _split_apa_authors(authors_raw)
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
    if URL_RE.match(tail) or re.match(r"^(?:https?://|www\.)", tail, re.I):
        # "机构(年). 网页题名. https://…" — a web citation, not a journal article.
        ref.doc_type = "EB"
        return True

    # Venue: text before the volume/issue or the year-ish part.
    tail_fields = _clean_title_ids(tail, ref.url, ref.doi)
    vm = VOL_ISSUE_RE.search(tail_fields)
    head = tail_fields[: vm.start()].strip() if vm else tail_fields
    head = re.sub(r"[,，]\s*$", "", head).strip()
    ref.venue = _clean(head)
    if BOOK_HINT_RE.search(tail_fields) and not vm:
        ref.doc_type = "M"
        # "Springer, 29." — the trailing number is a page, not the publisher.
        ref.publisher = re.sub(r"[,，]\s*\d{1,6}$", "", ref.venue).strip() or ref.venue
        ref.venue = ""
    else:
        ref.doc_type = "J"
    if vm:
        ref.volume, ref.issue = _split_volume_issue(vm.group(1), vm.group(2))
    after_vol = tail_fields[vm.end() :] if vm else tail_fields
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


def _is_date_only_ref(ref: Reference) -> bool:
    """A title that is only a date is the tail of the previous entry."""
    return bool(_DATE_ONLY_RE.fullmatch(ref.title or ""))


def parse_reference_list(refs_text: str) -> list[Reference]:
    refs: list[Reference] = []
    for entry in split_entries(refs_text):
        ref = parse_reference(entry, len(refs) + 1)
        if _is_date_only_ref(ref):
            continue
        refs.append(ref)
    return refs


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
