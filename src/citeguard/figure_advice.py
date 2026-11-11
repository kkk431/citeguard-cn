"""Turn a figure-check verdict into a concrete caption fix (rule-based, no model)."""

from __future__ import annotations

_ADVICE = {
    "contradicted": (
        "high",
        "图注/正文与图表不一致：核对数字或方向，按图中读数改写；"
        "若图中没有这项，删掉该结论，或标注“图中未给出”。",
    ),
    "insufficient": (
        "medium",
        "图表信息不足：补上单位、比较对象或具体数值；"
        "读不出来的结论不要写进图注。",
    ),
    "error": ("low", "未能判读该图：请人工核对图注与正文是否一致。"),
}


def advise(verdict: str) -> dict | None:
    """Return {level, text} for non-supported verdicts, else None."""
    hit = _ADVICE.get((verdict or "").strip().lower())
    if not hit:
        return None
    level, text = hit
    return {"level": level, "text": text}


def annotate_items(items: list[dict]) -> list[dict]:
    """Attach ``advice`` to each item when its verdict needs action."""
    for item in items:
        verdict = item.get("verdict") or ("supported" if item.get("ok") else "error")
        item["advice"] = advise(verdict)
    return items
