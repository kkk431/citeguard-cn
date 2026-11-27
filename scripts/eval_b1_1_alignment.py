"""Batch 1.4 lexical baseline audit for atomic claim/evidence alignment.

This is deliberately a *baseline* audit, not a claim of a semantic alignment
model.  It measures how far lexical retrieval gets on the machine-extracted
bilingual evidence in the CiteMap corpus.  With no judge, the alignment helper
must return ``insufficient``.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from citeguard.atomic_alignment import align_claim, rank_sentences, split_sentences
from citeguard.evidence_map import topic_payload

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="ai_education")
    ap.add_argument("--out", default="data/experiments/opt_b1_1_alignment_lexical_2026-11-27.json")
    ap.add_argument("--markdown", default="docs/optimization/b1_1_alignment.md")
    args = ap.parse_args()

    topic = topic_payload(args.topic)
    claims = {c["claim_id"]: c for c in topic.get("claims", [])}
    rows = []
    for ev in topic.get("evidence", []):
        claim = claims.get(ev.get("claim_id"))
        if not claim:
            continue
        text = ev.get("quote") or ""
        ranked = rank_sentences(claim["text"], text)
        result = align_claim(claim["text"], text)
        rows.append(
            {
                "claim_id": claim["claim_id"],
                "evidence_id": ev.get("evidence_id"),
                "claim_chars": len(claim["text"]),
                "evidence_chars": len(text),
                "quote_lang": ev.get("quote_lang"),
                "sentences": len(split_sentences(text)),
                "max_lexical_score": round(ranked[0][0], 4) if ranked else 0.0,
                "alignment_label": result.label,
                "coverage": result.coverage,
                "subclaims": len(result.subclaims),
            }
        )

    scores = [r["max_lexical_score"] for r in rows]
    payload = {
        "schema": "b1_4_lexical_baseline_v1",
        "topic": args.topic,
        "n": len(rows),
        "max_score": round(max(scores), 4) if scores else 0.0,
        "mean_score": round(statistics.mean(scores), 4) if scores else 0.0,
        "median_score": round(statistics.median(scores), 4) if scores else 0.0,
        "insufficient": sum(1 for r in rows if r["alignment_label"] == "insufficient"),
        "verdict": "lexical baseline cannot align cross-language claim/evidence; judge or embedding required",
        "rows": rows,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Batch 1.1 断言—证据对齐（词面基线审计）",
        "",
        f"- 样本：`{args.topic}` 机器抽取证据 {len(rows)} 对（非人工金标）。",
        f"- 最大词面覆盖率：**{payload['max_score']:.4f}**；均值 **{payload['mean_score']:.4f}**；中位数 **{payload['median_score']:.4f}**。",
        f"- 无 judge 时返回 insufficient：**{payload['insufficient']}/{len(rows)}**。",
        "",
        "## 结论",
        "",
        "跨语言 claim/evidence 的字面重合极低；词面检索只能召回候选句，不能当作支持度。",
        "Batch 1.1 若要有可测增益，必须接入语义 judge 或 embedding；本文件只记录负基线，不把 lexical 包装成对齐能力。",
        "",
        "## 复现",
        "",
        "```bash",
        "PYTHONPATH=src python scripts/eval_b1_1_alignment.py",
        "```",
    ]
    md_path = ROOT / args.markdown
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("n", "max_score", "mean_score", "median_score", "insufficient")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


