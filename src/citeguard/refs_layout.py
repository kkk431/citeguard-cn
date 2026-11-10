"""Layout-based reference extraction (hanging-indent lists).

Text extraction loses boundaries in two-column / hanging-indent reference lists:
continuation lines are indented ~10 pt, so joining the text makes the whole
bibliography one paragraph.  This module reads the PDF with PyMuPDF, keeps line
boxes, and starts a new entry whenever a line begins at the column's left
margin.  It is a *fallback*: callers use it only when the text splitter found
very few entries.
"""

from __future__ import annotations

import re
from pathlib import Path

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
_HEADING_RE = re.compile(r"^\s*(?:\d+\.?\s*)?(?:references|bibliography|参考文献)\s*$", re.I)


def _lines(page):
    out = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text:
                box = line.get("bbox", (0, 0, 0, 0))
                out.append((float(box[1]), float(box[0]), text))
    return out


def _column_starts(items, width):
    left = [x for _, x, _ in items if x < width * 0.55]
    right = [x for _, x, _ in items if x >= width * 0.55]
    starts = []
    for col in (left, right):
        if len(col) >= 3:
            starts.append(sorted(col)[max(0, len(col) // 10)])
    return starts or [min(x for _, x, _ in items)]


def extract_reference_entries(pdf_path, max_pages: int = 12):
    """Return reference entries using hanging-indent geometry; [] if unclear."""
    try:
        import fitz
    except Exception:
        return []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return []

    entries = []
    current = []
    started = False

    def flush():
        nonlocal current
        text = re.sub(r"\s+", " ", " ".join(current)).strip()
        if len(text) >= 30:
            entries.append(text)
        current = []

    try:
        pages = list(doc)
        start_page = None
        start_line = None
        for i, page in enumerate(pages):
            for y, x, text in _lines(page):
                if _HEADING_RE.match(text) or text.strip().lower() in {"references", "bibliography"}:
                    start_page, start_line = i, (y, x)
            if start_page is not None:
                break
        if start_page is None:
            return []

        for i in range(start_page, min(len(pages), start_page + max_pages)):
            page = pages[i]
            items = _lines(page)
            if i == start_page and start_line is not None:
                y0, x0 = start_line
                items = [it for it in items if it[0] > y0 + 1]
            if not items:
                continue
            starts = _column_starts(items, float(page.rect.width))
            groups = [[] for _ in starts]
            for it in items:
                idx = 0
                for j, sx in enumerate(starts):
                    if it[1] >= sx - 2:
                        idx = j
                groups[idx].append(it)
            for group in groups:
                if len(group) < 2:
                    continue
                margin = min(x for _, x, _ in group)
                for y, x, text in sorted(group):
                    if abs(x - margin) <= 2.5 and current:
                        flush()
                    current.append(text)
            if i > start_page:
                for y, x, text in items:
                    if re.match(r"^\s*(?:Appendix|A\.\s+[A-Z])", text) and len(text) < 60:
                        flush()
                        return [e for e in entries if _looks_like_entry(e)]
    finally:
        try:
            doc.close()
        except Exception:
            pass

    flush()
    return [e for e in entries if _looks_like_entry(e)]


def _looks_like_entry(text):
    if not 40 <= len(text) <= 1400:
        return False
    if not _YEAR_RE.search(text) and not re.search(r"(?i)\b(?:url|doi|arxiv)\b", text):
        return False
    if re.match(r"^\s*(?:table|figure|we |in this|the model)", text, re.I):
        return False
    return True

_URL_TITLE_RE = re.compile(r"^\s*(?:url|https?://|www\.|doi)", re.I)


def recover_title(entry: str) -> str:
    """Best-effort title for organisation-style entries such as
    ``AI@Meta. Llama 3 model card, 2024a. URL https://...``."""
    text = re.sub(r"\bURL\b\s+\S+", "", entry, flags=re.I)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    parts = [p.strip(" .") for p in text.split(". ") if p.strip()]
    if len(parts) < 2:
        return ""
    cands = []
    for part in parts[1:]:
        part = re.sub(r",?\s*(?:19|20)\d{2}[a-z]?\.?$", "", part).strip(" .")
        if len(part.split()) >= 3 and not _URL_TITLE_RE.match(part):
            cands.append(part)
    return (max(cands, key=len) if cands else "")[:220]
