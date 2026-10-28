"""Document text extraction and reference-section splitting.

Supported inputs: ``.pdf`` / ``.docx`` / ``.txt`` / ``.md``.
Scanned PDFs without a text layer are reported as an explicit error so the
caller can tell the user to OCR the file first.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

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


def extract_page_text(path: str | Path, page_number: int, *, max_chars: int = 6000) -> str:
    """Extract one 1-based page of a PDF, for figure-claim context.

    Raises ``ValueError`` with a user-facing message when the page has no usable
    text (scanned page / broken text layer); the caller should fall back to
    asking the user to paste the page text manually.
    """
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        raise ValueError("按页取正文只支持 PDF 论文（.pdf）")
    if page_number < 1:
        raise ValueError("页码从 1 开始")
    try:
        import pdfplumber
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("缺少 pdfplumber，无法按页提取 PDF 文字") from exc
    try:
        with pdfplumber.open(str(p)) as pdf:
            total = len(pdf.pages)
            if page_number > total:
                raise ValueError(f"页码超出范围：PDF 共 {total} 页")
            text = normalize_text(_page_text(pdf.pages[page_number - 1]))
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"读取 PDF 第 {page_number} 页失败：{exc}") from exc
    if not text.strip() or _looks_garbled(text):
        raise ValueError(
            f"第 {page_number} 页没有可提取的文字（可能是扫描页或文字层损坏），"
            "请手动粘贴该页正文或图注"
        )
    return text[:max_chars]


_FIG_REF_RE = re.compile(
    r"(?P<kind>图|表|figure|fig\.?|table|tab\.?)\s*(?P<num>[0-9]{1,3}(?:\.[0-9]+)?[a-zA-Z]?)",
    re.IGNORECASE,
)
_FIG_CAPTION_RE = re.compile(
    r"^\s*(?P<kind>图|表|figure|fig\.?|table|tab\.?)\s*"
    r"(?P<num>[0-9]{1,3}(?:\.[0-9]+)?[a-zA-Z]?)(?=[\s、.．:：]|$)",
    re.IGNORECASE,
)
_TABLE_KINDS = {"表", "table", "tab.", "tab"}


def _claim_ref(claim: str) -> tuple[str, str]:
    match = _FIG_REF_RE.search(claim or "")
    if not match:
        return "", ""
    return match.group("num").lower(), match.group("kind").lower().strip(". ")


def figure_number_from_claim(claim: str) -> str:
    """Return the figure/table number referenced by a claim ('' when none).

    Examples: ``如图 3 所示`` → ``3``; ``Figure 4a`` → ``4a``; ``见表 2`` → ``2``.
    """
    return _claim_ref(claim)[0]


def caption_kind_from_claim(claim: str) -> str:
    """Return ``"table"`` / ``"figure"`` / ``""`` for the claim's reference."""
    kind = _claim_ref(claim)[1]
    if kind in _TABLE_KINDS:
        return "table"
    return "figure" if kind else ""


_TOC_CAPTION_RE = re.compile(r"(?:[.．…·]{4,}|\s{6,})\s*\d+\s*$")


def _is_toc_caption(line: str) -> bool:
    """True for a table-of-contents line such as ``图 1 总体框架…… 5``."""
    line = line.strip()
    return bool(_TOC_CAPTION_RE.search(line)) or "\t" in line


def find_figure_pages(
    path: str | Path, number: str = "", *, kind: str = "", max_pages: int = 40
) -> list[tuple[int, str]]:
    """Locate every page carrying a matching figure/table caption.

    Some PDFs repeat a caption number in an appendix or reuse it for a table;
    collecting all matches lets the caller pick the page that best matches the
    claim instead of silently taking the first hit.
    """
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        return []
    target = re.sub(r"[^0-9a-z.]", "", (number or "").lower())
    try:
        import pdfplumber
    except Exception:  # pragma: no cover - dependency guard
        return []
    found_pages: list[tuple[int, str]] = []
    seen: set[int] = set()
    try:
        with pdfplumber.open(str(p)) as pdf:
            for index, page in enumerate(pdf.pages[:max_pages], start=1):
                if index in seen:
                    continue
                text = _page_text(page) or ""
                if not text.strip() or _looks_garbled(text):
                    continue
                for line in text.splitlines():
                    match = _FIG_CAPTION_RE.match(line.strip())
                    if not match:
                        continue
                    if _is_toc_caption(line):
                        continue
                    caption_kind = match.group("kind").lower().strip(". ")
                    if kind == "table" and caption_kind not in _TABLE_KINDS:
                        continue
                    if kind == "figure" and caption_kind in _TABLE_KINDS:
                        continue
                    found = re.sub(r"[^0-9a-z.]", "", match.group("num").lower())
                    if target and found != target:
                        continue
                    found_pages.append((index, line.strip()[:200]))
                    seen.add(index)
                    break
    except Exception:
        return []
    return found_pages


def _caption_similarity(claim: str, caption: str) -> float:
    """Token-coverage between a claim and a caption (works for zh + en)."""
    tokens = re.compile(r"[a-z0-9]{2,}|[\u4e00-\u9fff]")

    def bag(text: str) -> set[str]:
        return set(tokens.findall((text or "").lower()))

    want, have = bag(claim), bag(caption)
    if not want or not have:
        return 0.0
    return len(want & have) / len(want)


def find_figure_page(
    path: str | Path,
    number: str = "",
    *,
    kind: str = "",
    max_pages: int = 40,
    claim: str = "",
) -> tuple[int, str] | None:
    """Locate a figure caption (``图 N`` / ``Figure N``) in a PDF text layer.

    Returns ``(page_no, caption_line)`` for the first matching page, or ``None``
    when no caption is found. When ``claim`` is supplied and the same number
    appears on several pages, the caption whose wording overlaps the claim most
    wins (same-page-order tie-break). Scanned PDFs have no text layer, so this is
    a best-effort helper: callers must keep a manual-page fallback.
    """
    matches = find_figure_pages(path, number, kind=kind, max_pages=max_pages)
    if not matches:
        return None
    if claim and len(matches) > 1:
        return max(matches, key=lambda item: (_caption_similarity(claim, item[1]), -item[0]))
    return matches[0]


def render_page_png(path: str | Path, page_number: int, *, dpi: int = 150) -> bytes:
    """Render one PDF page to PNG bytes (for vision judgments without a screenshot)."""
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        raise ValueError("渲染页面只支持 PDF 论文（.pdf）")
    if page_number < 1:
        raise ValueError("页码从 1 开始")
    try:
        import pypdfium2 as pdfium
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "自动渲染 PDF 页面需要可选依赖 pypdfium2（pip install pypdfium2），"
            "未安装时请改为手动上传图表截图"
        ) from exc
    doc = None
    page = None
    bitmap = None
    try:
        doc = pdfium.PdfDocument(str(p))
        total = len(doc)
        if page_number > total:
            raise ValueError(f"页码超出范围：PDF 共 {total} 页")
        page = doc[page_number - 1]
        bitmap = page.render(scale=dpi / 72.0)
        image = bitmap.to_pil().convert("RGB")
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"渲染 PDF 第 {page_number} 页失败：{exc}") from exc
    finally:
        # Windows keeps the file locked until every pdfium handle is closed;
        # without this the caller cannot delete its temporary upload.
        for obj in (bitmap, page, doc):
            close = getattr(obj, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass


def extract_text_with_meta(path: str | Path, on_page=None) -> tuple[str, dict]:
    """Extract text and describe how it was obtained.

    ``on_page(done, total)`` is called while a PDF text layer is read, so the
    web job can show page-level progress on long documents instead of a blank
    “读取文件” stage.

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
    text = _pdf_pdfplumber(path, on_page=on_page) if on_page is not None else _pdf_pdfplumber(path)
    if not text.strip():
        text = _pdf_pypdf(path)
    # Some PDFs (notably arXiv/LaTeX exports) encode words with no inter-word
    # spaces, so pdfplumber returns "Neuralmachinetranslation...". PyMuPDF
    # reconstructs the spaces; switch only when it demonstrably helps. Running
    # the second extractor is not free on long papers, so skip it when the
    # first pass already looks spaced-out (few long ASCII runs).
    alt = None
    if not text.strip() or _long_ascii_runs(text) > 0:
        alt = _pdf_pymupdf(path)
        text_runs, alt_runs = _long_ascii_runs(text), _long_ascii_runs(alt)
        if alt.strip() and (text_runs > alt_runs * 2 + 3 or (alt_runs == 0 and text_runs >= 1)):
            text = alt
            meta["warnings"].append("PDF 文字层缺少词间空格，已用备用解析器恢复")
    if text.strip() and _looks_garbled(text):
        # CID/embedded fonts without a ToUnicode map produce strings such as
        # "(cid:131)(cid:243)" — parsing those would create garbage references,
        # so prefer OCR when it is available.
        garbled = True
        try:
            ocr_text = _ocr_pdf(path)
        except Exception as exc:
            raise RuntimeError(
                "PDF 文字层损坏（CID/自定义字体编码，无法可靠提取文字），"
                f"OCR 回退也失败：{_ocr_failure_hint(exc)}。可以："
                "1) 检查 OCR 运行环境（服务日志里有具体原因）；"
                "2) 上传 Word 原稿；3) 提供可搜索 PDF。"
            ) from exc
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
        try:
            ocr_text = _ocr_pdf(path)
        except Exception as exc:
            raise RuntimeError(
                "PDF 中没有可提取的文字层，可能是扫描件，"
                f"OCR 回退也失败：{_ocr_failure_hint(exc)}。可以："
                "1) 检查 OCR 运行环境（服务日志里有具体原因）；"
                "2) 直接上传 Word 原稿；3) 先用 OCR 工具转成可搜索 PDF。"
            ) from exc
        if not ocr_text.strip():
            raise RuntimeError(
                "PDF 中没有可提取的文字层，可能是扫描件。可以：1) 直接上传 Word 原稿；"
                "2) 安装可选 OCR 依赖后重试（pip install rapidocr-onnxruntime）；"
                "3) 先用 OCR 工具转成可搜索 PDF。"
            )
        text = ocr_text
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
    if cid >= 3 and cid / max(len(text), 1) > 0.01:
        return True
    # Some embedded CJK fonts decode into raw C0 control bytes instead of (cid:...).
    # A handful of controls is suspicious; a few percent is unambiguous corruption.
    ctrl = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t\f")
    return ctrl >= 30 and ctrl / max(len(text), 1) > 0.005


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


def _pdf_pdfplumber(path: Path, on_page=None) -> str:
    try:
        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages, 1):
                pages.append(_page_text(page))
                if on_page is not None:
                    try:
                        on_page(i, total)
                    except Exception:
                        pass
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


def _long_ascii_runs(text: str) -> int:
    """Count suspiciously long ASCII runs (a signal that spaces were lost)."""
    return len(re.findall(r"[A-Za-z]{25,}", text or ""))


def _pdf_pymupdf(path: Path) -> str:
    """Alternative text layer reader (handles tight LaTeX spacing better)."""
    try:
        import pymupdf
    except Exception:
        return ""
    try:
        with pymupdf.open(str(path)) as doc:
            return "\n".join(page.get_text() or "" for page in doc)
    except Exception:
        return ""


def _pdf_pypdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def _ocr_failure_hint(exc: Exception) -> str:
    """Turn an OCR exception into a short, honest user-facing reason."""
    msg = str(exc).strip() or exc.__class__.__name__
    lowered = msg.lower()
    if "需要可选依赖" in msg or "rapidocr-onnxruntime" in lowered:
        return f"未安装 OCR 依赖（{msg}）"
    if "pypdfium2" in lowered:
        return f"缺少 PDF 渲染依赖 pypdfium2（{msg}）"
    return f"{exc.__class__.__name__}: {msg}"


def _ocr_pdf(path: Path) -> str:
    """Optional OCR fallback for scanned PDFs (rapidocr-onnxruntime).

    Errors are propagated (after logging) instead of being swallowed: a broken
    OCR environment must not be reported as "the file has no text layer".
    """
    from .ocr import ocr_pdf

    try:
        return ocr_pdf(path)
    except Exception as exc:
        logger.warning("OCR fallback failed for %s: %s", path, exc, exc_info=True)
        raise


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


_APPENDIX_LETTER_RE = re.compile(r"^(?:[A-H]|[IVX]{1,3})\.?$")


def _trim_reference_appendix(rest: list[str]) -> list[str]:
    """Cut the appendix that follows the reference list.

    Some PDFs put appendices after the bibliography; the appendix's own
    section headings (``A`` + ``Related Work``) and prose then look like
    reference entries and corrupt the split.
    """
    if len(rest) < 10:
        return rest
    floor = max(5, len(rest) // 5)
    for i in range(floor, len(rest)):
        s = rest[i].strip()
        if s.lower() in {"appendix", "附录", "supplementary material"}:
            return rest[:i]
        if _APPENDIX_LETTER_RE.match(s):
            for nxt in rest[i + 1 : i + 3]:
                t = nxt.strip()
                if t and (t[0].isupper() or "\u4e00" <= t[0] <= "\u9fff"):
                    return rest[:i]
    return rest


def split_references(text: str) -> tuple[str, str]:
    """Split a paper into (body, references_text).

    Recognizes Chinese/English reference headings on their own line, including
    Markdown headings, numbered headings and wrappers such as
    ``## 参考文献``, ``7 参考文献``, ``参考文献（References）`` or
    ``参考文献：[1] 张三...``.

    When the heading appears several times (table of contents, cross references,
    a body sentence starting with "References"), the candidate followed by the
    most reference-like block wins: numbered/bracketed entries plus year density.
    If no heading is found, returns ``(text, "")`` so the caller can treat the
    whole input as a list.
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

    def score(rest: list[str]) -> tuple[int, int]:
        """Reference density in the first 24k chars + total entry-like markers."""
        head = "\n".join(rest)[:24000]
        numbered = sum(
            1
            for ln in rest[:400]
            if re.match(r"^\s*(?:\[\d{1,3}\]|\d{1,3}[.、)])\s+\S", ln)
        )
        years_head = len(re.findall(r"\b(?:19|20)\d{2}\b", head))
        density = (3 * numbered + min(years_head, 80)) * 10000 // max(len(head), 1)
        total = numbered + min(len(re.findall(r"\b(?:19|20)\d{2}\b", "\n".join(rest))), 80)
        return density, total

    substantial = [h for h in hits if len("\n".join(h[1]).strip()) >= 200]
    candidates = substantial or hits
    best = max(score(h[1]) for h in candidates)
    if best[1] >= 5:
        chosen = max(
            (h for h in candidates if score(h[1]) == best),
            key=lambda h: h[0],
        )
    else:
        chosen = candidates[-1]
    index, rest = chosen
    rest = _trim_reference_appendix(rest)
    return "\n".join(lines[:index]), "\n".join(rest)
