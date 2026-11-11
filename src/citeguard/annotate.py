"""Annotated PDF: pin problems to the page margin where the reference lives.

Pure-Python (pypdf) so the core stays Apache-2.0 clean. Page mapping is a text
search over extracted page text; when a reference cannot be located, it is
counted as unmapped instead of being placed on a misleading page.
"""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText

_SPACE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACE.sub(" ", (text or "")).strip().lower()


def locate_page(page_texts: list[str], ref: dict) -> int | None:
    """Return the 0-based page index whose text mentions this reference."""
    parsed = ref.get("parsed") or {}
    title = _norm(parsed.get("title") or "")
    raw = _norm(ref.get("raw") or "")
    index = ref.get("index")
    for i, text in enumerate(page_texts):
        norm = _norm(text)
        if not norm:
            continue
        if title and len(title) >= 12 and title in norm:
            return i
        if raw and len(raw) >= 20 and raw[:60] in norm:
            return i
        if index is not None and re.search(r"\[\s*%d\s*\]" % int(index), norm):
            return i
    return None


def _note(ref: dict) -> str:
    verify = ref.get("verify") or {}
    status = verify.get("status") or "Unknown"
    lines = [f"#{ref.get('index', '?')} {status}"]
    issues = (ref.get("compliance") or {}).get("issues") or []
    shown = 0
    for issue in issues:
        level = (issue.get("level") or "").lower()
        if level not in {"error", "warning"}:
            continue
        lines.append("- " + str(issue.get("message") or "")[:60])
        shown += 1
        if shown >= 2:
            break
    support = (ref.get("support") or {}).get("label")
    if support in {"contradict", "partial", "no_evidence"}:
        lines.append("- support: " + support)
    return "\n".join(lines)


def annotate_pdf(input_pdf: str | Path, report: dict, output_pdf: str | Path) -> dict:
    """Write a copy of ``input_pdf`` with margin notes for problem references."""
    reader = PdfReader(str(input_pdf))
    page_texts = []
    for page in reader.pages:
        try:
            page_texts.append(page.extract_text() or "")
        except Exception:
            page_texts.append("")

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    annotated = 0
    unmapped = 0
    for ref in report.get("references") or []:
        verify = ref.get("verify") or {}
        status = verify.get("status") or "Unknown"
        support = (ref.get("support") or {}).get("label")
        issues = (ref.get("compliance") or {}).get("issues") or []
        has_error = any((i.get("level") or "").lower() == "error" for i in issues)
        if status == "Exact" and support not in {"contradict", "partial"} and not has_error:
            continue
        page_no = locate_page(page_texts, ref)
        if page_no is None:
            unmapped += 1
            continue
        page = writer.pages[page_no]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        rect = (width - 196, height - 116, width - 8, height - 18)
        annotation = FreeText(
            text=_note(ref),
            rect=rect,
            font_size="7pt",
            font_color="9b2c1c",
            border_color="ff6b57",
            background_color="fff6e6",
        )
        writer.add_annotation(page_number=page_no, annotation=annotation)
        annotated += 1

    out = Path(output_pdf)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        writer.write(fh)
    return {"annotated": annotated, "unmapped": unmapped, "pages": len(reader.pages), "path": str(out)}
