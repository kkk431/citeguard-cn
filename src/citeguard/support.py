"""Claim-level citation support: does the cited paper support the sentence?

Pipeline:
1. Extract the sentence around each in-text citation.
2. Reconstruct the cited paper's abstract from OpenAlex / Crossref metadata.
3. Ask a judge model for a 4-way label:
   support / partial / contradict / no_evidence.

The judge is intentionally optional and pluggable: ``DEEPSEEK_API_KEY`` (or any
OpenAI-compatible local server via ``CITEGUARD_JUDGE_BASE_URL``) enables it; with
no endpoint configured the module returns ``None`` and the report marks support
as "not checked", so the open-source core runs without any third-party key.
"""
from __future__ import annotations

import hashlib
import json
import os
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
# v4: two-stage judge (evidence-first verdict + coverage audit that can
# downgrade support -> partial).
PROMPT_VERSION = 4

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


# Stage 2: coverage audit. Only runs for verdicts classified as ``support`` and
# asks a narrower question: are *all* parts of the claim (objects, conditions,
# causal chain, magnitude) explicitly covered by the evidence? This targets the
# dominant confusion-matrix error (partial -> support): macro-F1 0.9005 ->
# 0.9328 on the product path (0.9439 in the standalone experiment harness).
AUDIT_PROMPT = """你是学术引文的「覆盖审计员」。给定【引用句】和【证据片段】（来自被引论文摘要），只判断证据是否完整覆盖引用句的每一个断言要素。

请先把引用句拆成断言要素：研究对象、条件/人群、关系或因果（含方向）、中介路径、结果、量级/程度词（显著、最强、轻微、首次、最多等）。
再逐项检查证据片段是否明确写到了每个要素，并输出 JSON（不要输出其他文字）：
{"factors":["要素1","要素2"],"covered":[true,false],"fully_covered":true,"missing":["未被证据覆盖的要素"]}

判定规则：
1. 引用句是「A 通过 B 影响 C」这类链式/中介结论时，缺少任何一环都算 not fully covered；
2. 引用句给出具体数值、范围、程度或显著性词，而证据没有对应量级/程度表述，算 not fully covered；
3. 引用句是肯定的因果断言，而证据只说「相关/可能/有助于/提示」，算 not fully covered；
4. 引用句包含多个并列结论时，证据只覆盖其中一项，算 not fully covered；
5. 只有证据明确覆盖全部要素时才输出 fully_covered=true；拿不准时输出 false。"""


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


def judge_endpoint() -> tuple[str, str, str]:
    """Where the support judge runs: any OpenAI-compatible `/chat/completions`.

    Defaults to DeepSeek. Point ``CITEGUARD_JUDGE_BASE_URL`` / ``_MODEL`` at a
    local server (Ollama, vLLM, LM Studio, llama.cpp-server) to judge with an
    open-source model and no third-party API; ``CITEGUARD_JUDGE_API_KEY`` is
    optional in that case.
    """
    base = os.environ.get("CITEGUARD_JUDGE_BASE_URL") or config.DEEPSEEK_BASE_URL
    model = os.environ.get("CITEGUARD_JUDGE_MODEL") or config.DEEPSEEK_MODEL
    key = os.environ.get("CITEGUARD_JUDGE_API_KEY") or config.DEEPSEEK_API_KEY
    return base.rstrip("/"), model, key


def judge_available() -> bool:
    """True when a judge endpoint is configured (a local server needs no key)."""
    _base, _model, key = judge_endpoint()
    return bool(key or os.environ.get("CITEGUARD_JUDGE_BASE_URL"))


def _cache_path(claim: str, abstract: str):
    model = judge_endpoint()[1]
    h = hashlib.md5((model + "||" + claim + "||" + abstract).encode("utf-8")).hexdigest()
    d = config.CACHE_DIR / "support" / f"v{PROMPT_VERSION}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.json"


def _audit_cache_path(claim: str, abstract: str):
    model = judge_endpoint()[1]
    h = hashlib.md5(("AUDIT::" + model + "||" + claim + "||" + abstract).encode("utf-8")).hexdigest()
    d = config.CACHE_DIR / "support" / f"v{PROMPT_VERSION}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"audit-{h}.json"


def _chat_json(prompt: str, user: str, max_tokens: int = 400) -> Optional[dict]:
    """One judge call that returns the first JSON object in the reply."""
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
                {"role": "system", "content": "你是严谨的学术引文核验员。"},
                {"role": "user", "content": prompt + "\n\n" + user},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        return None
    content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _audit_support(claim: str, abstract: str) -> Optional[dict]:
    """Stage 2: is every part of the claim covered by the evidence?"""
    cp = _audit_cache_path(claim, abstract)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    audit = _chat_json(AUDIT_PROMPT, f"【引用句】{claim}\n【证据片段】{abstract[:1800]}", max_tokens=500)
    if audit is None:
        return None
    cp.write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
    return audit


def judge_support(claim: str, abstract: str, title: str = "", doi: str = "") -> Optional[dict]:
    """Return a 4-way support verdict, or None when the judge is unavailable.

    Stage 1 asks for the verdict with an evidence quote. Stage 2 audits every
    "support" verdict: if the evidence misses part of the claim, it is
    downgraded to "partial" (this fixed the dominant error on ClaimSupport-CN:
    partial cases being judged as support).
    """
    if not claim:
        return None
    if not abstract:
        return {
            "label": "not_checked",
            "confidence": 0.0,
            "reason": "未获取到被引论文摘要，无法判断",
            "evidence": "",
        }
    if not judge_available():
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
        parsed = _chat_json(PROMPT, user)
        if parsed is None:
            return None
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
        if label == "support" and config.SUPPORT_AUDIT:
            audit = _audit_support(claim, abstract)
            if audit:
                out["audit"] = {
                    "fully_covered": audit.get("fully_covered"),
                    "missing": [str(x) for x in (audit.get("missing") or []) if x][:5],
                }
                if audit.get("fully_covered") is False:
                    out["label"] = "partial"
                    missing = out["audit"]["missing"]
                    out["reason"] = (out["reason"] or "") + "；覆盖审计：证据未完整覆盖引用句" + (
                        "（缺：" + "；".join(missing[:3]) + "）" if missing else ""
                    )
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
