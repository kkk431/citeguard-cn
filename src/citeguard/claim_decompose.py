"""多结论拆解（Phase 1 · 可信内核）。

一句话里常常同时包含多个可独立核验的结论，例如：

    “A 组准确率 92%，比 B 组高 3 个百分点，但推理慢 2 倍。”

整体判一个 support 会掩盖局部错误。这里只做**规则拆解**（不调用模型）：
按分句/转折词切开，标出每个子结论的类型（数字/方向/比较/因果/陈述）、
数字与方向，供报告展示和后续逐条判定使用。

边界：这是启发式切分，不保证语义完整；报告里必须说明“整体标签仍是对
整句的判断”，不能把子结论当独立人审结论。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

_SPLIT = re.compile(r"[；;。]\s*|(?<=[，,])\s*(?:但|然而|不过|同时|并且|而且|而)\s*")
_NUM = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|％|倍|万|亿|个百分点|个|篇|条|秒|分钟|小时|GB|MB)?"
)
_CMP = re.compile(r"比|高于|低于|超过|落后|多于|少于|高于|提升|提高|增加|增长|上升|下降|降低|减少|下滑|"
                  r"\b(?:higher|lower|more|less|increase|decrease|better|worse|than)\b", re.I)
_CAUSAL = re.compile(r"因为|由于|导致|因此|所以|从而|使得|because|therefore|thus|lead(?:s|ing)? to", re.I)
_UP = re.compile(r"提升|提高|增加|增长|上升|高于|超过|better|higher|increase", re.I)
_DOWN = re.compile(r"下降|降低|减少|下滑|低于|落后|worse|lower|decrease", re.I)


@dataclass
class SubClaim:
    text: str
    kind: str                       # numeric | comparison | causal | statement
    numbers: list[dict] = field(default_factory=list)
    directions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _directions(text: str) -> list[str]:
    out: list[str] = []
    if _UP.search(text):
        out.append("up")
    if _DOWN.search(text):
        out.append("down")
    return out


def _numbers(text: str) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for m in _NUM.finditer(text):
        raw = m.group(0).strip()
        unit = (m.group("unit") or "").strip()
        key = (m.group("value"), unit)
        if key in seen:
            continue
        seen.add(key)
        out.append({"value": m.group("value"), "unit": unit, "raw": raw})
    return out


def decompose(claim: str) -> list[SubClaim]:
    """把一句话拆成子结论；单句无分句时返回一条。"""
    text = (claim or "").strip()
    if not text:
        return []
    parts = [p.strip(" ，,") for p in _SPLIT.split(text) if p and p.strip(" ，,")]
    if not parts:
        parts = [text]
    out: list[SubClaim] = []
    for part in parts:
        nums = _numbers(part)
        if nums and _CMP.search(part) and len(nums) >= 2:
            kind = "comparison"
        elif nums:
            kind = "numeric"
        elif _CAUSAL.search(part):
            kind = "causal"
        elif _CMP.search(part):
            kind = "comparison"
        else:
            kind = "statement"
        out.append(SubClaim(
            text=part,
            kind=kind,
            numbers=nums,
            directions=_directions(part),
        ))
    return out


def analyze_claim(claim: str) -> dict:
    """报告/API 用的结构：子结论 + 一句诚实的边界说明。"""
    subs = decompose(claim)
    kinds = [s.kind for s in subs]
    return {
        "parts": [s.to_dict() for s in subs],
        "count": len(subs),
        "has_numeric": "numeric" in kinds or "comparison" in kinds,
        "has_comparison": "comparison" in kinds,
        "note": (
            "整句仍只给一个支持度标签；这里拆出的子结论用于提示逐条核对，"
            "不是独立的人工判定结论。"
        ) if len(subs) > 1 else "",
    }
