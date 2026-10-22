"""PDF / text extraction and reference-section splitting."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_REF_HEADINGS = {
    "参考文献",
    "參考文獻",
    "references",
    "reference",
    "bibliography",
    "文献列表",
    "参考书目",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(path: str | Path) -> str:
    """Extract text from .txt/.md/.pdf. PDF uses pdfplumber first, pypdf as fallback."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return normalize_text(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".pdf":
        text = _pdf_pdfplumber(path)
        if not text.strip():
            text = _pdf_pypdf(path)
        if not text.strip():
            raise RuntimeError(
                "PDF text extraction returned empty. The PDF may be scanned; "
                "run OCR (e.g., PaddleOCR) before CiteGuard."
            )
        return normalize_text(text)
    raise ValueError(f"Unsupported file type: {suffix}")


def _pdf_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return "\n".join(pages)
    except Exception:
        return ""


def _pdf_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def split_references(text: str) -> tuple[str, str]:
    """Split a paper into (body, references_text).

    Looks for a heading line such as 参考文献 / References / Bibliography.
    If not found, returns (text, "") so callers can pass an explicit reference file.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip().lower().rstrip(":：")
        # strip Markdown heading marks and bullets: "## 参考文献", "- References"
        s = re.sub(r"^[#*\-–—\s]+", "", s).strip()
        if not s:
            continue
        if s in _REF_HEADINGS or s.startswith("参考文献") or s.startswith("參考文獻"):
            return "\n".join(lines[:i]), "\n".join(lines[i + 1 :])
        if s.startswith("references") or s.startswith("bibliography"):
            return "\n".join(lines[:i]), "\n".join(lines[i + 1 :])
    return text, ""
