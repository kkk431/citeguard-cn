"""正文引用句抽取（Phase 1 · 可信内核）。

从论文正文文本里找出“哪一句、引了哪几条参考文献”，为后续的支持度核验
提供上下文。只做抽取，不判断对错；不依赖 PDF 版面，纯文本规则，能在
无 PyMuPDF 的核心安装里工作。

支持：
- 数字键：[12]、[12,15]、[3-5]、[3–5]
- 中文写法：文献[12]、文献 3-5
- 作者-年：(Smith et al., 2020)、(Smith & Jones, 2019)
- 中文作者-年：张三（2020）、张三等（2020）
- 脚注/尾注标记：[^12]、^[12]（带圈数字/上标需字体信息，纯文本不猜）

边界：PDF 文本层把上标压平后，`[12]` 与普通方括号无法区分；这里只做
规则可判的标记，不声称覆盖所有上标引用。
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass

_MAX_REF = 300          # 单条引用最多展开到 300 个编号，防止异常文本爆炸
_MAX_SENTENCE = 320     # 句子截断长度
_SENT_END = "。！？；!?;"
_SENT_END_RE = re.compile(f"[{re.escape(_SENT_END)}]|\\n")

_NUM = re.compile(r"\[(\d{1,3}(?:\s*[-,–—~，]\s*\d{1,3})*)\]")
_CN_WENXIAN = re.compile(
    r"文献\s*\[?\s*(\d{1,3}(?:\s*[-,–—~，]\s*\d{1,3})*)\s*\]?"
)
_EN_AUTHOR_YEAR = re.compile(
    r"\(([A-Z][A-Za-z\-']+(?:\s+et\s+al\.?)?"
    r"(?:\s*(?:&|and)\s+[A-Z][A-Za-z\-']+)?),\s*((?:19|20)\d{2}[a-z]?)\)"
)
_CN_AUTHOR_YEAR = re.compile(
    r"[（(]([\u4e00-\u9fff]{2,4})(?:等)?[，,]\s*((?:19|20)\d{2})[）)]"
)
_CN_AUTHOR_YEAR_BARE = re.compile(
    r"([\u4e00-\u9fff]{2,4})(?:等)?[（(]((?:19|20)\d{2})[）)]"
)
# 脚注/尾注引用：[^12]（Markdown 脚注语义）与 ^[12]（Pandoc 语义）
_FOOTNOTE = re.compile(r"\[\^(\d{1,3})\](?!:)|\^\[(\d{1,3})\]")


@dataclass(frozen=True)
class Citation:
    """正文中的一处引用。"""

    key: str                 # 原始标记，如 "[3-5]"
    style: str               # numeric | chinese | author_year | cn_author_year | footnote
    ref_numbers: list[int]   # 展开后的参考文献编号；作者-年为 []
    sentence: str            # 所在句子（截断到 _MAX_SENTENCE）
    start: int               # 匹配起点（原文本偏移）
    end: int                 # 匹配终点

    def to_dict(self) -> dict:
        return asdict(self)


def _expand_numbers(spec: str) -> list[int]:
    nums: list[int] = []
    for part in re.split(r"\s*[,，]\s*", spec):
        if not part:
            continue
        if re.search(r"[-–—~]", part):
            a, b = re.split(r"\s*[-–—~]\s*", part, maxsplit=1)
            if a.isdigit() and b.isdigit():
                lo, hi = sorted((int(a), int(b)))
                if 0 < hi - lo <= 50:
                    nums.extend(range(lo, hi + 1))
                    continue
        if part.isdigit():
            nums.append(int(part))
    # 去重、保序、限长
    seen: set[int] = set()
    out: list[int] = []
    for n in nums:
        if 1 <= n <= _MAX_REF and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _sentence_at(text: str, start: int, end: int) -> str:
    left = start
    while left > 0 and text[left - 1] not in _SENT_END and text[left - 1] != "\n":
        left -= 1
    right = end
    while right < len(text) and text[right] not in _SENT_END and text[right] != "\n":
        right += 1
    sentence = text[left:right].strip()
    sentence = re.sub(r"\s+", " ", sentence)
    if len(sentence) > _MAX_SENTENCE:
        marker = text[start:end]
        pos = sentence.find(marker)
        if pos < 0:
            sentence = sentence[:_MAX_SENTENCE]
        else:
            lo = max(0, pos - _MAX_SENTENCE // 2)
            sentence = sentence[lo:lo + _MAX_SENTENCE]
    return sentence


def _collect(text: str, pattern: re.Pattern[str], style: str,
             drop: int = 0) -> list[Citation]:
    out: list[Citation] = []
    for m in pattern.finditer(text):
        groups = m.groups()
        spec = next((g for g in groups if g is not None), "") if style == "footnote" else groups[drop]
        key = m.group(0)
        if style == "footnote":
            nums = [int(spec)] if spec and spec.isdigit() else []
            if not nums:
                continue
        elif style in ("numeric", "chinese"):
            nums = _expand_numbers(spec)
            if not nums:
                continue
        else:
            nums = []
            key = f"{groups[0]}, {groups[1]}"
        out.append(Citation(
            key=key,
            style=style,
            ref_numbers=nums,
            sentence=_sentence_at(text, m.start(), m.end()),
            start=m.start(),
            end=m.end(),
        ))
    return out


def extract_citations(text: str) -> list[Citation]:
    """返回正文中所有引用，按出现位置排序并去重。"""
    if not text:
        return []
    items: list[Citation] = []
    # 先抽作者-年，避免 "(Smith et al., 2020)" 被当成别的模式
    items.extend(_collect(text, _EN_AUTHOR_YEAR, "author_year"))
    items.extend(_collect(text, _CN_AUTHOR_YEAR, "cn_author_year"))
    items.extend(_collect(text, _CN_AUTHOR_YEAR_BARE, "cn_author_year"))
    chinese = _collect(text, _CN_WENXIAN, "chinese")
    items.extend(chinese)
    # “文献[12]” 同时命中中文模式与数字模式：去掉被中文模式覆盖的数字命中
    spans = [(c.start, c.end) for c in chinese]
    for c in _collect(text, _NUM, "numeric"):
        if not any(s <= c.start and c.end <= e for s, e in spans):
            items.append(c)
    notes = _collect(text, _FOOTNOTE, "footnote")
    items.extend(notes)
    note_spans = [(c.start, c.end) for c in notes]
    # 去掉脚注标记里的方括号被数字模式重复命中的部分
    items = [c for c in items if not (
        c.style == "numeric" and any(s <= c.start and c.end <= e for s, e in note_spans)
    )]

    seen: set[tuple[int, str]] = set()
    unique: list[Citation] = []
    for c in sorted(items, key=lambda x: x.start):
        k = (c.start, c.key)
        if k in seen:
            continue
        seen.add(k)
        unique.append(c)
    return unique


def summarize(citations: list[Citation]) -> dict:
    """统计：总数、按样式、涉及编号数、覆盖句子数。"""
    refs = sorted({n for c in citations for n in c.ref_numbers})
    return {
        "total": len(citations),
        "by_style": {
            style: sum(1 for c in citations if c.style == style)
            for style in ("numeric", "chinese", "author_year", "cn_author_year", "footnote")
        },
        "ref_numbers": refs,
        "ref_numbers_count": len(refs),
        "sentences": len({c.sentence for c in citations}),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args:
        with open(args[0], encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    citations = extract_citations(text)
    print(json.dumps(
        {"summary": summarize(citations),
         "citations": [c.to_dict() for c in citations]},
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

def _citation_author_year(key: str) -> tuple[str, str] | None:
    """Best-effort (surname, year) from an author-year key like ``Smith et al., 2020``."""
    year = re.search(r"(?:19|20)\d{2}", key or "")
    if not year:
        return None
    head = (key or "").split(year.group(0), 1)[0].strip("( ").strip()
    name = head.split(",", 1)[0]
    name = re.split(r"\s+(?:et\s+al\.?|and|&)", name, maxsplit=1, flags=re.I)[0]
    surname = name.split()[-1] if name.split() else ""
    return (surname.casefold(), year.group(0)) if surname else None


def _author_year_cited(citations: list[Citation], references: list) -> set[int]:
    """Resolve author-year citations to 1-based reference indices when possible."""
    cited: set[int] = set()
    for c in citations:
        parsed = _citation_author_year(c.key)
        if not parsed:
            continue
        surname, year = parsed
        for i, ref in enumerate(references, 1):
            if str(getattr(ref, "year", "") or "") != year:
                continue
            authors = getattr(ref, "authors", []) or []
            joined = " ".join(str(a) for a in authors).casefold()
            names = [str(a).split()[-1].casefold() for a in authors if str(a).strip()]
            if any(n == surname or n.endswith(" " + surname) for n in names) or (
                len(surname) >= 2 and surname in joined
            ):
                cited.add(i)
                break
    return cited


def coverage(citations: list[Citation], references_or_count) -> dict:
    """正文引注覆盖了多少条参考文献。

    ``references_or_count`` 可以是参考文献数量（只算数字编号，兼容旧调用），
    也可以是 Reference 列表；传列表时会把作者年引用也解析到条目。
    """
    refs = references_or_count if isinstance(references_or_count, (list, tuple)) else None
    ref_count = len(refs) if refs is not None else int(references_or_count or 0)
    cited = {n for c in citations for n in c.ref_numbers if 1 <= n <= ref_count}
    if refs is not None:
        cited |= _author_year_cited(citations, refs)
    uncited = [n for n in range(1, ref_count + 1) if n not in cited]
    return {
        "refs": ref_count,
        "cited": len(cited),
        "uncited": uncited,
        "ratio": round(len(cited) / ref_count, 4) if ref_count else 0.0,
    }


_WS_RE = re.compile(r"\s+")


def _norm_text(text: str) -> str:
    return _WS_RE.sub(" ", (text or "")).strip().lower()


def find_page(sentence: str, pages: list[str]) -> int:
    """1-based page containing *sentence* (0 when not found).

    Whitespace and case are normalized; sentences split across a page boundary
    are not recovered — that is a known limit, not an error.
    """
    needle = _norm_text(sentence)
    if len(needle) < 8:
        return 0
    for i, page in enumerate(pages, 1):
        if needle in _norm_text(page):
            return i
    return 0
