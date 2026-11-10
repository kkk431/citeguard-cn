"""Rule-based numeric consistency check between a claim and its evidence.

This is deliberately shallow: it finds quantities in both texts, checks
whether the claim's value appears in the evidence, and flags obvious
direction conflicts (increase vs decrease). It is a *warning* attached to
the support judgement, not a truth verdict.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|％|倍|万|亿|个百分点|篇|条|例|人|秒|分钟|小时|年|GB|MB|TB)?",
    re.IGNORECASE,
)
_UP = ("提升", "提高", "增加", "增长", "高于", "上升", "多出", "领先")
_DOWN = ("下降", "降低", "减少", "低于", "下降", "落后", "少了")
_UNIT_ALIASES = {"％": "%", "个百分点": "%"}


@dataclass
class Quantity:
    value: float
    unit: str
    raw: str
    start: int
    end: int


def extract(text: str) -> list[Quantity]:
    out: list[Quantity] = []
    for m in _NUM.finditer(text or ""):
        try:
            value = float(m.group("value"))
        except ValueError:
            continue
        unit = _UNIT_ALIASES.get(m.group("unit") or "", (m.group("unit") or "").lower())
        out.append(Quantity(value, unit, m.group(0).strip(), m.start(), m.end()))
    return out


def _norm(value: float, unit: str) -> float:
    if unit == "万":
        return value * 10_000
    if unit == "亿":
        return value * 100_000_000
    return value


def _same(a: Quantity, b: Quantity) -> bool:
    if a.unit and b.unit and a.unit != b.unit:
        return False
    av, bv = _norm(a.value, a.unit), _norm(b.value, b.unit)
    if av == bv:
        return True
    scale = max(abs(av), abs(bv), 1e-9)
    return abs(av - bv) / scale <= 0.01


def _direction(text: str) -> str:
    up = any(w in text for w in _UP)
    down = any(w in text for w in _DOWN)
    if up and not down:
        return "up"
    if down and not up:
        return "down"
    return ""


@dataclass
class NumericCheck:
    checked: int = 0
    matched: int = 0
    missing: list[str] = field(default_factory=list)
    direction_conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.direction_conflicts

    def as_dict(self) -> dict:
        return {
            "checked": self.checked,
            "matched": self.matched,
            "missing": self.missing,
            "direction_conflicts": self.direction_conflicts,
            "notes": self.notes,
            "ok": self.ok,
        }


def check(claim: str, evidence: str) -> NumericCheck:
    result = NumericCheck()
    claim_q = extract(claim)
    evidence_q = extract(evidence)
    result.checked = len(claim_q)
    for q in claim_q:
        hits = [e for e in evidence_q if _same(q, e)]
        if not hits:
            result.missing.append(q.raw)
            continue
        result.matched += 1
        # compare direction words in a short window around each hit
        claim_dir = _direction(claim[max(0, q.start - 12): q.end + 12])
        if not claim_dir:
            continue
        for hit in hits:
            ev_dir = _direction(evidence[max(0, hit.start - 12): hit.end + 12])
            if ev_dir and ev_dir != claim_dir:
                result.direction_conflicts.append(q.raw)
                break
    if result.missing:
        result.notes.append("结论里的数字在证据中找不到同值；可能表述不同，也可能证据不支持")
    if result.direction_conflicts:
        result.notes.append("同一数字前后的方向词与证据相反（升/降）")
    if result.checked == 0:
        result.notes.append("结论中没有可解析的数字")
    return result
