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
from pathlib import Path
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


# General-purpose audit prompt (v2). The v1 prompt above is tuned for empirical
# claims and asks the judge to enumerate study design elements (population,
# causal chain, effect size ...). On non-empirical claims (policy statements,
# definitions, announcements) it rejects evidence that literally contains the
# claim, which over-downgrades *support* to *partial*. v2 audits only what the
# claim itself asserts and explicitly accepts verbatim evidence.
AUDIT_PROMPT_V2 = """你是严谨的「引文覆盖审计员」。给定【引用句】和【证据片段】（来自被引论文的摘要或正文），判断证据是否足以支撑引用句的核心断言。

先找出引用句的核心断言（一句话：它到底让读者相信什么），再检查证据片段是否给出了这个断言。
只审计引用句自己说了什么，不要求证据补齐引用句未提及的研究设计、样本量、统计方法等。

输出 JSON（不要输出其他文字）：
{"core":"引用句的核心断言","verdict":"yes|partial|no","reason":"一句话说明"}
- yes：证据明确包含引用句原句，或给出同义表述/直接数据；
- partial：证据只覆盖引用句的一部分（例如只提到研究对象/背景/目的，没有结论或结果）；
- no：证据主题相关但没有对应该断言，或断言相反。

判定时注意：
1. 引用句出现在证据中（允许标点差异）时判 yes；
2. 引用句是研究目的/背景（「本文研究X的疗效」），而证据也以同样措辞陈述该目的时判 yes；
3. 证据只说「可能/相关/有助于」而引用句是确定因果，最多 partial；
4. 拿不准时判 partial，不要判 no。"""

AUDIT_PROMPTS = {"v1": AUDIT_PROMPT, "v2": AUDIT_PROMPT_V2}

# Hybrid audit (v3): keeps v2's general applicability and verbatim-accept rule,
# but restores an explicit element checklist so "background-only" evidence is
# downgraded. Small local models tend to copy the stage-1 "support" verdict
# when the audit prompt does not force them to enumerate what is missing.
AUDIT_PROMPT_V3 = """你是严谨的学术引文核验员。给定【引用句】和【证据片段】，判断证据是否支撑引用句的【全部核心断言】。

步骤：
1. 把引用句拆成 1–3 个核心要素（研究对象/主题、关系或因果、结果/数值/方向）；
2. 逐条检查证据是否覆盖每个要素；
3. 给出判定。

输出 JSON（不要输出其他文字）：
{"elements":["要素1","要素2"],"covered":["已覆盖的要素"],"verdict":"yes|partial|no","reason":"一句话说明"}

判定规则：
- yes：证据包含引用句原句或等义表述，且覆盖全部要素；
- partial：证据只覆盖部分要素；或引用句给出具体结果/效应/因果方向，而证据只提供研究背景、目的、方法或相关性；
- no：证据主题不同，或断言与证据相反；
- 拿不准时判 partial，不要判 no。

示例：
【引用句】某干预能显著改善患者的睡眠质量。
【证据片段】某干预可能对患者睡眠有影响，仍需进一步研究。
→ partial（只有相关性/可能性，没有「显著改善」这一结果要素）

【引用句】本文调查了乡村教师的流动意愿。
【证据片段】本文调查乡村教师流动意愿及其影响因素。
→ yes（目的句被等义覆盖）

【引用句】A 导致 B 上升。
【证据片段】A 与 B 无显著相关。
→ no（断言相反）"""

AUDIT_PROMPTS["v3"] = AUDIT_PROMPT_V3


# Optional custom prompt file (``CITEGUARD_SUPPORT_PROMPT_FILE``): small local
# models follow the shorter ``scripts/support_prompt_simple.txt`` better than the
# built-in long prompt. A custom prompt gets its own cache namespace so its
# verdicts never mix with the built-in prompt's cache.
# Both endpoints default to the measured few-shot v10 prompt: on Qwen3-14B dev
# it scored 1.000 (v8 0.979), test 0.9574; hosted DeepSeek all-100 0.9597.
# Set the env var explicitly to override, or point at
# ``scripts/support_prompt_simple.txt`` for very small models.
if config.SUPPORT_PROMPT_FILE:
    _prompt_path = Path(config.SUPPORT_PROMPT_FILE)
    if not _prompt_path.exists():
        raise RuntimeError(
            f"CITEGUARD_SUPPORT_PROMPT_FILE points to a missing file: {_prompt_path}"
        )
    PROMPT = _prompt_path.read_text(encoding="utf-8")
    PROMPT_VERSION = f"{PROMPT_VERSION}-{hashlib.sha256(PROMPT.encode('utf-8')).hexdigest()[:8]}"
else:
    _prompt_dir = Path(__file__).resolve().parents[2] / "scripts"
    _v10_path = _prompt_dir / "support_prompt_v10.txt"
    if _v10_path.exists():
        PROMPT = _v10_path.read_text(encoding="utf-8")
        PROMPT_VERSION = f"10-{hashlib.sha256(PROMPT.encode('utf-8')).hexdigest()[:8]}"


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
    # The cached value is the *final* verdict (after the coverage audit), so the
    # audit style must be part of the key; otherwise switching v1<->v2 keeps
    # serving verdicts produced by the old audit prompt.
    audit_tag = _audit_style() if config.SUPPORT_AUDIT else "off"
    h = hashlib.md5((model + "||" + audit_tag + "||" + claim + "||" + abstract).encode("utf-8")).hexdigest()
    d = config.CACHE_DIR / "support" / f"v{PROMPT_VERSION}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.json"


def _audit_style() -> str:
    style = (getattr(config, "SUPPORT_AUDIT_STYLE", "auto") or "auto").strip().lower()
    if style == "auto":
        # 自托管（OpenAI 兼容本地端点）模型用通用覆盖审计 v2：实测比 v1
        # 更少把“部分支持”误升为支持；托管 API 继续用 v1 保持已发布口径。
        # 注意：本地端点既可能通过 CITEGUARD_JUDGE_BASE_URL 配置，也可能
        # 直接覆盖 DEEPSEEK_BASE_URL（部署文档里的写法），因此要看实际生效的
        # endpoint，而不是某一个环境变量。
        return "v2" if not _is_hosted_endpoint(judge_endpoint()[0]) else "v1"
    return style if style in AUDIT_PROMPTS else "v1"


def _is_hosted_endpoint(base: str) -> bool:
    """DeepSeek 托管端点；其余（localhost/内网/Ollama/vLLM）都按自托管处理。"""
    return "deepseek.com" in (base or "").lower()


def _audit_cache_path(claim: str, abstract: str):
    model = judge_endpoint()[1]
    style = _audit_style()
    h = hashlib.md5(("AUDIT::" + style + "::" + model + "||" + claim + "||" + abstract).encode("utf-8")).hexdigest()
    d = config.CACHE_DIR / "support" / f"v{PROMPT_VERSION}"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"audit-{style}-{h}.json"


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
    """Stage 2: is every part of the claim covered by the evidence?

    The prompt is selected by ``config.SUPPORT_AUDIT_STYLE`` (v1/v2/v3); every
    style is normalized to the same ``fully_covered`` boolean so callers do not
    depend on the shape of the raw reply.
    """
    cp = _audit_cache_path(claim, abstract)
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    style = _audit_style()
    prompt = AUDIT_PROMPTS[style]
    audit = _chat_json(prompt, f"【引用句】{claim}\n【证据片段】{abstract[:1800]}", max_tokens=500)
    if audit is None:
        return None
    verdict = audit.get("verdict")
    if isinstance(verdict, str) and verdict.strip().lower() in {"yes", "partial", "no"}:
        audit["fully_covered"] = verdict.strip().lower() == "yes"
        if "missing" not in audit:
            elements = [str(x) for x in (audit.get("elements") or []) if x]
            covered = [str(x) for x in (audit.get("covered") or []) if x]
            audit["missing"] = [e for e in elements if e not in covered][:5]
    audit["style"] = style
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
                    "style": audit.get("style") or _audit_style(),
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
