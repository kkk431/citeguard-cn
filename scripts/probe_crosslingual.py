"""Feasibility probe: can cross-lingual title matching recover Chinese references?

For Chinese references that OpenAlex/Crossref cannot match by the Chinese title,
translate the title to English with an LLM and search again. Reports how often a
close match appears.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard import config  # noqa: E402
from citeguard.metadata_verify import search_crossref, search_openalex, title_sim  # noqa: E402
from citeguard.reference_parser import Reference  # noqa: E402

ROWS = ROOT / "data" / "experiments" / "verify_real.json"


def translate(title: str) -> str:
    if not config.DEEPSEEK_API_KEY:
        return ""
    try:
        resp = requests.post(
            config.DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            json={
                "model": config.DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "你是学术翻译。只输出英文标题，不要解释。"},
                    {"role": "user", "content": f"把下面的中文论文标题翻译成英文学术标题：\n{title}"},
                ],
                "temperature": 0,
                "max_tokens": 120,
            },
            timeout=40,
        )
        if resp.status_code != 200:
            return ""
        text = resp.json()["choices"][0]["message"]["content"]
        return re.sub(r'^["“\s]+|["”\s.]+$', "", text.strip())
    except Exception:
        return ""


def main(limit: int = 12) -> int:
    rows = json.loads(ROWS.read_text(encoding="utf-8"))["rows"]
    cjk = [
        r
        for r in rows
        if any("\u4e00" <= ch <= "\u9fff" for ch in (r["title"] or "")) and not r["doi"]
    ][:limit]
    hits = 0
    for r in cjk:
        ref = Reference(raw=r["raw"], title=r["title"], authors=r["authors"], venue=r["venue"], year=r["year"])
        en = translate(ref.title)
        oa = search_openalex(en) if en else []
        cr = search_crossref(en) if en else []
        best = 0.0
        best_title = ""
        for c in oa + cr:
            sim = title_sim(en, c.title) if en else 0.0
            if sim > best:
                best, best_title = sim, c.title
        ok = best >= 0.78
        hits += ok
        print(f"[{'HIT' if ok else '   '}] zh={ref.title[:26]}")
        print(f"      en={en[:70]}")
        print(f"      best={best:.2f} {best_title[:60]}")
        time.sleep(0.5)
    print(f"\ncross-lingual hits: {hits}/{len(cjk)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
