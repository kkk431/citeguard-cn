"""Measure parse + verify latency on real papers (honest wall-clock, cache warm)."""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from citeguard import metadata_verify as mv  # noqa: E402
from citeguard.pdf_extract import extract_text_with_meta, split_references  # noqa: E402
from citeguard.reference_parser import parse_reference_list  # noqa: E402

OUT = ROOT / "data" / "experiments" / "latency_bench.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    rows = []
    for pdf in args.pdfs:
        p = Path(pdf)
        t0 = time.perf_counter()
        text, _ = extract_text_with_meta(str(p))
        _, refs_text = split_references(text)
        refs = parse_reference_list(refs_text)
        parse_s = time.perf_counter() - t0
        if not refs:
            rows.append({"file": p.name, "error": "no refs"}); continue
        t1 = time.perf_counter()
        mv.verify_many(refs, progress=False, workers=args.workers)
        verify_s = time.perf_counter() - t1
        rows.append({"file": p.name, "refs": len(refs), "parse_s": round(parse_s, 2),
                     "verify_s": round(verify_s, 2), "total_s": round(parse_s + verify_s, 2)})
        print(rows[-1], flush=True)
    data = {"note": "wall clock on this machine; metadata cache warm from prior eval runs; support judge disabled", "rows": rows}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
