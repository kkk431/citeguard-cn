"""Fill every static CiteMap paper with one machine claim + abstract evidence.

The human/master extraction map is never modified.  Machine cards are written
to a separate ``extractions_machine/<topic>.json`` file and merged only by the
web API, so the human layer stays auditable on its own.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from citeguard import evidence_map
from citeguard.citemap_builder import _best_sentence

DATA = Path("data/evidence_map")
TOPICS = ("ai_education", "medical_imaging")
MACHINE_CLAIM = re.compile(r"^.+_m\d{3}$")
MACHINE_EVIDENCE = re.compile(r"^.+_em\d{3}$")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _strip_machine(extraction: dict[str, Any]) -> None:
    extraction["claims"] = [
        c for c in extraction.get("claims", [])
        if not MACHINE_CLAIM.fullmatch(str(c.get("claim_id", "")))
    ]
    extraction["evidence"] = [
        e for e in extraction.get("evidence", [])
        if not MACHINE_EVIDENCE.fullmatch(str(e.get("evidence_id", "")))
    ]
    protocol = str(extraction.get("protocol") or "")
    protocol = protocol.replace(
        " 另含每篇无人工证据论文的 1 条机器摘要卡片（extracted_by=machine:abstract-finding），"
        "用于把 30 篇铺满；机器层未人审。",
        "",
    )
    extraction["protocol"] = protocol.strip()


def fill_topic(topic: str, abstracts: dict[str, Any]) -> dict[str, int]:
    corpus_path = DATA / "corpus" / f"{topic}.json"
    extraction_path = DATA / "extractions" / f"{topic}.json"
    machine_path = DATA / "extractions_machine" / f"{topic}.json"
    corpus = _load(corpus_path)
    extraction = _load(extraction_path)
    topic_id = corpus["topic"]["topic_id"]

    # Restore the human map if an older run wrote machine rows into it.
    before = len(extraction.get("evidence", []))
    _strip_machine(extraction)
    if len(extraction.get("evidence", [])) != before:
        evidence_map.EvidenceMap.from_dict(extraction)
        _write(extraction_path, extraction)

    evidence_papers = {e.get("paper_id") for e in extraction.get("evidence", [])}
    claims: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    added = 0
    for paper in corpus.get("papers", []):
        if paper.get("paper_id") in evidence_papers:
            continue
        record = abstracts.get(str(paper.get("openalex_id", "")).upper()) or {}
        sentence = _best_sentence(str(record.get("abstract") or ""))
        if not sentence:
            continue
        added += 1
        claim_id = f"{topic_id}_m{added:03d}"
        claims.append(
            {
                "claim_id": claim_id,
                "topic_id": topic_id,
                "text": sentence[:1200],
                "population": "",
                "outcome": "",
                "direction": "",
                "notes": "机器生成：摘要句，未人审；仅补足该论文的一张机器卡片",
            }
        )
        evidence.append(
            {
                "evidence_id": f"{topic_id}_em{added:03d}",
                "claim_id": claim_id,
                "paper_id": paper["paper_id"],
                "stance": "support",
                "summary": "机器抽取：摘要句，仅证明论文报告过该句，不代表已支持任何主断言",
                "quote": sentence,
                "quote_lang": "en",
                "locator": "Abstract",
                "confidence": 0.3,
                "extracted_by": "machine:abstract-finding",
                "verified": False,
                "notes": "自动补充；人工未核对。不要把本层当作人工金标。",
            }
        )

    machine = {
        "schema_version": extraction.get("schema_version", "1.0"),
        "topic": corpus["topic"],
        "claims": claims,
        "evidence": evidence,
        "gaps": [],
        "protocol": "每篇没有人工证据的论文补 1 条机器摘要句；机器层未人审，不进人工层。",
    }
    evidence_map.EvidenceMap.from_dict(machine)
    _write(machine_path, machine)
    return {
        "papers": len(corpus.get("papers", [])),
        "claims": len(claims),
        "evidence": len(evidence),
        "added": added,
    }


def main() -> None:
    abstracts = _load(DATA / "abstracts.json")
    for topic in TOPICS:
        print(topic, fill_topic(topic, abstracts))


if __name__ == "__main__":
    main()
