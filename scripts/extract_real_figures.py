"""Extract candidate figure images from born-digital PDFs (local corpus).

Heuristic: render the page region above a caption line that starts with 图/Figure.
Candidate crops are meant for human/vision review, not automatic scoring.

Usage:
  python scripts/extract_real_figures.py --pdf-dir data/real_corpus/pdfs \
      --out out/figtest_real/candidates --max-per-paper 4
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pymupdf

CAPTION_RE = re.compile(r"^\s*(图|Figure|Fig\.)\s*(\d+|[一二三四五六七八九十]+)\b", re.I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default="data/real_corpus/pdfs")
    ap.add_argument("--out", default="out/figtest_real/candidates")
    ap.add_argument("--max-per-paper", type=int, default=4)
    ap.add_argument("--min-height-ratio", type=float, default=0.18)
    ap.add_argument("--zoom", type=float, default=2.2)
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir)
    out = Path(args.out)
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob("*.png"):
        old.unlink()

    items = []
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        try:
            doc = pymupdf.open(pdf)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {pdf.name}: {exc}")
            continue
        taken = 0
        for pno in range(min(len(doc), 12)):
            if taken >= args.max_per_paper:
                break
            page = doc[pno]
            pw, ph = page.rect.width, page.rect.height
            for block in page.get_text("blocks"):
                if taken >= args.max_per_paper:
                    break
                x0, y0, x1, y1, text = block[:5]
                first_line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
                if not CAPTION_RE.match(first_line):
                    continue
                crop_y0 = max(20, y0 - ph * 0.58)
                crop_y1 = y0 - 4
                if crop_y1 - crop_y0 < ph * args.min_height_ratio:
                    continue
                clip = pymupdf.Rect(pw * 0.06, crop_y0, pw * 0.94, crop_y1)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(args.zoom, args.zoom), clip=clip)
                if pix.width < 200 or pix.height < 120:
                    continue
                name = f"{pdf.stem[:22]}_p{pno + 1}_{taken + 1}.png"
                path = img_dir / name
                pix.save(path)
                caption = " ".join((text or "").strip().split())[:160]
                items.append(
                    {
                        "id": f"real_{len(items) + 1:02d}",
                        "image": name,
                        "pdf": pdf.name,
                        "page": pno + 1,
                        "caption": caption,
                        "width": pix.width,
                        "height": pix.height,
                    }
                )
                taken += 1
        doc.close()

    (out / "candidates.json").write_text(
        json.dumps({"source": args.pdf_dir, "n": len(items), "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"extracted {len(items)} candidates -> {out}")
    for item in items[:10]:
        print(item["id"], item["pdf"], f"p{item['page']}", item["caption"][:60])


if __name__ == "__main__":
    main()
