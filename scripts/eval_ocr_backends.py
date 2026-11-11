"""Compare OCR backends on the same page image (clean raster).

Backends: rapidocr-onnxruntime (Apache-2.0, already optional in the product)
and PaddleOCR (Apache-2.0, evaluation only — not a product dependency).
Ground truth = the PDF's digital text layer for the same page.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]


def norm(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace())


def cer(pred: str, truth: str) -> float:
    p, t = norm(pred), norm(truth)
    return round(Levenshtein.distance(p, t) / max(1, len(t)), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(ROOT / "data/real_corpus/hanspub_152575.pdf"))
    ap.add_argument("--page", type=int, default=3)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--out", default=str(ROOT / "data/experiments/ocr_backends_eval.json"))
    args = ap.parse_args()

    doc = pdfium.PdfDocument(args.pdf)
    page = doc[args.page - 1]
    truth = page.get_textpage().get_text_range()
    img = np.array(page.render(scale=args.dpi / 72).to_pil().convert("RGB"))

    # Light scan simulation: small blur + gaussian noise (fixed seed).
    from PIL import Image, ImageFilter

    pil = Image.fromarray(img).filter(ImageFilter.GaussianBlur(0.6))
    rng = np.random.default_rng(20261111)
    noisy = np.clip(np.array(pil, dtype=np.int16) + rng.normal(0, 6, img.shape), 0, 255).astype(np.uint8)

    result = {"pdf": Path(args.pdf).name, "page": args.page, "dpi": args.dpi, "backends": {}}

    t0 = time.time()
    from rapidocr_onnxruntime import RapidOCR

    rapid = RapidOCR()
    out, _ = rapid(noisy)
    rapid_text = "\n".join(item[1] for item in (out or []))
    result["backends"]["rapidocr"] = {
        "seconds": round(time.time() - t0, 2),
        "chars": len(norm(rapid_text)),
        "cer": cer(rapid_text, truth),
        "sample": rapid_text[:200],
    }

    t0 = time.time()
    import types

    sys.modules.setdefault("modelscope", types.ModuleType("modelscope"))
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
    )
    res = ocr.predict(noisy)
    paddle_text = "\n".join(res[0].get("rec_texts") or [])
    result["backends"]["paddleocr"] = {
        "seconds": round(time.time() - t0, 2),
        "chars": len(norm(paddle_text)),
        "cer": cer(paddle_text, truth),
        "sample": paddle_text[:200],
    }

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
