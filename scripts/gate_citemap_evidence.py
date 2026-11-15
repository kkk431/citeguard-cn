"""Gate CiteMap evidence quotes with a strict claim-evidence judge.

Reads the 105-cell audit key (or a chosen quote file), asks the judge whether
each evidence quote fully supports the linked claim, and reports how the gate
performs against the human majority labels. This is a precision gate, not a
new extraction: a kept quote is the exact quote the human already reviewed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache" / "citemap_gate"
PROMPT = """你是一名引文核验员。给你一条中文断言和一段英文证据句，判断证据句对整条断言的支持程度。

规则：
- support：证据句支持断言的**全部核心部分**（对象、方向、结论；复合断言需要覆盖每个可检验部分），可以直接作为该断言的支持证据。
- partial：只支持断言的某一部分、只主题相关、或需要外部推断；只能标“部分支持”，不能当整条断言的证据。
- contradict：证据句明确给出与断言相反的方向或结论。
不要因为关键词相同就给 support。只输出 JSON：
{"verdict":"support|partial|contradict|none","reason":"不超过40字","quote_is_complete_sentence":true}"""


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def cache_path(claim: str, quote: str) -> Path:
    digest = hashlib.sha1((PROMPT + "\n" + claim + "\n" + quote).encode("utf-8")).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / f"{digest}.json"


def judge(claim: str, quote: str) -> dict:
    from citeguard import support

    path = cache_path(claim, quote)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = support._chat_json(PROMPT, f"断言：{claim}\n\n证据句：{quote}", max_tokens=300, timeout=45) or {}
    verdict = str(result.get("verdict") or "none").lower()
    if verdict not in {"support", "partial", "contradict", "none"}:
        verdict = "none"
    out = {"verdict": verdict, "reason": str(result.get("reason") or "")[:200]}
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def load_claims() -> dict[str, list[dict]]:
    claims: dict[str, list[dict]] = {}
    for path in (DATA / "evidence_map" / "extractions").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        topic = data.get("topic")
        topic_id = topic.get("topic_id") if isinstance(topic, dict) else topic
        claims[str(topic_id)] = list(data.get("claims") or [])
    return claims


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=str(ROOT / "dist" / "citemap_audit_full" / "_organizer_only_key.csv"))
    ap.add_argument("--merged", default=str(DATA / "experiments" / "citemap_audit_105" / "merged.csv"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(DATA / "experiments" / "citemap_fulltext_gate.json"))
    args = ap.parse_args()
    load_env()
    from citeguard import support

    if not support.judge_available():
        raise SystemExit("judge is not configured; set DEEPSEEK_API_KEY or CITEGUARD_JUDGE_BASE_URL")
    claims = {t: {c["claim_id"]: c["text"] for c in rows} for t, rows in load_claims().items()}
    with open(args.key, encoding="utf-8-sig") as fh:
        keys = {row["cell_id"]: row for row in csv.DictReader(fh)}
    with open(args.merged, encoding="utf-8-sig") as fh:
        merged = {row["cell_id"]: row for row in csv.DictReader(fh)}

    cells = []
    for cid, row in keys.items():
        if row.get("cell_kind") != "机器证据" or cid not in merged:
            continue
        if not row.get("evidence_quote"):
            continue
        claim = claims.get(row["topic_id"], {}).get(row["claim_id"], "")
        if not claim:
            continue
        cells.append((cid, row, claim, row["evidence_quote"]))
    print(f"evidence cells: {len(cells)}")

    def run(item):
        cid, row, claim, quote = item
        verdict = judge(claim, quote)
        return cid, row, verdict

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for cid, row, verdict in pool.map(run, cells):
            human = merged[cid]["majority"]
            kept = verdict["verdict"] in {"support", "contradict"}
            results.append(
                {
                    "cell_id": cid,
                    "topic_id": row["topic_id"],
                    "paper_id": row["paper_id"],
                    "claim_id": row["claim_id"],
                    "machine_stance": row["machine_stance"],
                    "human_majority": human,
                    "verdict": verdict["verdict"],
                    "reason": verdict["reason"],
                    "kept": kept,
                }
            )
            print(f"{cid} human={human} verdict={verdict['verdict']} kept={kept}")

    kept = [r for r in results if r["kept"]]
    human_correct = [r for r in results if r["human_majority"] == "correct"]
    kept_correct = [r for r in kept if r["human_majority"] == "correct"]
    dropped_wrong = [r for r in results if not r["kept"] and r["human_majority"] == "issue"]
    summary = {
        "evidence_cells": len(results),
        "human_correct": len(human_correct),
        "kept": len(kept),
        "kept_correct": len(kept_correct),
        "precision_kept": round(len(kept_correct) / len(kept), 4) if kept else 0.0,
        "recall_kept": round(len(kept_correct) / len(human_correct), 4) if human_correct else 0.0,
        "dropped_wrong": len(dropped_wrong),
        "dropped_human_correct": len([r for r in results if not r["kept"] and r["human_majority"] == "correct"]),
        "gate": "strict claim-evidence judge; keep only support/contradict",
        "note": "human majority is the reference; not a new extraction and not human re-review of new quotes",
    }
    out = {"summary": summary, "cells": results}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
