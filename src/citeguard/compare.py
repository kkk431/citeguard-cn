"""Multi-paper comparison: extract one study profile per paper, then align.

This is the "multiple papers side by side" capability: upload 2–6 papers, take a
short excerpt from each, ask the configured judge (any OpenAI-compatible chat
endpoint, hosted DeepSeek or a local open-source model) to fill six fields, and
return a field x paper matrix. Every extraction is labelled as machine-read and
must be checked against the source; nothing here verifies claims.

The module never imports the web layer: the FastAPI app wraps it in a job.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

import requests

from . import config
from .support import judge_available, judge_endpoint

PROMPT_VERSION = 2
MIN_PAPERS = 2
MAX_PAPERS = 6
EXCERPT_CHARS = 3600
SECTION_CHARS = 900
FIELD_MAX_CHARS = 220
MIN_FIELDS_FILLED = 2

FIELDS: tuple[tuple[str, str], ...] = (
    ("research_question", "研究问题"),
    ("method", "方法 / 设计"),
    ("data", "数据 / 样本"),
    ("findings", "主要结论"),
    ("limitations", "局限"),
    ("contribution", "贡献 / 创新点"),
)
FIELD_KEYS = tuple(key for key, _label in FIELDS)
FIELD_LABELS = dict(FIELDS)

PROMPT = """你是文献综述助手。只根据下面这段论文原文，抽取这篇论文的研究设计信息。
要求：
1. 只输出一个 JSON 对象，不要输出解释或 Markdown 代码块；
2. JSON 必须包含这些键：research_question（研究问题）、method（方法/设计）、
   data（数据/样本）、findings（主要结论）、limitations（局限）、contribution（贡献/创新点）；
3. 只写原文明确说到的内容；原文没有提到就填空字符串 ""，禁止编造；
4. 每个字段不超过 80 个汉字，用短语或一句话；
5. 原文按【摘要】【引言】【方法】【结果】【讨论】【结论】分节给出时，
   优先从「方法」「结果」「结论」抽取；摘要和讨论只作补充。"""


class CompareError(Exception):
    """A user-facing comparison failure (bad input, judge unavailable, ...)."""


def available() -> bool:
    """Whether a judge endpoint is configured for extraction."""
    return judge_available()


def _judge_json(user: str, max_tokens: int = 800) -> Optional[dict]:
    """One chat call; returns the first JSON object or None on HTTP failure."""
    base, model, key = judge_endpoint()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = requests.post(
        base + "/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "你是严谨的文献综述助手。"},
                {"role": "user", "content": PROMPT + "\n\n【原文】\n" + user},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
        },
        timeout=90,
    )
    if resp.status_code != 200:
        return None
    content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


_SECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("摘要", r"摘\s*要|abstract"),
    ("引言", r"引\s*言|前\s*言|introduction|背\s*景"),
    ("方法", r"方\s*法|研究设计|数据与方法|materials?\s+and\s+methods|methods?|methodology"),
    ("结果", r"结\s*果|results?|findings?"),
    ("讨论", r"讨\s*论|discussion"),
    ("结论", r"结\s*论|结\s*语|conclusions?"),
)
_HEADING_RE = re.compile(r"^\s*(?:[一二三四五六七八九十]+[、.．]\s*|\d+(?:\.\d+)*[、.．]?\s*)?")


def _section_snippets(text: str) -> list[tuple[str, str]]:
    """Split raw paper text on common section headings (best effort)."""
    raw = (text or "").replace("\r", "\n")
    lines = raw.split("\n")
    marks: list[tuple[int, int, str]] = []
    offset = 0
    for line in lines:
        clean = line.strip()
        if 0 < len(clean) <= 24:
            core = _HEADING_RE.sub("", clean).strip(" ：:.")
            for label, pattern in _SECTION_PATTERNS:
                if re.fullmatch(pattern, core, re.I):
                    marks.append((offset, offset + len(line), label))
                    break
        offset += len(line) + 1
    if len(marks) < 2:
        return []
    snippets: list[tuple[str, str]] = []
    for idx, (_start, end, label) in enumerate(marks):
        stop = marks[idx + 1][0] if idx + 1 < len(marks) else len(raw)
        body = re.sub(r"\s+", " ", raw[end:stop]).strip()
        if len(body) >= 80:
            snippets.append((label, body[:SECTION_CHARS]))
    return snippets


def _excerpt(text: str) -> str:
    """First few thousand characters, with the reference list cut off."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    if not flat:
        return ""
    headings = list(re.finditer(r"(?:^|\s)(?:参考文献|References)\s*[:：]?", flat, re.I))
    if headings and headings[-1].start() > len(flat) * 0.30:
        flat = flat[: headings[-1].start()].strip()
    return flat[:EXCERPT_CHARS]


def _context(text: str) -> tuple[str, list[str]]:
    """Section-labelled context if headings exist, else a plain excerpt."""
    snippets = _section_snippets(text)
    if snippets:
        body = "\n\n".join(f"【{label}】{body}" for label, body in snippets)
        return body[: EXCERPT_CHARS + 2400], [label for label, _ in snippets]
    return _excerpt(text), []


def _clean(value) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip().strip("。；;，,")
    return text[:FIELD_MAX_CHARS]


def _cache_path(excerpt: str) -> Path:
    model = judge_endpoint()[1]
    digest = hashlib.md5((model + "||" + excerpt).encode("utf-8")).hexdigest()
    folder = config.CACHE_DIR / "compare" / f"v{PROMPT_VERSION}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{digest}.json"


def extract_profile(text: str, *, use_cache: bool = True) -> dict:
    """Extract the six-field profile for one paper; raises CompareError."""
    if not judge_available():
        raise CompareError("未配置判官接口（设置 CITEGUARD_JUDGE_BASE_URL / API_KEY）")
    excerpt, sections = _context(text)
    if len(excerpt) < 200:
        raise CompareError("可用文字太少（不足 200 字），可能是扫描件或解析失败")
    cache = _cache_path(excerpt)
    if use_cache and cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(cached.get("fields"), dict):
                cached["cached"] = True
                return cached
        except Exception:
            pass
    started = time.perf_counter()
    parsed = _judge_json(excerpt)
    if parsed is None:
        raise CompareError("判官接口调用失败（检查服务地址 / API Key / 余额）")
    if not parsed:
        raise CompareError("判官没有返回可解析的 JSON")
    fields = {}
    for key in FIELD_KEYS:
        fields[key] = _clean(parsed.get(key) or parsed.get(FIELD_LABELS[key]) or "")
    if sum(1 for value in fields.values() if value) < MIN_FIELDS_FILLED:
        raise CompareError("判官没有返回足够的字段（研究问题/方法等），请换一篇或重试")
    result = {
        "fields": fields,
        "model": judge_endpoint()[1],
        "excerpt_chars": len(excerpt),
        "sections": sections,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "cached": False,
    }
    try:
        cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return result


def compare_texts(
    papers: Iterable[tuple[str, str]],
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """Build the field x paper matrix; one paper's failure does not kill the rest."""
    items = list(papers)
    if not MIN_PAPERS <= len(items) <= MAX_PAPERS:
        raise CompareError(f"一次需要 {MIN_PAPERS}–{MAX_PAPERS} 篇文献")
    result: dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": judge_endpoint()[1],
        "fields": [{"key": key, "label": label} for key, label in FIELDS],
        "papers": [],
        "warnings": [],
    }
    for index, (name, text) in enumerate(items, 1):
        if on_progress:
            on_progress(index, len(items), name)
        entry = {
            "name": name,
            "chars": len((text or "").strip()),
            "fields": {key: "" for key in FIELD_KEYS},
            "error": "",
            "cached": False,
        }
        try:
            profile = extract_profile(text)
            entry["fields"] = profile["fields"]
            entry["cached"] = bool(profile.get("cached"))
            entry["excerpt_chars"] = profile.get("excerpt_chars", 0)
            entry["sections"] = profile.get("sections", [])
            entry["latency_ms"] = profile.get("latency_ms", 0)
        except CompareError as exc:
            entry["error"] = str(exc)
        result["papers"].append(entry)
    if len(result["papers"]) and all(paper["error"] for paper in result["papers"]):
        raise CompareError("所有文献都没能抽取成功，请检查文件是否可解析、判官是否可用")
    return result


def _escape_md(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def render_markdown(result: dict) -> str:
    """Field x paper markdown table plus provenance notes."""
    papers = result.get("papers") or []
    heading = ["字段"] + [paper.get("name", f"文献{i+1}") for i, paper in enumerate(papers)]
    lines = ["# 多篇文献对比", ""]
    lines.append("| " + " | ".join(_escape_md(cell) for cell in heading) + " |")
    lines.append("|" + "|".join(["---"] * len(heading)) + "|")
    for field in result.get("fields") or []:
        row = [field["label"]]
        for paper in papers:
            if paper.get("error"):
                row.append("（抽取失败）")
            else:
                row.append(_escape_md((paper.get("fields") or {}).get(field["key"], "")) or "—")
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        f"- 生成时间：{result.get('generated_at', '')}",
        f"- 判官模型：{result.get('model', '')}",
        "- 字段由机器从每篇论文的摘录中抽取，可能不完整或出错，引用前必须回到原文核对。",
    ]
    for paper in papers:
        if paper.get("error"):
            lines.append(f"- 抽取失败：{paper.get('name')} — {paper['error']}")
    return "\n".join(lines) + "\n"


def render_csv(result: dict) -> str:
    """CSV version (utf-8-sig is added by the web layer)."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    papers = result.get("papers") or []
    writer.writerow(["字段"] + [paper.get("name", f"文献{i+1}") for i, paper in enumerate(papers)])
    for field in result.get("fields") or []:
        row = [field["label"]]
        for paper in papers:
            if paper.get("error"):
                row.append("（抽取失败）")
            else:
                row.append((paper.get("fields") or {}).get(field["key"], ""))
        writer.writerow(row)
    return buffer.getvalue()
