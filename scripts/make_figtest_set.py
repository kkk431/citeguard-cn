"""Build a small figure-claim feasibility set from locally downloaded PDFs.

For each paper figure (embedded raster image with a nearby 图/表/Fig./Table
caption) we find a body sentence that refers to that figure/table number and
contains a number itself -- that sentence is a realistic "claim about the
figure".  A contradicted claim is produced by mutating one numeric value in the
sentence.  Fallback: the caption itself (label stripped).

Usage: python scripts/make_figtest_set.py [--limit 24]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "real_corpus"
OUT = ROOT / "out" / "figtest"

CAPTION_RE = re.compile(r"^(图|表|Fig\.?|Figure|Table)\s*(\d+)", re.IGNORECASE)
LABEL_STRIP_RE = re.compile(r"^(图|表|Fig\.?|Figure|Table)\s*\d+[\.:：]?\s*", re.IGNORECASE)
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
SENT_SPLIT_RE = re.compile(r"(?<=[。！？；;.!?])\s*")


def _caption_for(page: fitz.Page, rect: fitz.Rect) -> tuple[str, str, int] | None:
    best = None
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text = block[:5]
        text = " ".join((text or "").split())
        if not text or len(text) > 400:
            continue
        m = CAPTION_RE.match(text)
        if not m:
            continue
        vertical = min(abs(y0 - rect.y1), abs(rect.y0 - y1))
        horizontal = 0 if not (x1 < rect.x0 - 20 or x0 > rect.x1 + 20) else 40
        score = vertical + horizontal
        if best is None or score < best[0]:
            best = (score, text, m.group(1), int(m.group(2)))
    if best and best[0] < 170:
        return best[1], best[2], best[3]
    return None


def _sentences(text: str) -> list[str]:
    out = []
    for chunk in SENT_SPLIT_RE.split(text):
        s = " ".join(chunk.split())
        if 12 <= len(s) <= 400:
            out.append(s)
    return out


def _ref_patterns(kind: str, num: int) -> list[re.Pattern]:
    zh = {"图": "图", "表": "表"}.get(kind, kind)
    pats = [
        re.compile(rf"{zh}\s*{num}(?!\d)"),
        re.compile(rf"(?:Fig\.?|Figure)\s*{num}(?!\d)", re.IGNORECASE),
        re.compile(rf"Table\s*{num}(?!\d)", re.IGNORECASE),
    ]
    return pats


def _mutate_first_data_number(claim: str, kind: str, num: int) -> str | None:
    """Mutate the first number that is *not* the figure/table reference label."""
    ref_spans = []
    for pat in _ref_patterns(kind, num):
        ref_spans += [(m.start(), m.end()) for m in pat.finditer(claim)]
    for m in NUM_RE.finditer(claim):
        if any(a <= m.start() < b for a, b in ref_spans):
            continue
        raw = m.group(0)
        try:
            if raw.endswith("%"):
                core = raw[:-1]
                new = f"{float(core) + 7:.1f}".rstrip("0").rstrip(".") + "%"
            elif "." in raw:
                new = f"{float(raw) + 0.3:.1f}"
            else:
                new = str(int(raw) + 3)
        except ValueError:
            continue
        if new == raw:
            continue
        return claim[: m.start()] + new + claim[m.end():]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--min-width", type=int, default=260)
    ap.add_argument("--min-height", type=int, default=180)
    args = ap.parse_args()

    images_dir = OUT / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for old in images_dir.glob("*.png"):
        old.unlink()

    items = []
    seen = set()
    for pdf in sorted(CORPUS.rglob("*.pdf")):
        try:
            doc = fitz.open(pdf)
        except Exception as exc:  # pragma: no cover - corrupt file
            print(f"[skip] {pdf.name}: {exc}")
            continue
        body = _sentences("\n".join(p.get_text("text") for p in doc))
        for pno, page in enumerate(doc, start=1):
            try:
                infos = page.get_images(full=True)
            except Exception:
                continue
            for info in infos:
                xref = info[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                except Exception:
                    continue
                if pix.width < args.min_width or pix.height < args.min_height:
                    continue
                if pix.n - pix.alpha >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                cap = _caption_for(page, rects[0])
                if not cap:
                    continue
                caption, kind, num = cap
                data = pix.tobytes("png")
                digest = hashlib.md5(data).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                pats = _ref_patterns(kind, num)
                claim = None
                for sent in body:
                    if LABEL_STRIP_RE.sub("", sent).strip() == caption:
                        continue
                    if any(p.search(sent) for p in pats) and NUM_RE.search(sent):
                        claim = sent
                        break
                if claim is None:
                    claim = LABEL_STRIP_RE.sub("", caption).strip()
                contradicted = _mutate_first_data_number(claim, kind, num)
                if not contradicted:
                    continue
                name = f"{pdf.stem[:28]}_p{pno}_{xref}.png"
                (images_dir / name).write_bytes(data)
                items.append(
                    {
                        "id": name[:-4],
                        "image": name,
                        "pdf": pdf.name,
                        "page": pno,
                        "kind": kind,
                        "figure_no": num,
                        "caption": caption,
                        "claim_supported": claim,
                        "claim_contradicted": contradicted,
                    }
                )
                if len(items) >= args.limit:
                    break
            if len(items) >= args.limit:
                break
        doc.close()
        if len(items) >= args.limit:
            break

    meta = {"source": "data/real_corpus PDFs", "n": len(items), "items": items}
    (OUT / "figtest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"figures: {len(items)} -> {OUT / 'figtest.json'}")
    for item in items[:6]:
        print(f"  {item['id']}")
        print(f"    claim:  {item['claim_supported'][:100]}")
        print(f"    mutant: {item['claim_contradicted'][:100]}")


if __name__ == "__main__":
    main()
