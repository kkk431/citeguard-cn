"""Score the human blind-audit kit: coverage, kappa, majority gold, disagreements.

Usage (from the repository root):

    $env:PYTHONPATH='src'
    python scripts/score_audit_kit.py --kit dist/audit_kit --out dist/audit_kit/_results
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.audit_kit import (  # noqa: E402
    AuditKitError,
    read_key,
    read_sheet,
    score,
)


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", default="dist/audit_kit", help="audit kit directory")
    parser.add_argument("--sheets", nargs="*", default=None, help="annotator CSV paths")
    parser.add_argument("--key", default=None, help="constructed key (optional)")
    parser.add_argument("--out", default=None, help="result directory (default: <kit>/_results)")
    parser.add_argument("--min-coverage", type=float, default=0.9)
    parser.add_argument("--allow-partial", action="store_true", help="do not enforce min coverage")
    args = parser.parse_args()

    kit = Path(args.kit)
    if args.sheets:
        paths = [Path(p) for p in args.sheets]
    else:
        paths = sorted(
            p for p in kit.glob("audit_*.csv") if p.name not in {"practice.csv"}
        )
    if not paths:
        print(f"no annotator sheets under {kit}", file=sys.stderr)
        return 2

    sheets = {}
    for path in paths:
        name = path.stem.replace("audit_", "").strip() or path.stem
        sheets[name] = read_sheet(path)
    if not sheets:
        print("no sheets could be read", file=sys.stderr)
        return 2

    key = None
    key_path = Path(args.key) if args.key else (kit / "_organizer_only" / "audit_key.json")
    if key_path.exists():
        key = read_key(key_path)

    try:
        result = score(
            sheets,
            key=key,
            min_coverage=0.0 if args.allow_partial else args.min_coverage,
        )
    except AuditKitError as exc:
        print(f"cannot score: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else (kit / "_results")
    out.mkdir(parents=True, exist_ok=True)
    gold_columns = [
        "item_id",
        "claim",
        "evidence",
        "final_label",
        "votes",
        "n_labels",
        "needs_adjudication",
        "mean_confidence",
        "labels",
    ]
    write_csv(out / "human_gold.csv", result["items"], gold_columns)
    write_csv(
        out / "disagreements.csv",
        result["disagreement_items"],
        gold_columns + ["notes"],
    )

    (out / "agreement_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"annotators: {', '.join(result['annotators'])}")
    print(f"items: {result['items_complete']} / {result['items_total']}")
    print("coverage: " + ", ".join(f"{k}={v:.1%}" for k, v in result["coverage"].items()))
    if result["fleiss_kappa"] is not None:
        print(f"Fleiss kappa: {result['fleiss_kappa']:.4f}")
        print(
            "pairwise Cohen kappa: "
            + ", ".join(f"{k}={v:.4f}" for k, v in result["pairwise_cohen_kappa"].items())
        )
        print(f"mean pairwise kappa: {result['mean_pairwise_kappa']:.4f}")
    print(f"majority: {result['majority_counts']}")
    print(f"ties: {result['ties']}; disagreements: {result['disagreements']}")
    if result["constructed_key_comparison"]:
        cmp = result["constructed_key_comparison"]
        print(f"constructed-key agreement (reference only): {cmp['agreement']:.1%} on {cmp['compared']}")
    print(f"wrote {out / 'human_gold.csv'}, {out / 'disagreements.csv'}, {out / 'agreement_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
