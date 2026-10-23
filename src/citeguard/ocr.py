"""OCR fallback for scanned PDFs (optional dependency: rapidocr-onnxruntime).

Many Chinese theses and old journal PDFs are pure images. When ``pdfplumber``
and ``pypdf`` both return no text, we render pages with pypdfium2 and run a
bundled PP-OCR model (RapidOCR, Apache-2.0) on CPU.

The dependency is optional: without it, ``extract_text`` keeps raising the
"scanned PDF, please OCR first" error, so the base install stays small.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

DEFAULT_MAX_PAGES = 30
RENDER_SCALE = 2.0  # 2x ~= 144 dpi, enough for body text


def ocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        import pypdfium2  # noqa: F401
        return True
    except Exception:
        return False


def ocr_pdf(path: str | Path, max_pages: int = DEFAULT_MAX_PAGES) -> str:
    """Render PDF pages to images and OCR them. Returns plain text."""
    try:
        import pypdfium2 as pdfium
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("扫描件 OCR 需要 pypdfium2") from exc
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "扫描件 OCR 需要可选依赖 rapidocr-onnxruntime，"
            "请先执行 pip install rapidocr-onnxruntime"
        ) from exc
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("扫描件 OCR 需要 numpy（安装 rapidocr-onnxruntime 时会自动安装）") from exc

    engine = RapidOCR()
    pdf = pdfium.PdfDocument(str(path))
    pages: list[str] = []
    try:
        for index in range(min(len(pdf), max_pages)):
            page = pdf[index]
            try:
                bitmap = page.render(scale=RENDER_SCALE)
                # RapidOCR >= 1.4 accepts str/ndarray/bytes/Path but not a PIL
                # image, so convert the rendered page to an RGB numpy array.
                image = np.array(bitmap.to_pil().convert("RGB"))
                result, _ = engine(image)
            finally:
                try:
                    page.close()
                except Exception:
                    pass
            if not result:
                continue
            # RapidOCR returns [box, text, score] entries in reading order.
            lines = [_clean_ocr_text(item[1]) for item in result if item and item[1]]
            lines = [line for line in lines if line]
            if lines:
                pages.append("\n".join(lines))
    finally:
        try:
            pdf.close()
        except Exception:
            pass
    return _merge_reference_numbers("\n\n".join(pages))


_CJK_GAP_RE = re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")
_TYPE_MARK_RE = re.compile(r"\[\s*([A-Za-z]{1,2}(?:/OL)?)\s*\]", re.I)
_REF_NUMBER_ONLY_RE = re.compile(r"^\[\s*\d{1,3}\s*\]$")
_REF_HEADING_RE = re.compile(r"^\s*(?:参考文献|參考文獻|references?)\s*$", re.I)


def _merge_reference_numbers(text: str) -> str:
    """Attach standalone reference numbers (``[12]``) to the following line.

    OCR frequently recognises the bracketed number as its own text line while
    the entry starts on the next line; without this merge the reference parser
    cannot segment the list. The rewrite is limited to the reference section to
    avoid touching citations in the body.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _REF_HEADING_RE.match(line.strip()):
            start = i
    if start is None:
        return text
    out = lines[: start + 1]
    pending = ""
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if _REF_NUMBER_ONLY_RE.match(stripped):
            pending = stripped
            continue
        if pending:
            out.append(f"{pending} {stripped}")
            pending = ""
        else:
            out.append(line)
    if pending:
        out.append(pending)
    return "\n".join(out)


def _clean_ocr_text(text: str) -> str:
    """OCR often inserts spaces between Chinese characters; drop those."""
    cleaned = _CJK_GAP_RE.sub("", str(text or "").strip())
    # "[ J ]" / "[j]" -> "[J]" so the type marker survives OCR spacing.
    cleaned = _TYPE_MARK_RE.sub(lambda m: f"[{m.group(1).upper()}]", cleaned)
    # Normalise full-width punctuation spacing noise a little.
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def ocr_image(path: str | Path) -> str:
    """OCR a single image file (used by tests / manual checks)."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("OCR 需要可选依赖 rapidocr-onnxruntime") from exc

    engine = RapidOCR()
    result, _ = engine(str(path))
    if not result:
        return ""
    return "\n".join(_clean_ocr_text(item[1]) for item in result if item and item[1])
