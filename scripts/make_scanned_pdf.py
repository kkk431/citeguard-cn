"""Rasterize a text-layer PDF into an image-only PDF (OCR regression fixture).

The output has no text layer at all, so ``pdf_extract.extract_text`` has to go
through the OCR fallback. Used to validate the optional OCR path end-to-end on
real papers; the generated file stays in ``out/`` (git-ignored).

Usage:
    python scripts/make_scanned_pdf.py --input data/real_corpus/hanspub_152572.pdf \
        --output out/scanned_sample.pdf --dpi 150 --max-pages 3
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--max-pages", type=int, default=0, help="0 = all pages")
    args = ap.parse_args()

    src = Path(args.input)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(src))
    total = len(pdf)
    page_count = total if not args.max_pages else min(total, args.max_pages)
    images: list[Image.Image] = []
    for index in range(page_count):
        page = pdf[index]
        # scale = dpi / 72 (PDF points)
        bitmap = page.render(scale=args.dpi / 72.0)
        image = bitmap.to_pil().convert("RGB")
        images.append(image)
    if not images:
        raise SystemExit("no pages rendered")
    images[0].save(out, "PDF", save_all=True, append_images=images[1:], resolution=args.dpi)
    print(f"wrote {out} ({page_count}/{total} pages, dpi={args.dpi})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
