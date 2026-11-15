"""Split compound CiteMap claims into atomic, checkable propositions.

The original topic claims contain several assertions at once (population,
predictor, outcome, direction). Evidence that supports one part was being
counted as support for the whole claim, which inflated apparent errors.

This script asks a model for 2-4 atomic claims per parent and requires the
result to remain a faithful decomposition: no new facts, every atomic claim
entails only a part of the parent. Output is reviewed by a human before use.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evidence_map"
sys.path.insert(0, str(ROOT / "scripts"))
import extract_citemap_auto_v2 as v2  # noqa: E402

SYSTEM = """Split one compound research claim into 2-4 atomic propositions.
Rules:
- Each atomic proposition must be checkable against a single sentence.
- Keep the original population, intervention, outcome and direction exactly.
- Do not add facts, do not reinterpret, do not merge parts.
- Use Chinese, concise.
- If the claim is already atomic, return one item.
Return JSON only:
{"atomic":[{"id":"a","text":"..."}]}"""


def main() -> int:
    v2._load_env()
    out = {}
    for topic_id in ("ai_education", "medical_imaging"):
        manual = json.loads((DATA / "extractions" / f"{topic_id}.json").read_text(encoding="utf-8"))
        items = []
        for claim in manual["claims"]:
            prompt = f"Parent claim:\n{claim['text']}\n\nSplit it into atomic propositions."
            try:
                obj = v2._post(SYSTEM, prompt, max_tokens=600)
            except Exception as exc:  # noqa: BLE001
                raise SystemExit(f"{topic_id}/{claim['claim_id']} failed: {exc}") from exc
            atomic = obj.get("atomic") or []
            if not isinstance(atomic, list) or not atomic:
                raise SystemExit(f"{topic_id}/{claim['claim_id']} returned no atomic claims")
            for idx, item in enumerate(atomic, 1):
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                items.append(
                    {
                        "atomic_id": f"{claim['claim_id']}-a{idx}",
                        "parent_claim_id": claim["claim_id"],
                        "text": text,
                    }
                )
        out[topic_id] = {"topic_id": topic_id, "claims": items}
        (DATA / "claims_atomic.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "note": "Atomic decomposition of CiteMap claims; review before using in a benchmark.",
                    "topics": out,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(topic_id, len(items), "atomic claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
