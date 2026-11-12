"""Baseline citation-health profile on the 22-paper real corpus.

Runs the product pipeline itself (online metadata verification + local library,
no LLM support judgement) on every PDF, reads `report["health"]`, and reports the
distribution. No hand-entered scores, no cross-file joins.

Condition: local library loaded (412 entries), online verification on, support
judgement off. Authenticity reflects the real online chain (cached requests keep
this reproducible without hammering upstream); support is unavailable and
excluded. The JSON records the condition and any data-source degradation.

Run:  PYTHONPATH=src python scripts/eval_health_real.py
Out:  data/experiments/health_real.json
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from citeguard import config, pdf_extract, pipeline
from citeguard.local_library import Library

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "real_corpus"
OUT = ROOT / "data" / "experiments" / "health_real.json"


def main() -> None:
    library = Library.load(config.LIBRARY_FILE)
    rows = []
    for path in sorted(CORPUS.glob("*.pdf")):
        text, meta = pdf_extract.extract_text_with_meta(path)
        report = pipeline.analyze_text(
            text,
            path.name,
            support_max=0,
            online=True,
            library=library,
            pdf_path=str(path),
            progress=lambda *_: None,
            input_meta={"pages": meta.get("pages") or 0, "chars": len(text)},
        )
        health = report.get("health") or {}
        rows.append(
            {
                "paper": path.name,
                "pages": meta.get("pages") or 0,
                "refs": len(report.get("references") or []),
                "citations": (report.get("citations") or {}).get("summary", {}).get("total", 0),
                "overall": health.get("overall"),
                "grade": health.get("grade"),
                "confidence": health.get("confidence"),
                "dimensions": {d["key"]: d["score"] for d in health.get("dimensions") or []},
                "top_fix": (health.get("top_fixes") or [{}])[0].get("title", ""),
            }
        )

    scores = [r["overall"] for r in rows if r["overall"] is not None]
    grades: dict[str, int] = {}
    for r in rows:
        grades[r["grade"]] = grades.get(r["grade"], 0) + 1
    dims = {}
    for key in ("authenticity", "support", "relevance", "coverage", "compliance"):
        vals = [r["dimensions"].get(key) for r in rows if r["dimensions"].get(key) is not None]
        dims[key] = {"n": len(vals), "mean": round(statistics.mean(vals), 1) if vals else None}

    out = {
        "corpus": "data/real_corpus/*.pdf",
        "papers": len(rows),
        "condition": {
            "online_verify": True,
            "library_entries": len(library),
            "support_max": 0,
            "model": "none (support off)",
        },
        "mean": round(statistics.mean(scores), 1) if scores else 0,
        "median": round(statistics.median(scores), 1) if scores else 0,
        "min": min(scores) if scores else 0,
        "max": max(scores) if scores else 0,
        "grades": grades,
        "dimensions": dims,
        "rows": rows,
        "note": (
            "Rule-weighted triage score, not a journal/reviewer standard. "
            "Online condition with local library; support excluded. "
            "Scores are comparable only within the same parser/verifier version."
        ),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"{len(rows)} papers | mean {out['mean']} median {out['median']} "
        f"range {out['min']}-{out['max']} | grades {grades}"
    )
    for key, val in dims.items():
        print(f"  {key}: n={val['n']} mean={val['mean']}")


if __name__ == "__main__":
    main()
