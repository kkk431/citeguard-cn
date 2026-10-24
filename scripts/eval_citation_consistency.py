"""Evaluate the in-text citation consistency checker on hand-built cases.

Each case declares the expected flags from the GB/T 7714 sequential-numeric
rule, independently of the implementation.  Run:

    PYTHONPATH=src python scripts/eval_citation_consistency.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.gbt7714 import citation_consistency  # noqa: E402
from citeguard.reference_parser import parse_intext_citations, parse_reference  # noqa: E402

CASES = ROOT / "data" / "citation_consistency_cases" / "cases.json"
OUT = ROOT / "data" / "experiments" / "citation_consistency.json"


def evaluate() -> dict:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    rows = []
    for case in data["cases"]:
        refs = [parse_reference(raw, index=i + 1) for i, raw in enumerate(case["refs"])]
        intext = parse_intext_citations(case["body"])
        got = citation_consistency(refs, intext)
        exp = case["expected"]
        checks = {
            "numeric_style": got["numeric_style"] == exp["numeric_style"],
            "missing": got["missing_numbers"] == exp["missing"],
            "uncited": got["uncited_numbers"] == exp["uncited"],
            "order_inversions": got["order_inversions"] == exp["order_inversions"],
        }
        rows.append(
            {
                "id": case["id"],
                "pass": all(checks.values()),
                "checks": checks,
                "expected": exp,
                "got": {
                    "numeric_style": got["numeric_style"],
                    "missing": got["missing_numbers"],
                    "uncited": got["uncited_numbers"],
                    "order_inversions": got["order_inversions"],
                },
            }
        )
    total = len(rows)
    passed = sum(1 for r in rows if r["pass"])
    summary = {
        "name": data["name"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cases": total,
        "passed": passed,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "field_accuracy": {
            key: round(sum(1 for r in rows if r["checks"][key]) / total, 4) if total else 0.0
            for key in ("numeric_style", "missing", "uncited", "order_inversions")
        },
        "failures": [r["id"] for r in rows if not r["pass"]],
        "rows": rows,
        "notes": "Cases are constructed from the GB/T sequential-numeric rule; expected sets are exact.",
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    summary = evaluate()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[citation-consistency] {summary['passed']}/{summary['cases']} cases "
        f"accuracy={summary['accuracy']:.4f} failures={summary['failures']}"
    )
    return 0 if summary["passed"] == summary["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
