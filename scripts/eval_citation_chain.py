"""Real smoke evidence for the one-hop citation-chain check.

Two DOIs are enough here: one known clean, one known to cite a retracted paper.
This is not an accuracy benchmark; it is a reproducible check that the feature
actually queries OpenAlex and reports what it finds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.retraction import check_chain, summarize_chain  # noqa: E402

OUT = ROOT / "data" / "experiments" / "citation_chain_smoke.json"

DOIS = [
    "10.1038/nature14539",
    "10.1080/14653240600855905",
]


def main() -> int:
    items = []
    for doi in DOIS:
        items.append(check_chain(doi, max_refs=12))
    summary = summarize_chain(items)
    payload = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(timespec="seconds"),
        "dois": DOIS,
        "summary": summary,
        "items": items,
        "note": (
            "只查一层间接撤稿；抽样覆盖=返回/抽样，不等于全量；"
            "OpenAlex referenced_works 覆盖不全，中文文献更弱。"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
