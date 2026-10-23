"""End-to-end OCR fallback evaluation on a rasterized real paper.

Takes a text-layer PDF, renders it to an image-only PDF (simulating a scanned
document), runs the OCR fallback + reference parsing, and records how much of
the reference list survives. Useful for regression on the optional OCR path and
for documenting its real-world quality.

Requires the optional OCR extras:
    pip install -r requirements-ocr.txt

Usage:
    PYTHONPATH=src python scripts/eval_ocr_scanned.py \
        --input data/real_corpus/hanspub_152572.pdf --out data/experiments/ocr_scan_real.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.pdf_extract import extract_text, split_references  # noqa: E402
from citeguard.reference_parser import parse_reference_list  # noqa: E402


def rasterize(src: Path, dst: Path, dpi: int, max_pages: int = 0) -> int:
    import pypdfium2 as pdfium
    from PIL import Image

    pdf = pdfium.PdfDocument(str(src))
    total = len(pdf)
    pages = total if not max_pages else min(total, max_pages)
    images: list[Image.Image] = []
    for index in range(pages):
        bitmap = pdf[index].render(scale=dpi / 72.0)
        images.append(bitmap.to_pil().convert("RGB"))
    if not images:
        raise SystemExit("no pages rendered")
    dst.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(dst, "PDF", save_all=True, append_images=images[1:], resolution=dpi)
    return pages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="text-layer PDF used as the source")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--max-pages", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "data" / "experiments" / "ocr_scan_real.json"))
    # An optional ground-truth reference count (e.g. from the text-layer parse).
    ap.add_argument("--expected-refs", type=int, default=0)
    args = ap.parse_args()

    src = Path(args.input)
    scanned = ROOT / "out" / f"scanned_{src.stem}.pdf"
    pages = rasterize(src, scanned, args.dpi, args.max_pages)

    started = time.time()
    text = extract_text(scanned)
    elapsed = time.time() - started
    _body, refs_text = split_references(text)
    refs = parse_reference_list(refs_text)
    coverage = {
        field: sum(1 for ref in refs if getattr(ref, field))
        for field in ("title", "authors", "year", "venue", "doi")
    }
    payload = {
        "source_pdf": str(src),
        "scanned_pdf": str(scanned),
        "pages": pages,
        "dpi": args.dpi,
        "ocr_text_chars": len(text),
        "refs_chars": len(refs_text),
        "parsed_refs": len(refs),
        "expected_refs": args.expected_refs or None,
        "field_coverage": coverage,
        "elapsed_sec": round(elapsed, 1),
        "dependencies": ["rapidocr-onnxruntime (Apache-2.0)", "pypdfium2", "Pillow"],
        "note": (
            "Image-only PDF (no text layer) rendered from a real OA paper; OCR fallback then "
            "reference parsing. Raw corpus and scanned PDFs are git-ignored; only this metrics "
            "file is committed."
        ),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
