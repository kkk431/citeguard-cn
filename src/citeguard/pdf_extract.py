"""Document text extraction and reference-section splitting.

Supported inputs: ``.pdf`` / ``.docx`` / ``.txt`` / ``.md``.
Scanned PDFs without a text layer are reported as an explicit error so the
caller can tell the user to OCR the file first.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_REF_HEADINGS = {
    "参考文献",
    "參考文獻",
    "主要参考文献",
    "引用文献",
    "引用文獻",
    "文献列表",
    "參考書目",
    "参考书目",
    "参考资料",
    "references",
    "reference",
    "bibliography",
    "works cited",
    "literature cited",
    "cited literature",
}

SUPPORTED_SUFFIXES = (".pdf", ".docx", ".txt", ".md")

_LEGACY_WORD_HINT = (
    "暂不支持旧版 .doc 格式：请在 Word 中「另存为」.docx 或导出 PDF 后再分析。"
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(path: str | Path) -> str:
    """Extract text from .pdf/.docx/.txt/.md (kept for callers that want text only)."""
    text, _meta = extract_text_with_meta(path)
    return text


def _pdf_page_count(path: Path) -> int:
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            return len(pdf.pages)
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(path)).pages)
    except Exception:
        return 0


def extract_text_with_meta(path: str | Path) -> tuple[str, dict]:
    """Extract text and describe how it was obtained.

    The returned metadata drives the report banner: users must be able to see
    whether the text came from a PDF text layer or from OCR, because OCR output
    carries character-level errors that the verification results inherit.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    meta: dict = {
        "method": "text",
        "file_type": suffix.lstrip("."),
        "pages": 0,
        "ocr": False,
        "chars": 0,
        "warnings": [],
    }

    if suffix in {".txt", ".md"}:
        text = normalize_text(_read_text_file(path))
        meta["chars"] = len(text)
        return text, meta

    if suffix == ".docx":
        meta["method"] = "docx"
        text = _docx_text(path)
        if not text.strip():
            raise RuntimeError("Word 文件里没有读到文字：请确认正文不是纯图片/扫描件。")
        text = normalize_text(text)
        meta["chars"] = len(text)
        return text, meta

    if suffix == ".doc":
        raise ValueError(_LEGACY_WORD_HINT)

    if suffix != ".pdf":
        raise ValueError(f"不支持的文件类型 {suffix}；当前支持 PDF / DOCX / TXT / MD。")

    meta["method"] = "pdf-text"
    meta["pages"] = _pdf_page_count(path)
    garbled = False
    text = _pdf_pdfplumber(path)
    if not text.strip():
        text = _pdf_pypdf(path)
    if text.strip() and _looks_garbled(text):
        # CID/embedded fonts without a ToUnicode map produce strings such as
        # "(cid:131)(cid:243)" — parsing those would create garbage references,
        # so prefer OCR when it is available.
        garbled = True
        ocr_text = _ocr_pdf(path)
        if ocr_text.strip():
            text = ocr_text
            meta["method"] = "ocr"
            meta["ocr"] = True
        else:
            raise RuntimeError(
                "PDF 文字层损坏（CID/自定义字体编码，无法可靠提取文字）。可以："
                "1) 安装 OCR 依赖后重试（pip install -r requirements-ocr.txt）；"
                "2) 上传 Word 原稿；3) 提供可搜索 PDF。"
            )
    if not text.strip():
        text = _ocr_pdf(path)
        if not text.strip():
            raise RuntimeError(
                "PDF 中没有可提取的文字层，可能是扫描件。可以：1) 直接上传 Word 原稿；"
                "2) 安装可选 OCR 依赖后重试（pip install rapidocr-onnxruntime）；"
                "3) 先用 OCR 工具转成可搜索 PDF。"
            )
        meta["method"] = "ocr"
        meta["ocr"] = True
    if meta["ocr"]:
        pages = f"{meta['pages']} 页" if meta["pages"] else "整份文件"
        reason = (
            "PDF 文字层损坏（CID/自定义字体编码），已用 OCR 识别"
            if garbled
            else "本文件没有可用的文字层，已用 OCR 识别"
        )
        meta["warnings"].append(
            f"{reason} {pages}；识别文字可能有错字，建议核对原文后再采用核验结论。"
        )
    # Running headers/footers land in the middle of the reference list.
    text = normalize_text(strip_repeated_lines(text))
    meta["chars"] = len(text)
    return text, meta


_CID_TOKEN_RE = re.compile(r"\(cid:\d+\)")


def _looks_garbled(text: str) -> bool:
    """True when a PDF text layer is mostly CID placeholders instead of text."""
    if not text:
        return False
    cid = len(_CID_TOKEN_RE.findall(text))
    if cid >= 20:
        return True
    return cid >= 3 and cid / max(len(text), 1) > 0.01


def _read_text_file(path: Path) -> str:
    """Read a text file, tolerating UTF-8 BOM and GBK-encoded Chinese text."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


_PAGE_NUMBER_RE = re.compile(r"^[\s\-–—·|]*\d{1,4}[\s\-–—·|]*$")
_FOOTER_NOISE_RE = re.compile(
    r"^(?:doi\s*[:：]?\s*10\.\S+\s*)?\d{1,4}\s*$", re.I
)


_TYPE_MARK_RE = re.compile(r"\[[A-Z]{1,2}(?:/OL)?\]")


def _looks_like_page_furniture(key: str) -> bool:
    """Short repeated line with no sentence punctuation — a running header.

    Exception: a bare reference number like ``[12]`` repeats with only the
    digits changing (template ``[#]``), but it is part of the reference list,
    not page furniture — OCR often puts it on its own line.
    """
    if re.fullmatch(r"\[\s*\d{1,3}\s*\]", key or ""):
        return False
    return (
        len(key) <= 40
        and not _TYPE_MARK_RE.search(key)
        and ". " not in key
        and "。 " not in key
    )


def strip_repeated_lines(text: str, min_repeats: int = 3, max_len: int = 60) -> str:
    """Drop page headers/footers that repeat across pages.

    PDF text extraction puts running headers (journal name, DOI, page number)
    in the middle of the reference list, which breaks entry splitting. Two
    patterns are removed:

    - lines that repeat verbatim (running journal/section titles),
    - short furniture lines that repeat with only the page number changing
      (``"心理科学进展 187"``, ``"DOI: 10.xxxx 12"``). Reference entries are
      excluded from this rule by punctuation and by their ``[J]`` type marks.
    """
    lines = text.splitlines()
    if not lines:
        return text
    exact: dict[str, int] = {}
    templated: dict[str, int] = {}
    for line in lines:
        key = line.strip()
        if not key or len(key) > max_len:
            continue
        exact[key] = exact.get(key, 0) + 1
        template = re.sub(r"\d+", "#", key)
        templated[template] = templated.get(template, 0) + 1

    kept: list[str] = []
    for line in lines:
        key = line.strip()
        if not key:
            kept.append(line)
            continue
        template = re.sub(r"\d+", "#", key)
        repeated_exact = exact.get(key, 0) >= min_repeats
        repeated_template = (
            templated.get(template, 0) >= min_repeats and _looks_like_page_furniture(key)
        )
        page_number = bool(_PAGE_NUMBER_RE.match(line)) or bool(_FOOTER_NOISE_RE.match(key))
        if repeated_exact or repeated_template or (page_number and exact.get(key, 0) >= 2):
            continue
        kept.append(line)
    return "\n".join(kept)


def _pdf_pdfplumber(path: Path) -> str:
    try:
        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                pages.append(_page_text(page))
        return "\n".join(pages)
    except Exception:
        return ""


def _page_text(page) -> str:
    """Extract one page, handling two-column layouts.

    Chinese journals frequently print two columns; naive ``extract_text``
    interleaves the columns line by line, which destroys reference entries.
    When the words split cleanly at the page's vertical midline, each column is
    cropped and read separately.
    """
    try:
        words = page.extract_words(keep_blank_chars=False)
    except Exception:
        return page.extract_text() or ""
    if not words:
        return page.extract_text() or ""
    mid = page.width / 2.0
    left = [w for w in words if w["x1"] <= mid + 4]
    right = [w for w in words if w["x0"] >= mid - 4]
    crossing = len(words) - len(left) - len(right)
    if len(left) >= 40 and len(right) >= 40 and crossing <= max(2, 0.01 * len(words)):
        left_text = page.crop((0, 0, mid, page.height)).extract_text() or ""
        right_text = page.crop((mid, 0, page.width, page.height)).extract_text() or ""
        return left_text + "\n" + right_text
    return page.extract_text() or ""


def _pdf_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def _ocr_pdf(path: Path) -> str:
    """Optional OCR fallback for scanned PDFs (rapidocr-onnxruntime)."""
    try:
        from .ocr import ocr_pdf

        return ocr_pdf(path)
    except Exception:
        return ""


def _docx_text(path: Path) -> str:
    """Extract paragraphs and tables from a .docx in document order.

    Chinese theses often put the reference list in a table, so table rows are
    flattened to ``\\t``-separated lines instead of being dropped.
    """
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(str(path))
    blocks: list[str] = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            blocks.append(Paragraph(child, document).text)
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                line = "\t".join(cell for cell in cells if cell)
                if line:
                    blocks.append(line)
    return "\n".join(blocks)


def _normalize_heading(line: str) -> str:
    s = line.strip().lower().rstrip(":：")
    # Markdown heading marks and list bullets ("## 参考文献", "- References")
    s = re.sub(r"^[#*\-–—\s]+", "", s)
    # Numbered headings: "7 参考文献", "7. 参考文献", "7、参考文献", "IV. References"
    s = re.sub(r"^(?:[0-9]+|[ivx]+)(?:[.、)）]\s*|\s+)", "", s)
    return s.strip()


_REF_HEADING_PREFIXES = sorted(_REF_HEADINGS, key=len, reverse=True)
_HEADING_TAIL_CHARS = set("：:（(),，.．;；/ \t")


def split_references(text: str) -> tuple[str, str]:
    """Split a paper into (body, references_text).

    Recognizes Chinese/English reference headings on their own line, including
    Markdown headings, numbered headings and wrappers such as
    ``## 参考文献``, ``7 参考文献``, ``参考文献（References）`` or
    ``参考文献：[1] 张三...``.

    When the heading appears several times (table of contents, cross references),
    the last occurrence followed by a substantial block wins, because the
    reference list lives at the end of the document. If no heading is found,
    returns ``(text, "")`` so the caller can treat the whole input as a list.
    """
    lines = text.splitlines()
    hits: list[tuple[int, list[str]]] = []
    for i, line in enumerate(lines):
        s = _normalize_heading(line)
        if not s:
            continue
        for heading in _REF_HEADING_PREFIXES:
            matched = False
            inline = ""
            if s == heading:
                matched = True
            elif s.startswith(heading) and s[len(heading)] in _HEADING_TAIL_CHARS:
                matched = True
                inline = s[len(heading) :].lstrip("".join(_HEADING_TAIL_CHARS))
            if matched:
                rest = ([inline] if inline else []) + lines[i + 1 :]
                hits.append((i, rest))
                break
    if not hits:
        return text, ""
    substantial = [h for h in hits if len("\n".join(h[1]).strip()) >= 200]
    index, rest = substantial[-1] if substantial else hits[-1]
    return "\n".join(lines[:index]), "\n".join(rest)
