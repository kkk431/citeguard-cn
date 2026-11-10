"""One-command evidence replay for CiteGuard-CN.

What it does by default (offline, no LLM calls):
  1. runs the test suite;
  2. runs the artifact checker;
  3. re-prints the headline numbers from the committed experiment JSON files.

What it does NOT do: re-run live model evaluations. Those need an API key and
network; the exact commands are printed at the end so a reviewer can rerun them.

Usage:
    python scripts/reproduce_all.py            # offline replay (~1 min)
    python scripts/reproduce_all.py --no-tests # skip pytest
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "experiments"


def run(cmd: list[str]) -> int:
    print("$ " + " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def load(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pick(d: dict, *keys: str, default="—"):
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
        # allow one level of nesting: {"test": {"macro_f1": ...}}
        for value in d.values():
            if isinstance(value, dict) and key in value:
                return value[key]
    return default


def pct(value) -> str:
    try:
        return f"{float(value):.4f}"
    except Exception:
        return str(value)


def headline() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []

    cb = json.loads((ROOT / "data/citebench_cn/results.json").read_text(encoding="utf-8")) if (ROOT / "data/citebench_cn/results.json").exists() else {}
    rows.append(("CiteBench-CN macro-F1", pct((cb.get("metrics") or {}).get("macro_f1")), "data/citebench_cn/results.json"))

    cs = load_path(ROOT / "data/claimsupport_cn/results.json")
    rows.append(("ClaimSupport-CN macro-F1", pct((cs.get("metrics") or {}).get("macro_f1")), "data/claimsupport_cn/results.json"))

    ext = load("ext60.json")
    rows.append(("ClaimSupport-CN-Ext 60 macro-F1", pct((ext.get("metrics") or {}).get("macro_f1", ext.get("macro_f1"))), "data/experiments/ext60.json"))

    lora = load("support_lora_qwen3_1.7b.json")
    rows.append(("Qwen3-1.7B LoRA test macro-F1", pct((lora.get("test") or {}).get("macro_f1")), "data/experiments/support_lora_qwen3_1.7b.json"))
    rows.append(("Qwen3-1.7B zero-shot test macro-F1", pct((lora.get("base") or {}).get("macro_f1")), "same file (base)"))

    product = load("support_adapter_product_path.json")
    rows.append(("LoRA via product prompt macro-F1", pct((product.get("metrics") or {}).get("macro_f1", product.get("macro_f1"))), "data/experiments/support_adapter_product_path.json"))

    scifact = load("scifact_support_results.json")
    rows.append(("SciFact zero-shot macro-F1 (oracle)", pct(((scifact.get("results") or {}).get("oracle") or {}).get("macro_f1")), "data/experiments/scifact_support_results.json"))

    chart = load("chartcheck_val400_v3.json")
    rows.append(("ChartCheck-400 zero-shot accuracy", pct(chart.get("accuracy")), "data/experiments/chartcheck_val400_v3.json"))

    fig = load("figure_real26_8b_v3.json")
    rows.append(("Real-figure accuracy (n=10)", pct(((fig.get("summary") or {}).get("v3") or {}).get("accuracy")), "data/experiments/figure_real26_8b_v3.json"))

    e4 = load("e4_format.json")
    drift = e4.get("drift") or {}
    rows.append(("E4 drift regression", f"{drift.get('strict_detected','—')}/{drift.get('n','30')}", "data/experiments/e4_format.json"))

    return rows


def load_path(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


LIVE_COMMANDS = """
Live re-runs (network + API key required, long):
  CITEGUARD_JUDGE_ENDPOINT=... python scripts/eval_citebench.py
  CITEGUARD_JUDGE_ENDPOINT=... python scripts/eval_support.py --split test
  CITEGUARD_JUDGE_ENDPOINT=... python scripts/eval_support_scifact.py
  CITEGUARD_VL_ENDPOINT=...    python scripts/eval_chartcheck.py --json out/chartcheck/val400.json
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tests", action="store_true")
    args = ap.parse_args()

    failed = False
    if not args.no_tests:
        failed = run([sys.executable, "-m", "pytest", "tests", "-q"]) != 0
    # The artifact checker is best-effort: it prints claims that no longer match docs.
    run([sys.executable, "scripts/verify_artifacts.py"])

    rows = headline()
    width = max(len(name) for name, _, _ in rows) + 2
    print("\nStored evidence (recomputed from files, not retyped):")
    print("-" * (width + 34))
    for name, value, source in rows:
        print(f"{name:<{width}} {value:<10} {source}")
    print("-" * (width + 34))
    print(LIVE_COMMANDS)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
