"""页面级引用解析：正文抽取 → 参考文献列表 → ``[n]`` 映射。

这是 t25 spike 的纯函数层，供 ``scripts/spike_live_pages.py`` 调用；不接入
产品路由，也不改动 ``live_check.py``。

设计边界
--------
- 正文抽取用 readability-lxml 0.9（Apache-2.0）。它把页面归一化成一个
  ``summary`` DOM；参考文献列表仍从原始 HTML 解析，因为抽取器可能丢掉列表。
- 参考文献列表支持三类页面结构：arXiv LaTeXML（``li.ltx_bibitem``）、
  Wikipedia（``li[id^=cite_note]``）、通用 ``ref-list``/``references`` 容器。
- 引用标记支持 ASCII 方括号、中文全角方括号（［1］/【2】）和常见列表/范围
  （``[1,3]``、``[2–4]``）。编号 0 不视为引用（参考文献从 1 开始）。
- 只做“定位”：把正文里的 ``[n]`` 指到文献列表的第 n 条，不做真伪判定。

许可证
------
readability-lxml 0.9 为 Apache-2.0；本模块自身与仓库一致为 Apache-2.0。
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

EXTRACTOR_NAME = "readability-lxml"
EXTRACTOR_VERSION = "0.9"
EXTRACTOR_LICENSE = "Apache-2.0"
DEFAULT_TIMEOUT = 8.0
MAX_HTML_BYTES = 2 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 CiteGuard-LiveSpike/0.1"
)

_MARKER_RE = re.compile(
    r"[\[［【]\s*(?P<spec>\d+(?:\s*[-–—,，;；]\s*\d+)*)\s*[\]］】]"
)
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>，。；、]+", re.I)
_TAG_LABEL_RE = re.compile(r"\d+")
_FRAGMENT_NUMBER_RE = re.compile(r"^(?:bib\.bib|B|REF|ref|b)(\d+)$")
_AUTHOR_YEAR_TEXT_RE = re.compile(
    r"^(?P<first>[A-Z][A-Za-z'’\-]+)"
    r"(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z'’\-]+|&\s*[A-Z][A-Za-z'’\-]+))?"
    r"\s*,?\s*\(?(?P<year>(?:19|20)\d{2})(?P<suffix>[a-z]?)\)?$"
)
_PAREN_GROUP_RE = re.compile(r"\(([^()]{3,240})\)")
_NARRATIVE_AY_RE = re.compile(
    r"(?P<first>[A-Z][A-Za-z'’\-]+)"
    r"(?:\s+et\s+al\.?|\s+and\s+[A-Z][A-Za-z'’\-]+)?"
    r"\s*\((?P<year>(?:19|20)\d{2})(?P<suffix>[a-z]?)\)"
)
_FIRST_SURNAME_RE = re.compile(r"^[^\w]*([A-Z][A-Za-z'’\-]+)")
_REFERENCE_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})([a-z]?)\b")
_SENTENCE_ABBREVIATIONS = ("et al.", "e.g.", "i.e.", "vs.", "Fig.", "Figs.", "Eq.", "No.")
_ABBREVIATION_DOT = "\u2024"
_DOI_TRAILING = ".,;:)]}>，。；、"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _host_allowed(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts)


class _AllowedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only when the final host is still allow-listed."""

    def __init__(self, allowed_hosts: tuple[str, ...]):
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(str(newurl or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError(f"重定向到不支持的地址：{newurl!r}")
        if not _host_allowed(parsed.hostname, self.allowed_hosts):
            raise RuntimeError(f"重定向到非白名单站点：{parsed.hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_html(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_HTML_BYTES,
    allowed_hosts: tuple[str, ...] | None = None,
) -> str:
    """Fetch one public HTML page with a browser-like UA and a hard byte cap.

    The spike only reads public pages.  When ``allowed_hosts`` is provided the
    initial URL and every redirect hop are checked against it (the Live preflight
    uses this to avoid turning an allow-listed URL into an SSRF pivot).
    """

    parsed = urllib.parse.urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"只支持 http(s) 页面：{url!r}")
    if allowed_hosts and (not parsed.hostname or not _host_allowed(parsed.hostname, allowed_hosts)):
        raise RuntimeError(f"不在允许的页面白名单内：{parsed.hostname or url}")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        },
    )
    opener = (
        urllib.request.build_opener(_AllowedRedirectHandler(tuple(allowed_hosts)))
        if allowed_hosts
        else urllib.request.build_opener()
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}：{url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 {url}：{exc.reason}") from exc
    except OSError as exc:  # timeout and connection resets
        raise RuntimeError(f"读取 {url} 失败：{exc}") from exc
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------


def parse_html(html: str):
    """Parse HTML into an lxml tree (kept separate for tests)."""

    from lxml import html as lxml_html

    return lxml_html.fromstring(html)


def _normalise(text: Any) -> str:
    return " ".join(str(text or "").split())


def _strip_noise(tree) -> None:
    """Drop elements that never contain article text."""

    for xpath in ("//script", "//style", "//noscript", "//nav", "//footer"):
        for node in tree.xpath(xpath):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)


def _node_text(node) -> str:
    return _normalise("".join(node.itertext()))


def normalise_doi(value: Any) -> str:
    """Lowercase a DOI and strip URL prefixes / trailing punctuation."""

    doi = str(value or "").strip().lower()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi)
    return doi.rstrip(_DOI_TRAILING)


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------


def expand_marker(spec: str) -> list[int]:
    """Expand ``"1,3-5"`` into ``[1, 3, 4, 5]`` (0 is not a reference number)."""

    numbers: list[int] = []
    for part in re.split(r"[,，;；]", str(spec or "")):
        part = part.strip()
        if not part:
            continue
        range_match = re.fullmatch(r"(\d+)\s*[-–—]\s*(\d+)", part)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start <= end and end - start <= 100:
                numbers.extend(range(start, end + 1))
            continue
        if part.isdigit():
            numbers.append(int(part))
    return [number for number in numbers if number > 0]


def find_markers(text: str) -> list[dict[str, Any]]:
    """Find citation markers in plain text (ASCII + full-width brackets).

    Each occurrence is one marker; ``numbers`` may contain several references
    (``[12,13]``).  Markers whose numbers are all invalid (0) are dropped.
    """

    markers: list[dict[str, Any]] = []
    for match in _MARKER_RE.finditer(str(text or "")):
        numbers = expand_marker(match.group("spec"))
        if numbers:
            markers.append({"text": match.group(0), "numbers": numbers, "kind": "numeric"})
    return markers


def _parse_author_year(text: str) -> dict[str, Any] | None:
    """Parse ``"Annamalai et al., 2023a"`` / ``"Ryan and Deci (2020)"``."""

    cleaned = _normalise(text).strip(" .,;:")
    match = _AUTHOR_YEAR_TEXT_RE.match(cleaned)
    if not match:
        return None
    return {
        "authors": match.group("first"),
        "year": int(match.group("year")),
        "suffix": (match.group("suffix") or "").lower(),
        "text": cleaned,
    }


def _reference_author_year(reference: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort first author + publication year of one reference entry."""

    raw = _normalise(reference.get("raw") or reference.get("title") or "")
    if not raw:
        return None
    raw = re.sub(r"^[^A-Za-z]+", "", raw)
    surname = _FIRST_SURNAME_RE.match(raw)
    year = _REFERENCE_YEAR_RE.search(raw)
    if not surname or not year:
        return None
    return {
        "authors": surname.group(1),
        "year": int(year.group(1)),
        "suffix": (year.group(2) or "").lower(),
    }


def _author_year_index(references: dict[int, dict[str, Any]]) -> dict[tuple[str, int, str], list[int]]:
    index: dict[tuple[str, int, str], list[int]] = {}
    for number, reference in references.items():
        parsed = _reference_author_year(reference)
        if parsed is None:
            continue
        key = (parsed["authors"].lower(), parsed["year"], parsed["suffix"])
        index.setdefault(key, []).append(number)
    return index


def _resolve_author_year(
    parsed: dict[str, Any] | None,
    references: dict[int, dict[str, Any]],
    index: dict[tuple[str, int, str], list[int]] | None = None,
) -> list[int]:
    """Map one author-year citation to reference numbers, or ``[]`` if unsure."""

    if not parsed or not references:
        return []
    index = index if index is not None else _author_year_index(references)
    name = str(parsed["authors"]).lower()
    year = int(parsed["year"])
    suffix = str(parsed.get("suffix") or "").lower()
    candidates = list(dict.fromkeys(index.get((name, year, suffix), [])))
    if not candidates and suffix:
        candidates = list(dict.fromkeys(index.get((name, year, ""), [])))
    if not candidates and not suffix:
        suffixed = [
            number
            for (candidate_name, candidate_year, _suffix), numbers in index.items()
            if candidate_name == name and candidate_year == year
            for number in numbers
        ]
        candidates = list(dict.fromkeys(suffixed))
        # More than one suffixed entry (2020a / 2020b) is ambiguous: do not guess.
        if len(candidates) > 1:
            candidates = []
    return [number for number in candidates if number in references]


def find_author_year_markers(
    text: str,
    references: dict[int, dict[str, Any]],
    index: dict[tuple[str, int, str], list[int]] | None = None,
) -> list[dict[str, Any]]:
    """Find author-year citations (parenthetical or narrative) in plain text."""

    source = str(text or "")
    index = index if index is not None else _author_year_index(references)
    markers: list[dict[str, Any]] = []

    def append_marker(parsed: dict[str, Any], surface: str, kind: str = "author-year") -> None:
        numbers = _resolve_author_year(parsed, references, index)
        markers.append(
            {
                "text": surface,
                "numbers": numbers,
                "kind": kind,
                "mapped": bool(numbers) and all(number in references for number in numbers),
                "authors": parsed["authors"],
                "year": parsed["year"],
                "suffix": parsed["suffix"],
            }
        )

    for group in _PAREN_GROUP_RE.finditer(source):
        for part in re.split(r"[;；]", group.group(1)):
            parsed = _parse_author_year(part)
            if parsed is not None:
                append_marker(parsed, f"({part.strip()})")

    for match in _NARRATIVE_AY_RE.finditer(source):
        parsed = {
            "authors": match.group("first"),
            "year": int(match.group("year")),
            "suffix": (match.group("suffix") or "").lower(),
        }
        append_marker(parsed, match.group(0), kind="author-year-narrative")
    return markers


def sentence_split(text: str) -> list[str]:
    """Split article text into sentences, protecting common abbreviations."""

    protected = str(text or "")
    for abbreviation in _SENTENCE_ABBREVIATIONS:
        protected = protected.replace(abbreviation, abbreviation.replace(".", _ABBREVIATION_DOT))
    sentences: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+|(?<=[。！？])", protected):
        part = part.replace(_ABBREVIATION_DOT, ".").strip()
        if part:
            sentences.append(part)
    return sentences


def _fragment_number(fragment: str) -> int | None:
    match = _FRAGMENT_NUMBER_RE.match(str(fragment or "").strip())
    if match is None:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def _anchor_marker(anchor, references: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    """Return a marker for an in-page citation anchor, else ``None``."""

    href = (anchor.get("href") or "").strip()
    if not href.startswith("#") or len(href) < 2:
        return None
    fragment = urllib.parse.unquote(href[1:])
    target = _fragment_number(fragment)
    text = _normalise("".join(anchor.itertext()))
    if not text:
        return None
    bracketed = find_markers(text)
    if bracketed:
        marker = dict(bracketed[0])
        if target is not None and not any(number in references for number in marker["numbers"]):
            marker["numbers"] = [target]
        return marker
    parsed = _parse_author_year(text)
    if parsed is not None:
        numbers = [target] if target is not None and target in references else _resolve_author_year(
            parsed, references
        )
        return {
            "text": text,
            "numbers": numbers,
            "kind": "author-year",
            "mapped": bool(numbers) and all(number in references for number in numbers),
            "authors": parsed["authors"],
            "year": parsed["year"],
            "suffix": parsed["suffix"],
        }
    if target is not None and re.fullmatch(r"\d{1,4}", text):
        return {
            "text": text,
            "numbers": [target],
            "kind": "numeric",
            "mapped": target in references,
        }
    return None


def reference_containers(tree) -> list:
    """Elements that hold a reference list (arXiv / Wikipedia / generic)."""

    groups = [
        tree.xpath('//section[contains(@class,"ltx_bibliography")]'),
        tree.xpath('//ol[contains(@class,"ltx_bibliography")]'),
        tree.xpath(
            '//*[contains(translate(@class,"REFERENCE","reference"),"references") '
            'or starts-with(@id,"references") or starts-with(@id,"reflist") '
            'or contains(@class,"reflist") or contains(@class,"ref-list") '
            'or starts-with(@id,"ref-list")]'
        ),
        tree.xpath('//*[starts-with(@id,"cite_note-")]/ancestor::ol[1]'),
    ]
    seen: set[int] = set()
    containers: list = []
    for group in groups:
        for node in group:
            key = id(node)
            if key in seen:
                continue
            seen.add(key)
            containers.append(node)
    return containers


def _remove_reference_nodes(tree) -> None:
    """Remove reference lists from a copy used for marker counting."""

    for container in reference_containers(tree):
        parent = container.getparent()
        if parent is not None:
            parent.remove(container)


def _body_tree(tree):
    """Return a copy of ``tree`` with noise and the reference list removed."""

    from copy import deepcopy

    body = deepcopy(tree)
    _strip_noise(body)
    _remove_reference_nodes(body)
    return body


def extract_markers_from_tree(tree, references: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Collect citation markers from the page body and mark mapped ones.

    Anchors are resolved to their target reference first, then removed from a
    working copy so the same citation is not counted twice by the plain-text
    scan.  Author-year citations (PMC) have no numeric anchor text, so their
    anchor text and the remaining prose are both parsed for ``(Author, year)``.
    """

    from copy import deepcopy

    work = deepcopy(tree)
    markers: list[dict[str, Any]] = []
    for anchor in work.xpath("//a[@href]"):
        marker = _anchor_marker(anchor, references)
        if marker is None:
            continue
        markers.append(marker)
        parent = anchor.getparent()
        if parent is not None:
            parent.remove(anchor)
    text = _normalise(work.text_content())
    markers.extend(find_markers(text))
    markers.extend(find_author_year_markers(text, references))
    for marker in markers:
        numbers = list(dict.fromkeys(marker.get("numbers") or []))
        marker["numbers"] = numbers
        marker["mapped"] = bool(numbers) and all(number in references for number in numbers)
    return markers


def _annotate_citation_anchors(tree, references: dict[int, dict[str, Any]]):
    """Return a copy where recognised anchors carry canonical citation text.

    Numeric anchors become ``[n]`` so a sentence copy keeps a locatable marker;
    author-year anchors keep their prose (wrapped in parentheses if needed) so
    ``find_author_year_markers`` can resolve them from the sentence alone.
    """

    from copy import deepcopy

    work = deepcopy(tree)
    for anchor in work.xpath("//a[@href]"):
        marker = _anchor_marker(anchor, references)
        if marker is None:
            continue
        text = _normalise("".join(anchor.itertext()))
        if marker.get("kind", "").startswith("author-year"):
            if text.startswith("("):
                replacement = text
            elif text.endswith(")"):
                replacement = text
            else:
                replacement = f"({text})"
        else:
            replacement = "[" + ",".join(str(number) for number in marker["numbers"]) + "]"
        anchor.text = replacement
        for child in list(anchor):
            anchor.remove(child)
    return work


def _reference_sentences(
    text: str,
    references: dict[int, dict[str, Any]],
    index: dict[tuple[str, int, str], list[int]] | None = None,
) -> int:
    """Count sentences that carry at least one citation mapped to a reference."""

    index = index if index is not None else _author_year_index(references)
    count = 0
    for sentence in sentence_split(text):
        markers = find_markers(sentence) + find_author_year_markers(sentence, references, index)
        if any(
            marker["numbers"]
            and all(number in references for number in marker["numbers"])
            for marker in markers
        ):
            count += 1
    return count


def summarise_markers(markers: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the counters used in the spike JSON."""

    total = len(markers)
    mapped = sum(1 for marker in markers if marker.get("mapped"))
    unique_numbers = sorted({number for marker in markers for number in marker["numbers"]})
    unique_mapped = [number for number in unique_numbers if any(
        number in marker["numbers"] and marker.get("mapped") for marker in markers
    )]
    return {
        "markers_total": total,
        "markers_mapped": mapped,
        "mapped_ratio": round(mapped / total, 4) if total else 0.0,
        "unique_markers": len(unique_numbers),
        "unique_mapped": len(unique_mapped),
        "mapped_sources": len(unique_mapped),
        "unmapped_markers": [
            marker["text"] for marker in markers if not marker.get("mapped")
        ][:10],
    }


# ---------------------------------------------------------------------------
# Reference lists
# ---------------------------------------------------------------------------


def _reference_label(item, position: int) -> int:
    """Best-effort 1-based reference number for one list item."""

    tag = item.xpath('.//*[contains(@class,"ltx_tag_bibitem")]')
    if tag:
        match = _TAG_LABEL_RE.search(_node_text(tag[0]))
        if match:
            return int(match.group())
    item_id = (item.get("id") or "").strip()
    id_match = _FRAGMENT_NUMBER_RE.match(item_id)
    if id_match:
        # PMC uses li id="B3" / id="REF3"; the anchor href points at the same id.
        return int(id_match.group(1))
    lowered_id = item_id.lower()
    if lowered_id.startswith("cite_note-"):
        # MediaWiki numbers by list order; trailing ids are not reliable when
        # the same source is cited several times.
        return position
    text = _node_text(item)
    match = re.match(r"^[\[［【]?\s*(\d{1,4})\s*[\]］】.、)]?", text)
    if match:
        number = int(match.group(1))
        if number > 0:
            return number
    return position


def _fallback_reference_title(raw: str) -> str:
    """Best-effort title for PMC / generic lists that have no markup.

    The raw citation is usually ``Authors (Year). Title. Venue …``; strip the
    leading label/authors/year and stop at the venue.  When no year is present
    (short test fixtures) the first sentence is kept unchanged.
    """

    cleaned = re.sub(r"^[\[［【]?\s*\d{1,4}\s*[\]］】.、)]?\s*", "", raw)
    after_year = re.search(r"\((?:19|20)\d{2}[a-z]?\)\.\s+(.+)", cleaned) or re.search(
        r"\b(?:19|20)\d{2}[a-z]?\.\s+(.+)", cleaned
    )
    if after_year:
        cleaned = after_year.group(1)
    title = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0].strip()
    title = re.split(r";\s*pp?\.", title, maxsplit=1)[0].strip()
    title = title.rstrip(" .;；。")
    return (title or cleaned)[:300]


def _reference_title(item, raw: str) -> str:
    """Extract a display title without pulling in the whole citation."""

    classes = (item.get("class") or "").lower()
    if "ltx_bibitem" in classes:
        blocks = item.xpath('.//*[contains(@class,"ltx_bibblock")]')
        texts = [_node_text(block) for block in blocks if _node_text(block)]
        if len(texts) >= 2:
            return texts[1][:300]
        if texts:
            return texts[0][:300]
    quoted = re.search(r"[\"“”]([^\"“”]{3,240})[\"“”]", raw)
    if quoted:
        return quoted.group(1).strip()
    italic = item.xpath(".//i[1]")
    if italic:
        text = _node_text(italic[0])
        if text:
            return text[:300]
    return _fallback_reference_title(raw)


def _reference_url(item) -> str | None:
    for anchor in item.xpath(".//a[@href]"):
        href = (anchor.get("href") or "").strip()
        if href.startswith("http://") or href.startswith("https://"):
            return href
    return None


def parse_references(tree) -> dict[int, dict[str, Any]]:
    """Parse a reference list from an lxml tree, keyed by reference number.

    Supports arXiv LaTeXML, Wikipedia ``cite_note`` items, and generic
    ``references`` / ``ref-list`` containers.  Returns ``{}`` when the page has
    no recognisable list.
    """

    _strip_noise(tree)
    items: list = []
    arxiv_items = tree.xpath('//li[contains(@class,"ltx_bibitem")]')
    if arxiv_items:
        items = arxiv_items
    else:
        wiki_items = tree.xpath('//li[starts-with(@id,"cite_note-")]')
        if wiki_items:
            items = wiki_items
        else:
            for container in reference_containers(tree):
                items.extend(container.xpath(".//li"))
    references: dict[int, dict[str, Any]] = {}
    for position, item in enumerate(items, start=1):
        # Wikipedia backlinks ("1 2 3") are not part of the citation text.
        for backlink in item.xpath('.//*[contains(@class,"mw-cite-backlink")]'):
            parent = backlink.getparent()
            if parent is not None:
                parent.remove(backlink)
        raw = _node_text(item)
        if not raw:
            continue
        index = _reference_label(item, position)
        if index in references:  # duplicate label: keep the first, skip the rest
            continue
        doi_match = _DOI_RE.search(raw)
        doi = normalise_doi(doi_match.group(0)) if doi_match else ""
        references[index] = {
            "index": index,
            "title": _reference_title(item, raw),
            "raw": raw[:600],
            "doi": doi,
            "url": _reference_url(item) or "",
        }
    return dict(sorted(references.items()))


# ---------------------------------------------------------------------------
# Page model
# ---------------------------------------------------------------------------


def _readability_extract(html: str) -> tuple[str, str]:
    """Return ``(title, summary_html)`` from readability-lxml."""

    try:
        from readability import Document
    except ImportError as exc:  # pragma: no cover - environment specific
        raise RuntimeError(
            "缺少 readability-lxml；请运行 `pip install readability-lxml==0.9`"
        ) from exc
    document = Document(html)
    title = _normalise(document.short_title() or "")
    summary = document.summary(html_partial=True)
    return title, summary


def build_page_model(html: str, page_url: str = "", page_title: str = "") -> dict[str, Any]:
    """Build the spike page model: text + references + ``[n]`` mapping.

    ``extractor`` records whether readability-lxml produced usable body text;
    when it collapses to a small fragment, the raw body is used as a fallback
    and the mode is reported instead of silently claiming success.
    """

    raw_tree = parse_html(html)
    references = parse_references(raw_tree)
    raw_reference_count = len(references)

    extractor_mode = EXTRACTOR_NAME
    title = _normalise(page_title)
    try:
        extracted_title, summary_html = _readability_extract(html)
        summary_tree = parse_html(summary_html) if summary_html else _body_tree(raw_tree)
        summary_references = parse_references(summary_tree)
        text = _normalise(summary_tree.text_content())
        if title:
            pass
        elif extracted_title:
            title = extracted_title
        # Two failure signals: the summary collapsed to a fragment, or it lost
        # most of the reference list (LaTeXML pages with several sibling
        # sections).  In both cases fall back to the raw body and say so.
        use_fallback = len(text) < 1500
        if (
            not use_fallback
            and raw_reference_count
            and len(summary_references) < raw_reference_count * 0.8
        ):
            use_fallback = True
        if use_fallback:
            extractor_mode = "body-fallback"
            body_tree = _body_tree(raw_tree)
            text = _normalise(body_tree.text_content())
        else:
            body_tree = summary_tree
    except Exception:
        extractor_mode = "body-fallback"
        body_tree = _body_tree(raw_tree)
        text = _normalise(body_tree.text_content())

    # Remove the bibliography from the body before counting markers, otherwise
    # the labels of the reference list itself inflate the denominator.
    body_tree = _body_tree(body_tree)
    markers = extract_markers_from_tree(body_tree, references)
    counters = summarise_markers(markers)
    annotated_tree = _annotate_citation_anchors(body_tree, references)
    text = _normalise(annotated_tree.text_content())
    author_year_index = _author_year_index(references)
    reference_sentences = _reference_sentences(text, references, author_year_index)

    samples: list[dict[str, Any]] = []
    for marker in markers:
        if len(samples) >= 5:
            break
        if not marker.get("mapped"):
            continue
        sample_references = [
            {
                "index": references[number]["index"],
                "title": references[number]["title"],
                "doi": references[number]["doi"],
                "url": references[number]["url"],
            }
            for number in marker["numbers"]
            if number in references
        ]
        samples.append({"marker": marker["text"], "references": sample_references})

    return {
        "page_url": str(page_url or ""),
        "page_title": title,
        "extractor": {
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "license": EXTRACTOR_LICENSE,
            "mode": extractor_mode,
        },
        "text_chars": len(text),
        "reference_count": len(references),
        **counters,
        "reference_sentences": reference_sentences,
        "samples": samples,
        "references": list(references.values()),
        "body_text": text,
    }


def locate_claim(claim: str, model: dict[str, Any]) -> list[dict[str, Any]]:
    """Locate every citation in a claim on the page's reference list.

    Handles numeric ``[n]`` markers plus author-year citations (PMC).  This is
    the "来源定位" part only: no abstract fetch and no stance judgement.
    """

    references = {entry["index"]: entry for entry in model.get("references", [])}
    index = _author_year_index(references)
    markers = find_markers(claim) + find_author_year_markers(claim, references, index)
    located: list[dict[str, Any]] = []
    for marker in markers:
        mapped = [references[number] for number in marker["numbers"] if number in references]
        item: dict[str, Any] = {
            "marker": marker["text"],
            "numbers": marker["numbers"],
            "kind": marker.get("kind", "numeric"),
            "references": mapped,
            "mapped": bool(marker["numbers"]) and len(mapped) == len(marker["numbers"]),
        }
        if marker.get("kind", "").startswith("author-year"):
            item["authors"] = marker.get("authors", "")
            item["year"] = marker.get("year", 0)
        located.append(item)
    return located


def reference_matches(reference: dict[str, Any], gold_doi: str = "", gold_title: str = "") -> bool:
    """Whether a page reference entry points at the gold source."""

    if gold_doi:
        left = normalise_doi(reference.get("doi"))
        right = normalise_doi(gold_doi)
        if left and right and left == right:
            return True
    title = _title_tokens(gold_title)
    if title:
        haystack = _title_tokens(reference.get("title", "") + " " + reference.get("raw", ""))
        if haystack and len(title & haystack) / len(title) >= 0.8:
            return True
    return False


def _title_tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 2
    }
