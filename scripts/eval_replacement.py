"""Compare retrieval baselines for citation-context -> reference suggestion.

Methods:
- title-overlap: share of query tokens appearing in the candidate title
- bm25: Okapi BM25 over title + venue + year
- bge: cosine similarity of BGE-M3 embeddings (requires CITEGUARD_EMBED_ENDPOINT)

Metrics: Recall@1, Recall@5, MRR (and Recall@3 as the product's hit@3).
The ground truth is the reference the author cited; see build_replacement_eval.py
for the boundary note.

Run: PYTHONPATH=src python scripts/eval_replacement.py [--methods title,bm25,bge]
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

from citeguard.embeddings import EmbeddingError, cosine, embed_texts, is_configured

LATIN = re.compile(r"[a-z0-9]{2,}")
CJK = re.compile(r"[\u4e00-\u9fff]")


def tokens(text: str) -> list[str]:
    text = (text or "").lower()
    out = LATIN.findall(text)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        out.extend(run[i : i + 2] for i in range(max(len(run) - 1, 1)))
    return out


def metrics(rankings: list[int]) -> dict:
    n = len(rankings)
    if not n:
        return {"n": 0, "recall@1": None, "recall@3": None, "recall@5": None, "mrr": None}
    return {
        "n": n,
        "recall@1": round(sum(1 for r in rankings if r == 1) / n, 4),
        "recall@3": round(sum(1 for r in rankings if r <= 3) / n, 4),
        "recall@5": round(sum(1 for r in rankings if r <= 5) / n, 4),
        "mrr": round(sum(1 / r for r in rankings) / n, 4),
    }


def rank_of(order: list[str], target: str) -> int:
    try:
        return order.index(target) + 1
    except ValueError:
        return 10**6


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.avg = sum(len(d) for d in docs) / max(len(docs), 1)
        self.tf = [Counter(d) for d in docs]
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (len(docs) - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf in self.tf:
            s = 0.0
            dl = sum(tf.values()) or 1
            for t in query:
                if t not in tf:
                    continue
                f = tf[t]
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avg)
                )
            out.append(s)
        return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/experiments/replacement_eval_dataset.json")
    parser.add_argument("--methods", default="title,bm25,bge")
    parser.add_argument("--out", default="data/experiments/replacement_eval.json")
    args = parser.parse_args()
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    keys = list(data["pool"].keys())
    docs = [
        tokens(
            " ".join(
                str(x or "")
                for x in (
                    data["pool"][k].get("title"),
                    data["pool"][k].get("venue"),
                    data["pool"][k].get("year"),
                )
            )
        )
        for k in keys
    ]
    queries = data["queries"]
    results: dict[str, dict] = {}

    if "title" in methods:
        rankings = []
        for q in queries:
            qt = set(tokens(q["query"]))
            scores = [len(qt & set(d)) / max(len(qt), 1) for d in docs]
            order = [keys[i] for i in sorted(range(len(keys)), key=lambda i: -scores[i])]
            rankings.append(rank_of(order, q["target"]))
        results["title"] = metrics(rankings)

    if "bm25" in methods:
        bm = BM25(docs)
        rankings = []
        for q in queries:
            scores = bm.scores(tokens(q["query"]))
            order = [keys[i] for i in sorted(range(len(keys)), key=lambda i: -scores[i])]
            rankings.append(rank_of(order, q["target"]))
        results["bm25"] = metrics(rankings)

    if "bge" in methods:
        try:
            if not is_configured():
                results["bge"] = {"error": "CITEGUARD_EMBED_ENDPOINT not configured"}
            else:
                texts = [data["pool"][k].get("title") or "" for k in keys]
                doc_vecs = embed_texts(texts)
                q_vecs = embed_texts([q["query"] for q in queries])
                rankings = []
                for q, vec in zip(queries, q_vecs):
                    scores = [cosine(vec, dv) for dv in doc_vecs]
                    order = [keys[i] for i in sorted(range(len(keys)), key=lambda i: -scores[i])]
                    rankings.append(rank_of(order, q["target"]))
                results["bge"] = metrics(rankings)
        except EmbeddingError as exc:
            results["bge"] = {"error": str(exc)}

    report = {
        "dataset": data["summary"],
        "results": results,
        "boundary": "Context-to-cited-reference retrieval over the 22-paper corpus; "
        "not a judgement that the cited reference supports the claim.",
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
