"""Assertion-level evidence alignment.

This module decomposes a compound claim into atomic sub-claims and aligns each
sub-claim against candidate sentences from a paper.  It deliberately separates
the *retrieval* step (lexical, deterministic) from the *judgement* step (an
injected judge).  Without a judge it returns ``insufficient`` rather than
guessing that a lexical overlap means support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from .claim_decompose import SubClaim, decompose

Judge = Callable[[str, str], dict | None]

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}|[\u4e00-\u9fff]+")
_SENT_RE = re.compile(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_NEGATIONS = ("不", "未", "没有", "并非", "不能", "无法", "not ", "no ", "never", "without")


@dataclass
class SubClaimAlignment:
    subclaim: str
    label: str = "insufficient"
    confidence: float = 0.0
    evidence: str = ""
    sentence_index: int = -1
    candidates: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class AlignmentResult:
    claim: str
    label: str
    subclaims: list[SubClaimAlignment]
    coverage: float = 0.0
    checked: int = 0
    boundary: str = ""


def _terms(text: str) -> set[str]:
    out: set[str] = set()
    for token in _TOKEN_RE.findall(text or ""):
        if re.search(r"[\u4e00-\u9fff]", token):
            if len(token) == 1:
                out.add(token)
            else:
                out.update(token[i : i + 2] for i in range(len(token) - 1))
        else:
            out.add(token.lower())
    return out


def split_sentences(text: str) -> list[str]:
    """Split Chinese/English body text into sentence-ish units."""
    parts = [p.strip() for p in _SENT_RE.split(text or "") if p and p.strip()]
    return parts


def sentence_score(claim: str, sentence: str) -> float:
    """Cheap lexical retrieval score; not a support score."""
    a, b = _terms(claim), _terms(sentence)
    if not a or not b:
        return 0.0
    overlap = len(a & b) / len(a)
    # Long sentences are often section headers / reference blobs; penalise.
    length_penalty = min(1.0, 240.0 / max(80.0, float(len(sentence))))
    return overlap * (0.6 + 0.4 * length_penalty)


def rank_sentences(claim: str, text: str, *, top_k: int = 4) -> list[tuple[float, int, str]]:
    scored = [(sentence_score(claim, s), i, s) for i, s in enumerate(split_sentences(text))]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[: max(1, top_k)]


def _numeric_conflict(claim: str, evidence: str) -> bool:
    from .numeric_check import check

    try:
        result = check(claim, evidence)
    except Exception:
        return False
    return bool(result.direction_conflicts)


def _negation_mismatch(claim: str, evidence: str) -> bool:
    a = any(n in claim.lower() for n in _NEGATIONS)
    b = any(n in evidence.lower() for n in _NEGATIONS)
    return a != b


def align_subclaim(
    subclaim: str,
    evidence_text: str,
    *,
    judge: Judge | None = None,
    top_k: int = 4,
) -> SubClaimAlignment:
    """Align one sub-claim to the best evidence sentence.

    With ``judge`` the judge decides label/quote; without it we only retrieve
    candidates and return ``insufficient``.  Lexical overlap is never treated
    as support.
    """
    ranked = rank_sentences(subclaim, evidence_text, top_k=top_k)
    candidates = [s for _, _, s in ranked]
    if not candidates and (evidence_text or "").strip() and (_CJK_RE.search(subclaim) is None) != (_CJK_RE.search(evidence_text) is None):
        # A cross-language evidence snippet has no lexical overlap with the
        # claim.  The snippet itself is still the candidate; retrieval must not
        # turn a valid judgeable pair into "no candidates".
        candidates = [(evidence_text or "").strip()]
        ranked = [(0.0, 0, candidates[0])]
    if not candidates:
        return SubClaimAlignment(subclaim=subclaim, candidates=[], reason="没有召回到候选句")

    best = candidates[0]
    if judge is None:
        return SubClaimAlignment(
            subclaim=subclaim,
            label="insufficient",
            confidence=0.0,
            evidence="",
            sentence_index=ranked[0][1],
            candidates=candidates,
            reason="仅有候选句；未调用 judge，不能把字面重合当作支持",
        )

    verdict = judge(subclaim, best) or {}
    label = str(verdict.get("label") or "insufficient")
    if label not in {"support", "partial", "contradict", "no_evidence", "insufficient"}:
        label = "insufficient"
    confidence = float(verdict.get("confidence") or 0.0)
    quote = str(verdict.get("quote") or "").strip()
    # If the judge returns a quote, it must be grounded in the sentence we sent.
    if quote and quote not in best and best not in quote:
        label, confidence, quote = "insufficient", 0.0, ""
    reason = str(verdict.get("reason") or "")
    if _numeric_conflict(subclaim, best) and label == "support":
        label, reason = "contradict", (reason + "；数字/方向冲突").strip("；")
    elif _negation_mismatch(subclaim, best) and label == "support":
        label, reason = "contradict", (reason + "；否定方向相反").strip("；")
    return SubClaimAlignment(
        subclaim=subclaim,
        label=label,
        confidence=confidence,
        evidence=quote or best,
        sentence_index=ranked[0][1],
        candidates=candidates,
        reason=reason,
    )


def _aggregate(items: Sequence[SubClaimAlignment]) -> str:
    labels = [x.label for x in items]
    if not labels:
        return "insufficient"
    if "contradict" in labels:
        return "contradict"
    checked = [x for x in items if x.label in {"support", "partial", "contradict"}]
    if not checked:
        return "insufficient"
    if len(checked) == len(items) and all(x.label == "support" for x in checked):
        return "support"
    if any(x.label in {"support", "partial"} for x in checked):
        return "partial"
    return "insufficient"


def align_claim(
    claim: str,
    evidence_text: str,
    *,
    judge: Judge | None = None,
    top_k: int = 4,
    subclaims: Iterable[SubClaim] | None = None,
) -> AlignmentResult:
    parts = list(subclaims) if subclaims is not None else decompose(claim)
    if not parts:
        parts = [SubClaim(text=claim, kind="statement")]
    aligned = [align_subclaim(p.text, evidence_text, judge=judge, top_k=top_k) for p in parts]
    checked = [x for x in aligned if x.label != "insufficient"]
    coverage = len(checked) / len(aligned) if aligned else 0.0
    return AlignmentResult(
        claim=claim,
        label=_aggregate(aligned),
        subclaims=aligned,
        coverage=coverage,
        checked=len(checked),
        boundary="subclaim labels are judge-dependent; lexical-only mode returns insufficient by design",
    )
