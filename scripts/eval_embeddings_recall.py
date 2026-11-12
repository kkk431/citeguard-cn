"""Recall@1 / MRR for the optional embedding reranker.

For each ClaimSupport-CN item: the true evidence plus 5 distractor evidence
sentences from other items. Embed claim + candidates, rank by cosine.

This is a sanity check on the embedding endpoint, not a semantic benchmark:
constructed items often share wording with their evidence, so scores are high.

Usage:
  $env:CITEGUARD_EMBED_ENDPOINT = "http://<host>:8090/v1"
  python scripts/eval_embeddings_recall.py --n 100
"""
import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from citeguard.embeddings import cosine, embed_texts, load_config  # noqa: E402


def load_items(n):
    rows = [json.loads(line) for line in Path("data/claimsupport_cn/claimsupport_cn_300.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rng = random.Random(20261112)
    rng.shuffle(rows)
    return rows[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--distractors", type=int, default=5)
    ap.add_argument("--out", default="data/experiments/embeddings_recall_bge_m3.json")
    args = ap.parse_args()

    cfg = load_config(os.environ)
    if cfg is None:
        sys.exit("CITEGUARD_EMBED_ENDPOINT is not set")
    items = load_items(args.n)
    rng = random.Random(7)
    rows = []
    for i, item in enumerate(items):
        others = [x["evidence"] for j, x in enumerate(items) if j != i]
        rng.shuffle(others)
        cands = [item["evidence"]] + others[: args.distractors]
        rows.append((item["id"], item["claim"], cands))

    texts = []
    for _, claim, cands in rows:
        texts.append(claim)
        texts.extend(cands)
    t0 = time.time()
    vecs = embed_texts(texts, cfg)
    elapsed = time.time() - t0

    hits, rr, lat = 0, 0.0, []
    per_row = args.distractors + 2
    for k, (rid, claim, cands) in enumerate(rows):
        base = k * per_row
        q = vecs[base]
        sims = [cosine(q, v) for v in vecs[base + 1 : base + 1 + args.distractors + 1]]
        order = sorted(range(len(sims)), key=lambda x: -sims[x])
        rank = order.index(0) + 1
        hits += rank == 1
        rr += 1.0 / rank
        lat.append(rank)

    result = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "endpoint": cfg.endpoint,
        "model": cfg.model,
        "n": len(rows),
        "distractors": args.distractors,
        "recall_at_1": round(hits / len(rows), 4),
        "mrr": round(rr / len(rows), 4),
        "embed_seconds": round(elapsed, 2),
        "boundary": "构造集，正例证据与引用句措辞接近；只验证向量端点与重排链路，不代表语义检索 SOTA。",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
