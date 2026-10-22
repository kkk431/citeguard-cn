"""Claim-level citation support: does the cited paper support the sentence?

Pipeline:
1. Extract the sentence around each in-text citation.
2. Reconstruct the cited paper's abstract from OpenAlex / Crossref metadata.
3. Ask a judge model (DeepSeek API, optional) for a 4-way label:
   support / partial / contradict / no_evidence.

The judge is intentionally optional: if ``DEEPSEEK_API_KEY`` is not set the
module returns ``None`` and the report marks support as "not checked". This
keeps the open-source core runnable without any third-party key.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Optional

import requests

from . import config
from .reference_parser import InTextCitation, Reference

SENT_END = "。！？!?；;\n."
CITE_RE = re.compile(r"\[\d+(?:\s*[-–—,，]\s*\d+)*\]")
SUPPORT_LABELS = {"support", "partial", "contradict", "no_evidence", "not_checked"}

# Bump when the prompt changes: judge responses are cached per (prompt, claim,
# evidence), so an old cached verdict must not be reused with a new prompt.
PROMPT_VERSION = 3

PROMPT = """你是学术引文核验员。给定【引用句】和【证据片段】（来自被引论文摘要），判断证据是否支持引用句。

先做一步：从证据片段里找出最能支持或反驳引用句的那一句原文（没有就留空），再据此判定。
只输出 JSON，不要输出其他文字：
{"evidence_quote":"证据中最相关的一句原文","label":"support|partial|contradict|no_evidence","confidence":0.0,"reason":"一句话理由"}

判定标准：
- support：证据明确断言了引用句的核心命题——同样的对象、同样的关系方向，可以被单独引用作为依据；
- partial：证据只支持引用句的一部分（只覆盖其中一个分句、一个中介路径、一个条件或一个结果），或只是间接/较弱支持；
- contradict：证据明确断言了与引用句相反的方向（提高↔降低、增加↔减少、有效↔无效、正相关↔负相关等）；
- no_evidence：证据没有涉及引用句的命题，或信息不足以判断。

容易判错的边界，请特别注意：
1. 引用句是「A 通过 B 影响 C」这类中介/链式结论时，若证据只证明 A→B 或 B→C，判 partial，不要判 support。
2. 引用句包含多个并列结论时，证据只覆盖其中一项，判 partial。
3. 引用句给出具体数值、范围或程度（显著/轻微/最强）时，证据若没有对应量级，最多判 partial。
4. 只有当证据与引用句的核心结论一一对应时，才判 support；拿不准时判 partial 或 no_evidence，不要为了「看起来支持」而判 support。"""


def extract_claim(body: str, position: int, max_len: int = 220) -> str:
    if not body:
        return ""
    start = 0
    for ch in SENT_END:
        i = body.rfind(ch, 0, position)
        if i > start:
            start = i + 1
    end = len(body)
    for ch in SENT_END:
        i = body.find(ch, position)
        if i != -1 and i < end:
            end = i + 1
    sentence = body[start:end].strip()
    sentence = CITE_RE.sub("", sentence).strip()
    return sentence[:max_len]


def build_claims(body: str, intext: list[InTextCitation], refs: list[Reference]) -> dict[int, str]:
    """Map reference index -> the citing sentence."""
    by_index = {r.index: r for r in refs if r.index is not None}
    claims: dict[int, str] = {}
    for c in intext:
        claim = extract_claim(body, c.position)
        if not claim:
            continue
        if c.kind == "numeric":
            for n in c.numbers:
                if n in by_index and n not in claims:
                    claims[n] = claim
        else:
            for r in refs:
                if r.index is None:
                    continue
                if r.year and c.year and r.year != c.year:
                    continue
                if r.authors and c.authors:
                    a, b = r.authors[0], c.authors[0]
                    if not (a in b or b in a or a[:2] == b[:2]):
                        continue
                claims.setdefault(r.index, claim)
    return claims


def _cache_path(claim: str, abstract: str):
    h = hashlib.md5((claim + "||" + abstract).encode("utf-8")).hexdigest()
    d = config.CACHE_DIR / "support" / f"v{PROMPT_VERSION}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.json"


def judge_support(claim: str, abstract: str, title: str = "", doi: str = "") -> Optional[dict]:
    """Return a 4-way support verdict, or None when the judge is unavailable."""
    if not claim:
        return None
    if not abstract:
        return {
            "label": "not_checked",
            "confidence": 0.0,
            "reason": "未获取到被引论文摘要，无法判断",
            "evidence": "",
        }
    if not config.DEEPSEEK_API_KEY:
        return None

    cp = _cache_path(claim, abstract)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Measured best on ClaimSupport-CN: claim + evidence only. Adding the paper
    # title into the message made the judge more lenient (macro-F1 0.876 -> 0.925
    # when removed), so it is intentionally left out here.
    user = f"【引用句】{claim}\n【证据片段】{abstract[:1800]}"
    try:
        resp = requests.post(
            config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "你是严谨的学术引文核验员。"},
                    {"role": "user", "content": PROMPT + "\n\n" + user},
                ],
                "temperature": 0,
                "max_tokens": 400,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return None
        content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        m = re.search(r"\{.*\}", content, re.S)
        parsed = json.loads(m.group(0)) if m else {}
        label = parsed.get("label", "no_evidence")
        if label not in SUPPORT_LABELS:
            label = "no_evidence"
        out = {
            "label": label,
            "confidence": float(parsed.get("confidence", 0.5) or 0.5),
            "reason": parsed.get("reason", ""),
            # v2 asks for evidence_quote; keep reading the v1 key for compatibility.
            "evidence": parsed.get("evidence_quote") or parsed.get("evidence", ""),
        }
        cp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(config.API_SLEEP)
        return out
    except Exception:
        return None


def summarize_support(results: list[Optional[dict]]) -> dict:
    counts = {"support": 0, "partial": 0, "contradict": 0, "no_evidence": 0, "not_checked": 0}
    for r in results:
        if not r:
            counts["not_checked"] += 1
        else:
            label = r.get("label", "no_evidence")
            counts[label] = counts.get(label, 0) + 1
    return counts
