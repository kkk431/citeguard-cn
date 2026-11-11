"""置信度校准（Phase 1）：分桶、ECE、弃权曲线。

输入是 (confidence, correct) 序列，不依赖任何模型；产品报告里的置信度
仍由 judge 给出，本模块只回答两个问题：
1. 说 0.9 的时候，实际对多少？（分桶 + ECE）
2. 阈值以下弃权后，覆盖率与准确率怎么变？（弃权曲线）
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Bucket:
    lo: float
    hi: float
    n: int
    avg_confidence: float
    accuracy: float

    def to_dict(self) -> dict:
        return {
            "range": f"[{self.lo:.2f},{self.hi:.2f})",
            "n": self.n,
            "avg_confidence": round(self.avg_confidence, 4),
            "accuracy": round(self.accuracy, 4),
            "gap": round(self.accuracy - self.avg_confidence, 4),
        }


def _clean(pairs) -> list[tuple[float, bool]]:
    out: list[tuple[float, bool]] = []
    for conf, correct in pairs:
        c = max(0.0, min(1.0, float(conf)))
        out.append((c, bool(correct)))
    return out


def bucket_stats(pairs, edges: tuple[float, ...] = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)) -> list[Bucket]:
    """按置信度分桶统计；最后一桶包含 1.0。"""
    rows = _clean(pairs)
    buckets: list[Bucket] = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        last = i == len(edges) - 2
        sel = [(c, ok) for c, ok in rows if lo <= c < hi or (last and c == 1.0)]
        if not sel:
            continue
        n = len(sel)
        avg = sum(c for c, _ in sel) / n
        acc = sum(1 for _, ok in sel if ok) / n
        buckets.append(Bucket(lo=lo, hi=hi, n=n, avg_confidence=avg, accuracy=acc))
    return buckets


def expected_calibration_error(pairs, bins: int = 10) -> float:
    rows = _clean(pairs)
    if not rows:
        return 0.0
    step = 1.0 / bins
    ece = 0.0
    for b in range(bins):
        lo, hi = b * step, (b + 1) * step
        sel = [(c, ok) for c, ok in rows if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if not sel:
            continue
        avg = sum(c for c, _ in sel) / len(sel)
        acc = sum(1 for _, ok in sel if ok) / len(sel)
        ece += (len(sel) / len(rows)) * abs(acc - avg)
    return round(ece, 4)


def abstain_curve(pairs, thresholds: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)) -> list[dict]:
    """阈值 t：置信度 >= t 的才判，其余弃权。"""
    rows = _clean(pairs)
    if not rows:
        return []
    out: list[dict] = []
    for t in thresholds:
        kept = [(c, ok) for c, ok in rows if c >= t]
        out.append({
            "threshold": t,
            "coverage": round(len(kept) / len(rows), 4),
            "accuracy": round(sum(1 for _, ok in kept if ok) / len(kept), 4) if kept else 0.0,
            "kept": len(kept),
            "total": len(rows),
        })
    return out


def summarize(pairs) -> dict:
    rows = _clean(pairs)
    n = len(rows)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "accuracy": round(sum(1 for _, ok in rows if ok) / n, 4),
        "avg_confidence": round(sum(c for c, _ in rows) / n, 4),
        "ece": expected_calibration_error(rows),
        "buckets": [b.to_dict() for b in bucket_stats(rows)],
        "abstain": abstain_curve(rows),
    }
