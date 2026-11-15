"""Generic sentence-level evidence verification for CiteMap.

This module deliberately contains **no domain-specific vocabulary**.  It
splits a paper into sentences, ranks candidate sentences by lexical overlap
with an atomic claim, and asks the configured judge to classify the best
candidate as ``full`` / ``partial`` / ``none`` while quoting the sentence
verbatim.  The ranking is only a recall helper; the judge makes the claim
decision and invalid quotes are discarded.

The design follows the 105-cell audit finding: a single abstract sentence is
not evidence for a compound claim, so callers must pass atomic claims and a
real full-text (or explicitly mark the source as abstract-only).
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional

from . import support

_JSON_PROMPT = """你是论文证据核验器。给定一条原子断言和若干候选句子，判断候选句子对断言的支持程度。
只输出 JSON，不要解释：
{"verdict":"full|partial|none","evidence":"候选原文逐字句，找不到就空字符串","reason":"一句话理由"}
规则：
- full：某一句直接、完整地断言了该原子断言的语义（数字/方向/对象都对得上）。
- partial：某一句只支持断言的一部分（例如只支持子集、只支持方向、只支持样本），或需要多句合起来才成立。
- none：没有句子支持；仅主题相关、背景介绍、方法描述都不算支持。
- evidence 必须从候选句中原样复制，不能改写；没有 full/partial 时为空。
- 不要因为断言“看起来合理”就给 full；以原文为准。"""

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n{2,}")
_CHUNK_SPLIT = re.compile(r"(?<=[。！？!?；;.])\s+")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")
MAX_SENTENCE_CHARS = 620
_QUERY_CACHE: dict[str, str] = {}


def _chunks(part: str) -> list[str]:
    """Cut one extraction blob into sentence-sized pieces.

    PDFs often glue table cells, references and columns into one huge line
    with no Chinese full stop.  We split at ASCII sentence punctuation as a
    fallback, then hard-cap the result so a table dump cannot become a
    candidate "sentence" (and cannot overflow the judge prompt).
    """
    part = " ".join(part.split()).strip()
    if not part:
        return []
    if len(part) <= MAX_SENTENCE_CHARS:
        return [part]
    pieces = _CHUNK_SPLIT.split(part)
    out: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        while len(piece) > MAX_SENTENCE_CHARS:
            out.append(piece[:MAX_SENTENCE_CHARS].rstrip())
            piece = piece[MAX_SENTENCE_CHARS:].lstrip()
        if piece:
            out.append(piece)
    return out


def split_sentences(text: str, min_len: int = 40, max_sentences: int = 1200) -> list[str]:
    """Split mixed Chinese/English text into sentence-ish units.

    This is a retrieval helper, not a linguistic sentence tokenizer: quotes
    and table fragments are imperfect, but no candidate is allowed to be an
    unbounded PDF blob.
    """
    raw = _SENT_SPLIT.split(text.replace("\r", " "))
    out: list[str] = []
    for part in raw:
        for sentence in _chunks(part):
            sentence = " ".join(sentence.split()).strip()
            if len(sentence) < min_len:
                continue
            # Skip reference/table-like debris with almost no prose.
            cjk = len(_CJK.findall(sentence))
            words = len(_WORD.findall(sentence))
            if cjk < 8 and words < 6:
                continue
            digits = sum(ch.isdigit() for ch in sentence)
            quotes = sum(sentence.count(ch) for ch in '"“”')
            letters = sum(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in sentence)
            if digits > 0.3 * len(sentence) or quotes > 8 or letters < 0.35 * len(sentence):
                continue
            out.append(sentence)
            if len(out) >= max_sentences:
                return out
    return out


def terms(text: str) -> set[str]:
    """Language-agnostic bag of Latin word stems + CJK bigrams."""
    lowered = text.lower()
    words = {w for w in _WORD.findall(lowered) if len(w) >= 3}
    chars = _CJK.findall(text)
    bigrams = {"".join(chars[i : i + 2]) for i in range(len(chars) - 1)}
    return words | bigrams


def _query_for(claim: str, text: str) -> str:
    """Add an English keyword query when a Chinese claim meets English text.

    This is a retrieval aid only.  The judge still sees the original claim and
    the candidate sentence; the translation is never used as evidence.
    """
    if not _CJK.search(claim):
        return claim
    latin = sum(ch.isascii() and ch.isalpha() for ch in text[:5000])
    if latin < 400:
        return claim
    if claim in _QUERY_CACHE:
        return _QUERY_CACHE[claim]
    try:
        extra = support.translate_query(claim)
    except Exception:
        extra = ""
    _QUERY_CACHE[claim] = extra
    return (claim + " " + extra).strip()


def rank_sentences(claim: str, sentences: list[str], limit: int = 6) -> list[str]:
    """Rank sentences by overlap, keeping first occurrence order for ties."""
    want = terms(claim)
    if not want:
        return sentences[:limit]
    scored: list[tuple[float, int, str]] = []
    for idx, sentence in enumerate(sentences):
        got = terms(sentence)
        if not got:
            continue
        overlap = len(want & got) / max(1, len(want))
        # Normalise a little by length so one huge paragraph does not win.
        scored.append((overlap * (1.0 + 0.15 * min(1.0, len(sentence) / 500)), -idx, sentence))
    scored.sort(reverse=True)
    return [s for _, _, s in scored[:limit]]


def _clean_json(raw: Optional[dict]) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    verdict = str(raw.get("verdict", "")).strip().lower()
    if verdict not in {"full", "partial", "none"}:
        return None
    evidence = str(raw.get("evidence", "")).strip()
    reason = str(raw.get("reason", "")).strip()[:300]
    return {"verdict": verdict, "evidence": evidence, "reason": reason}


def verify_claim_in_text(
    claim: str,
    text: str,
    title: str = "",
    top: int = 6,
    timeout: float = 45.0,
) -> dict:
    """Return a verified/partial/none verdict for one atomic claim."""
    query = _query_for(claim, text)
    sentences = rank_sentences(query, split_sentences(text), limit=top)
    if not sentences:
        return {"verdict": "none", "evidence": "", "reason": "全文没有可用句子", "candidates": []}
    numbered = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(sentences))
    user = f"论文标题：{title or '（未提供）'}\n断言：{claim}\n\n候选句：\n{numbered}"
    try:
        raw = support._chat_json(_JSON_PROMPT, user, max_tokens=420, timeout=timeout)
    except TypeError:  # older test doubles / monkeypatches without timeout
        raw = support._chat_json(_JSON_PROMPT, user, max_tokens=420)
    except Exception as exc:  # noqa: BLE001 - judge failures are not evidence
        return {"verdict": "error", "evidence": "", "reason": f"判官失败：{exc}", "candidates": sentences}
    parsed = _clean_json(raw)
    if parsed is None:
        return {"verdict": "error", "evidence": "", "reason": "判官没有返回合法 JSON", "candidates": sentences}
    if parsed["verdict"] == "none":
        parsed["evidence"] = ""
    elif parsed["evidence"]:
        # The quote must be a substring of one of the candidates, otherwise
        # the model hallucinated it; downgrade to partial rather than trust it.
        quote = " ".join(parsed["evidence"].split())
        joined = " ".join(sentences)
        if quote not in joined:
            parsed["verdict"] = "partial" if parsed["verdict"] == "full" else "none"
            parsed["reason"] = (parsed["reason"] + "；引用未在候选句中找到，已降级/丢弃").strip("；")[:300]
            parsed["evidence"] = ""
            if parsed["verdict"] == "none":
                parsed["reason"] = "引用不存在的证据已被丢弃"
    parsed["candidates"] = sentences
    return parsed


def verify_many(claims: Iterable[dict], text: str, title: str = "", top: int = 6) -> list[dict]:
    """Verify a list of atomic claims against one paper, preserving order."""
    claims = list(claims)
    results: list[dict] = []
    for claim in claims:
        verdict = verify_claim_in_text(claim["text"], text, title=title, top=top)
        results.append({**claim, **verdict})
    return results


def summarize(results: Iterable[dict]) -> dict:
    counts = {"full": 0, "partial": 0, "none": 0, "error": 0}
    for result in results:
        verdict = result.get("verdict", "error")
        counts[verdict if verdict in counts else "error"] += 1
    total = sum(counts.values())
    supported = counts["full"]
    return {
        "claims": total,
        "full": counts["full"],
        "partial": counts["partial"],
        "none": counts["none"],
        "error": counts["error"],
        "full_rate": round(supported / total, 4) if total else 0.0,
        "any_support_rate": round((counts["full"] + counts["partial"]) / total, 4) if total else 0.0,
    }


def verify_topic(
    topic: str,
    claims: list[dict],
    paper_texts: dict[str, str],
    titles: dict[str, str] | None = None,
    top: int = 6,
    workers: int = 4,
) -> list[dict]:
    """Run claim × paper verification with a bounded thread pool."""
    titles = titles or {}
    jobs = [(claim, paper_id, text) for claim in claims for paper_id, text in paper_texts.items()]
    out: list[dict] = []

    def run(job):
        claim, paper_id, text = job
        verdict = verify_claim_in_text(claim["text"], text, title=titles.get(paper_id, ""), top=top)
        return {**claim, "paper_id": paper_id, "paper_title": titles.get(paper_id, ""), **verdict}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for result in pool.map(run, jobs):
            out.append(result)
    return out
