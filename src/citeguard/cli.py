"""CLI entry point.

Usage:
    python -m citeguard.cli --input paper.pdf --out out/demo
    python -m citeguard.cli --input refs.txt --refs-only --no-verify
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the repo root without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from citeguard.gbt7714 import check_reference_list, summarize  # noqa: E402
from citeguard.metadata_verify import verify_many  # noqa: E402
from citeguard.pdf_extract import extract_text, split_references  # noqa: E402
from citeguard.reference_parser import parse_intext_citations, parse_reference_list  # noqa: E402
from citeguard.report import build_report, save_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CiteGuard-CN: Chinese citation verification + GB/T 7714-2025 check")
    ap.add_argument("--input", required=True, help="paper file (.pdf/.txt/.md) or reference list file")
    ap.add_argument("--refs", help="optional separate reference-list file")
    ap.add_argument("--refs-only", action="store_true", help="treat --input as a reference list, not a full paper")
    ap.add_argument("--out", default="out", help="output directory")
    ap.add_argument("--no-verify", action="store_true", help="skip online metadata verification")
    ap.add_argument("--no-arxiv", action="store_true", help="do not query arXiv")
    ap.add_argument("--max-refs", type=int, default=0, help="limit number of references (0 = all)")
    ap.add_argument("--stem", default="report", help="output file stem")
    args = ap.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] input not found: {input_path}", file=sys.stderr)
        return 2

    text = extract_text(input_path)
    if args.refs_only:
        body, refs_text = "", text
    else:
        body, refs_text = split_references(text)
        if not refs_text and args.refs:
            refs_text = extract_text(args.refs)
        if not refs_text:
            # Last resort: treat everything after the first line that looks like an entry.
            refs_text = text

    refs = parse_reference_list(refs_text)
    if args.max_refs > 0:
        refs = refs[: args.max_refs]
    if not refs:
        print("[error] no references parsed. Check the file or use --refs.", file=sys.stderr)
        return 3

    intext = parse_intext_citations(body)
    print(f"[1/3] parsed {len(refs)} references, {len(intext)} in-text citations")

    if args.no_verify:
        verify_results = [None] * len(refs)  # type: ignore[list-item]
        print("[2/3] metadata verification skipped (--no-verify)")
    else:
        print("[2/3] verifying metadata via OpenAlex/Crossref/arXiv ...")
        verify_results = verify_many(refs, use_arxiv=not args.no_arxiv)

    print("[3/3] checking GB/T 7714-2025 fields ...")
    compliance = check_reference_list(refs)

    report = build_report(str(input_path), body, refs, verify_results, compliance, intext)  # type: ignore[arg-type]
    paths = save_report(report, args.out, stem=args.stem)

    s = report["stats"]
    print("\n=== summary ===")
    print(f"references: {s['total']}  exact: {s['Exact']}  minor: {s['Minor']}  major: {s['Major']}  unknown: {s['Unknown']}")
    print(f"GB/T 7714-2025 avg compliance: {s['avg_compliance']}/100")
    print(f"risk index: {s['risk_index']}")
    print("\noutputs:")
    for k, v in paths.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
