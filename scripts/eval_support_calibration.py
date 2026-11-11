"""置信度校准评测：从评测 JSON 的原始 judge 输出重算分桶 / ECE / 弃权曲线。

用法：
    PYTHONPATH=src python scripts/eval_support_calibration.py
输出：
    data/experiments/support_calibration.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.calibration import summarize  # noqa: E402

SOURCES = {
    "claimsupport_100": ROOT / "data" / "claimsupport_cn" / "results.json",
    "claimsupport_300": ROOT / "data" / "experiments" / "release300.json",
}


def _confidence(item: dict) -> float:
    raw = item.get("raw")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return float(parsed.get("confidence", 0.5) or 0.5)
        except Exception:
            pass
    try:
        return float(item.get("confidence", 0.5) or 0.5)
    except Exception:
        return 0.5


def load_pairs(path: Path) -> list[tuple[float, bool]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[float, bool]] = []
    for item in data.get("predictions") or []:
        label, pred = item.get("label"), item.get("pred")
        if not label or not pred:
            continue
        out.append((_confidence(item), pred == label))
    return out


def main() -> int:
    result: dict = {}
    for name, path in SOURCES.items():
        if not path.exists():
            result[name] = {"error": f"missing {path}"}
            continue
        pairs = load_pairs(path)
        summary = summarize(pairs)
        summary["source"] = str(path.relative_to(ROOT))
        result[name] = summary

    out_path = ROOT / "data" / "experiments" / "support_calibration.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
