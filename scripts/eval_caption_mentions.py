"""Evaluate figure/table caption mentions over the real corpus (rule-based)."""
from __future__ import annotations

import json
from pathlib import Path

from citeguard.citation_anchor import extract_caption_mentions, extract_citations
from citeguard.pdf_extract import extract_text_with_meta

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "real_corpus"
OUT = ROOT / "data" / "experiments" / "citation_captions.json"


def main() -> int:
    rows = []
    for pdf in sorted(CORPUS.glob("*.pdf")):
        try:
            text, meta = extract_text_with_meta(str(pdf))
            caps = extract_caption_mentions(text)
            cites = extract_citations(text)
            rows.append({
                "paper": pdf.name,
                "pages": meta.get("pages"),
                "captions_unique": len(caps),
                "captions_total": sum(c["count"] for c in caps),
                "labels": [c["label"] for c in caps][:12],
                "citations": len(cites),
            })
        except Exception as exc:  # noqa: BLE001 - report per-file failure
            rows.append({"paper": pdf.name, "error": str(exc)})
    papers = [r for r in rows if "error" not in r]
    out = {
        "corpus": "data/real_corpus",
        "papers": len(papers),
        "with_captions": sum(1 for r in papers if r["captions_unique"] > 0),
        "captions_total": sum(r["captions_total"] for r in papers),
        "captions_unique": sum(r["captions_unique"] for r in papers),
        "per_paper": rows,
        "note": ("rule-based mention detection only; counts are lower bounds; "
                 "no semantic verification; bilingual captions may list both 图 N and Figure N"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("papers", "with_captions", "captions_total", "captions_unique")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
