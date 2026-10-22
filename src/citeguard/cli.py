"""CLI entry point.

Usage:
    python -m citeguard.cli --input paper.pdf --out out/demo
    python -m citeguard.cli --input papers/ --out out/batch      # batch directory
    python -m citeguard.cli --input refs.txt --refs-only --no-verify
    python -m citeguard.cli --import-library cnki_export.ris     # build local library
    python -m citeguard.cli --input paper.pdf --library cnki_export.ris
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the repo root without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from citeguard import config  # noqa: E402
from citeguard.local_library import Library, parse_library_text  # noqa: E402
from citeguard.pdf_extract import SUPPORTED_SUFFIXES, extract_text  # noqa: E402
from citeguard.pipeline import analyze_text  # noqa: E402
from citeguard.report import save_report  # noqa: E402


LIBRARY_SUFFIXES = {".ris", ".bib", ".enw", ".json", ".csl", ".txt"}


def _read_library_file(path: Path) -> list:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return parse_library_text(raw.decode(encoding), path.name)
        except UnicodeDecodeError:
            continue
    return parse_library_text(raw.decode("utf-8", errors="replace"), path.name)


def _read_library(path: Path) -> list:
    """Read one export file, or every supported export file in a directory."""
    if path.is_dir():
        entries: list = []
        for item in sorted(path.iterdir()):
            if item.is_file() and item.suffix.lower() in LIBRARY_SUFFIXES:
                entries.extend(_read_library_file(item))
        return entries
    return _read_library_file(path)


def _load_library(args) -> Library:
    library = Library.load(config.LIBRARY_FILE)
    if args.library:
        path = Path(args.library)
        if not path.exists():
            print(f"[warn] library not found: {path}", file=sys.stderr)
        else:
            library.add(_read_library(path))
    return library


def _input_text(input_path: Path, args) -> tuple[str, str]:
    """Return (text_for_analysis, source_name)."""
    text = extract_text(input_path)
    if args.refs_only:
        return "参考文献\n" + text, input_path.name
    if args.refs:
        refs_path = Path(args.refs)
        if not refs_path.exists():
            raise SystemExit(f"[error] refs file not found: {refs_path}")
        return f"{text}\n参考文献\n{extract_text(refs_path)}", input_path.name
    return text, input_path.name


def _analyze_one(input_path: Path, args, library: Library) -> dict:
    text, source_name = _input_text(input_path, args)
    report = analyze_text(
        text,
        source_name,
        support_max=None if args.support_max is None else args.support_max,
        online=not args.no_verify,
        use_arxiv=not args.no_arxiv,
        library=library,
        max_refs=args.max_refs,
    )
    paths = save_report(report, args.out, stem=args.stem)
    return {"report": report, "paths": paths, "source": source_name}


def _print_summary(report: dict, source: str) -> None:
    s = report["stats"]
    print(f"\n=== {source} ===")
    print(
        f"references: {s['total']}  exact: {s['Exact']}  minor: {s['Minor']}  "
        f"major: {s['Major']}  unverified: {s.get('Unverified', 0)}  unknown: {s['Unknown']}"
    )
    print(f"GB/T 7714-2025 avg compliance: {s['avg_compliance']}/100   risk index: {s['risk_index']}")
    if s.get("library_entries"):
        print(f"local library: {s['library_entries']} entries, {s.get('library_hits', 0)} references verified from it")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CiteGuard-CN: Chinese citation verification + GB/T 7714-2025 check")
    ap.add_argument("--input", help="paper file (.pdf/.docx/.txt/.md) or a directory for batch mode")
    ap.add_argument("--refs", help="optional separate reference-list file")
    ap.add_argument("--refs-only", action="store_true", help="treat --input as a reference list, not a full paper")
    ap.add_argument("--out", default="out", help="output directory")
    ap.add_argument("--no-verify", action="store_true", help="skip online metadata verification")
    ap.add_argument("--no-arxiv", action="store_true", help="do not query arXiv")
    ap.add_argument("--max-refs", type=int, default=0, help="limit number of references (0 = all)")
    ap.add_argument("--support-max", type=int, default=None, help="how many references get an LLM support verdict (default: config)")
    ap.add_argument("--stem", default="report", help="output file stem")
    ap.add_argument("--library", help="RIS/EndNote/BibTeX/CSL-JSON/plain list used as local verification source")
    ap.add_argument("--import-library", help="merge a library file into data/library/library.json and exit")
    args = ap.parse_args(argv)

    if args.import_library:
        path = Path(args.import_library)
        if not path.exists():
            print(f"[error] library not found: {path}", file=sys.stderr)
            return 2
        library = Library.load(config.LIBRARY_FILE)
        before = len(library)
        library.add(_read_library(path))
        library.save(config.LIBRARY_FILE)
        print(f"library: {before} -> {len(library)} entries (saved to {config.LIBRARY_FILE})")
        return 0

    if not args.input:
        print("[error] --input is required (or use --import-library)", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] input not found: {input_path}", file=sys.stderr)
        return 2

    library = _load_library(args)

    if input_path.is_dir():
        files = sorted(p for p in input_path.iterdir() if p.suffix.lower() in SUPPORTED_SUFFIXES)
        if not files:
            print(f"[error] no supported files in {input_path}", file=sys.stderr)
            return 2
        print(f"[batch] {len(files)} files")
        failed = 0
        for path in files:
            try:
                result = _analyze_one(path, args, library)
                _print_summary(result["report"], result["source"])
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
                failed += 1
                print(f"[fail] {path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"\n[done] {len(files) - failed}/{len(files)} files, output in {args.out}")
        return 0 if failed == 0 else 1

    try:
        result = _analyze_one(input_path, args, library)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 3
    report = result["report"]
    print(f"[1/3] parsed {report['stats']['total']} references, {report['stats']['intext_citations']} in-text citations")
    print("[2/3] verification + GB/T check done")
    print("[3/3] reports written")
    _print_summary(report, result["source"])
    print("\noutputs:")
    for kind, path in result["paths"].items():
        print(f"  {kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
