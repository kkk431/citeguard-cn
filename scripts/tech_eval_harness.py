"""Print or persist the frozen Batch-0 evaluation scorecard.

Examples:
    python scripts/tech_eval_harness.py --check
    python scripts/tech_eval_harness.py --out data/experiments/opt_b0_harness_2026-11-27.json \
        --markdown docs/optimization/b0_harness.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.tech_eval import HarnessError, check, collect, to_markdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen Batch-0 evaluation harness")
    parser.add_argument("--out", help="write scorecard JSON here")
    parser.add_argument("--markdown", help="write a Markdown table here")
    parser.add_argument("--check", action="store_true", help="exit 1 if a required gate fails")
    parser.add_argument("--experiments", help="override the data/experiments directory (tests)")
    args = parser.parse_args()

    try:
        card = collect(Path(args.experiments) if args.experiments else None)
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    problems = check(card)
    if args.check and problems:
        for p in problems:
            print(f"FAIL: {p}", file=sys.stderr)
        return 1

    text = json.dumps(card, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)
    if args.markdown:
        md = Path(args.markdown)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(to_markdown(card), encoding="utf-8")
        print(f"wrote {md}")
    for name, ok in (card.get("gates") or {}).items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
