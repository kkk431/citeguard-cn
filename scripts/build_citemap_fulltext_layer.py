"""Turn the offline full-text verification into a product evidence layer.

The 1.7.29 evaluation verifies atomic claims against full texts.  This script
publishes the *full* and *partial* verdicts as machine evidence that CiteMap
can display next to the abstract-only atomic layer.  It never marks the
evidence as human-verified: every card keeps ``verified=false`` and an explicit
"未人审" label in the UI.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "experiments" / "citemap_atomic_fulltext_v2.json"
ATOMIC = ROOT / "data" / "evidence_map" / "claims_atomic.json"
OUT_DIR = ROOT / "data" / "evidence_map" / "extractions_fulltext"
TOPICS = ("ai_education", "medical_imaging")


def main() -> int:
    results = json.loads(RESULTS.read_text(encoding="utf-8"))["results"]
    atomic_doc = json.loads(ATOMIC.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for topic in TOPICS:
        claims = {
            item["atomic_id"]: item
            for item in (atomic_doc.get("topics", {}).get(topic, {}).get("claims") or [])
        }
        evidence = []
        seen = set()
        for item in results:
            verdict = item.get("verdict")
            if verdict not in {"full", "partial"}:
                continue
            atomic_id = item.get("atomic_id") or ""
            paper_id = item.get("paper_id")
            if not atomic_id or not paper_id or atomic_id not in claims:
                continue
            key = (paper_id, atomic_id)
            if key in seen:
                continue
            seen.add(key)
            parent = claims[atomic_id].get("parent_claim_id") or item.get("parent_claim_id")
            evidence.append({
                "evidence_id": f"ft-{topic}-{paper_id}-{atomic_id}".replace("_", "-"),
                "claim_id": parent,
                "parent_claim_id": parent,
                "atomic_id": atomic_id,
                "paper_id": paper_id,
                "stance": "support",
                "summary": f"全文逐句核验为 {verdict}；原子断言：{claims[atomic_id].get('text', '')}",
                "quote": item.get("evidence") or "",
                "locator": "Full text · 逐句检索",
                "confidence": 0.9 if verdict == "full" else 0.65,
                "extracted_by": "fulltext:atomic-v2",
                "verified": False,
                "fulltext_verdict": verdict,
                "notes": (item.get("reason") or "")[:800],
            })
        payload = {
            "schema_version": "1.0",
            "topic_id": topic,
            "extractor": "fulltext:atomic-v2",
            "extracted_at": "2026-11-15",
            "protocol": "21 atomic claims x local OA full texts; full/partial only; quote must match a candidate sentence.",
            "evidence": evidence,
        }
        (OUT_DIR / f"{topic}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(topic, len(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
