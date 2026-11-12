"""Score a filled blind-audit sheet against its answer key.

    python scripts/score_audit_sheet.py --sheet data/audit/audit_sheet.csv \
        --key data/audit/audit_key.json

The sheet from ``scripts/build_audit_sheet.py`` has empty ``human_label``
cells on purpose; fill them with support / partial / contradict / no_evidence
and keep the key away from the annotator.

Exit codes: 0 scored, 2 sheet/key problem (empty, unknown label, too many
missing rows).  A partial sheet needs ``--allow-partial`` and is reported as
partial, never as a full result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.audit_score import (  # noqa: E402
    AuditError,
    compare_predictions,
    load_human_sheet,
    load_key,
    load_predictions,
    score,
)


def _print(result: dict) -> None:
    print(f"scored {result['n_scored']}/{result['n_key']} items "
          f"(coverage {result['coverage']:.0%})")
    print(f"accuracy {result['accuracy']:.4f}  macro-F1 {result['macro_f1']:.4f}  "
          f"kappa {result['kappa']:.4f}")
    print(f"{'label':<12}{'support':>8}{'precision':>11}{'recall':>8}{'f1':>8}")
    for label, row in result["per_label"].items():
        print(f"{label:<12}{row['support']:>8}{row['precision']:>11.4f}"
              f"{row['recall']:>8.4f}{row['f1']:>8.4f}")
    labels = result["confusion"]["labels"]
    print("confusion (rows=gold, cols=human): " + " ".join(f"{l:>11}" for l in labels))
    for label, row in zip(labels, result["confusion"]["matrix"]):
        print(f"{label:>11} " + " ".join(f"{n:>11}" for n in row))
    if result["confidence"]:
        c = result["confidence"]
        print(f"confidence n={c['n']} mean={c['mean']} mean_correct={c['mean_correct']}")
    if result["missing"]:
        print(f"missing ({len(result['missing'])}): {', '.join(result['missing'][:10])}"
              + (" ..." if len(result["missing"]) > 10 else ""))
    if result["unknown_ids"]:
        print(f"ids not in key: {', '.join(result['unknown_ids'][:10])}")
    if result["partial"]:
        print("PARTIAL: not every key item was labeled; do not quote as a full audit.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--predictions", help="optional CSV: item_id,label")
    ap.add_argument("--allow-partial", action="store_true")
    ap.add_argument("--json-out")
    args = ap.parse_args()

    try:
        human = load_human_sheet(args.sheet)
        gold = load_key(args.key)
        result = score(human, gold, allow_partial=args.allow_partial)
        if args.predictions:
            result["predictions"] = compare_predictions(
                human, gold, load_predictions(args.predictions)
            )
    except AuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _print(result)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
