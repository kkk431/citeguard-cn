"""E3 检索基线：T2Retrieval（中文段落检索）BM25 baseline。

调研脚本，不是产品代码。目的：验证开放中文检索数据能否作为 CiteMap / 替换候选
检索的外部 sanity check，并给出可复现的 BM25 数字。

数据：mteb/T2Retrieval（HF，Apache-2.0），本脚本读取其 parquet 导出：
  corpus/dev-00000-of-00001.parquet   -> _id, text, title
  queries/dev-00000-of-00001.parquet  -> _id, text
  data/dev-00000-of-00001.parquet     -> query-id, corpus-id, score
只保存 query id / doc id / 聚合指标，不落库全文。

方法：
- 分词与产品 scripts/eval_replacement.py 的 tokens() 完全一致：英文/数字 >=2 字符
  token + 中文按“字符二元组（bigram）”，不做词级切分（无 jieba 依赖）。
- Okapi BM25（k1=1.5, b=0.75），在**全量 corpus** 上建倒排（仅保留抽样 query 出现
  过的 term），对每条 query 全库打分。
- 抽样：固定种子从有 qrels 的 query 中等概率抽 N=200 条；corpus 不抽样。

运行（在 citeguard/ 下，任选其一）：
  python docs/research/experiments/e3_t2retrieval.py \
      --corpus "$env:TEMP/citeguard_e3/corpus.parquet" \
      --queries "$env:TEMP/citeguard_e3/queries.parquet" \
      --qrels  "$env:TEMP/citeguard_e3/qrels.parquet" \
      --out     docs/research/experiments/e3_t2retrieval.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
from array import array
from pathlib import Path

import numpy as np
import pandas as pd

LATIN = re.compile(r"[a-z0-9]{2,}")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")


def tokens(text: str) -> list[str]:
    """与 scripts/eval_replacement.py 中的 tokens() 保持一致。"""
    text = (text or "").lower()
    out = LATIN.findall(text)
    for run in CJK_RUN.findall(text):
        out.extend(run[i : i + 2] for i in range(max(len(run) - 1, 1)))
    return out


def random_hit_at_k(n_docs: int, n_gold: int, k: int) -> float:
    """随机排序下 hit@k 的精确期望：1 - C(N-g,k)/C(N,k)。"""
    if n_gold <= 0 or n_docs <= 0:
        return 0.0
    if n_docs - n_gold < k:
        return 1.0
    p_miss = 1.0
    for i in range(k):
        p_miss *= (n_docs - n_gold - i) / (n_docs - i)
    return 1.0 - p_miss


def random_mrr(n_docs: int, n_gold: int) -> float:
    """随机排序下 E[1/rank(first gold)] 的几何近似：-p*ln(p)/(1-p)，p=g/N。"""
    p = n_gold / n_docs
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    return -p * math.log(p) / (1.0 - p)


def metrics(ranks: list[int]) -> dict:
    n = len(ranks)
    return {
        "n": n,
        "recall@1": round(sum(1 for r in ranks if r == 1) / n, 4) if n else None,
        "recall@3": round(sum(1 for r in ranks if r <= 3) / n, 4) if n else None,
        "recall@5": round(sum(1 for r in ranks if r <= 5) / n, 4) if n else None,
        "mrr": round(sum(1.0 / r for r in ranks) / n, 4) if n else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--qrels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-queries", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--k1", type=float, default=1.5)
    ap.add_argument("--b", type=float, default=0.75)
    args = ap.parse_args()

    corpus = pd.read_parquet(args.corpus)
    queries = pd.read_parquet(args.queries)
    qrels = pd.read_parquet(args.qrels)

    doc_ids = corpus["_id"].astype(str).tolist()
    texts = corpus["text"].fillna("").tolist()
    n_docs = len(doc_ids)
    doc_index = {d: i for i, d in enumerate(doc_ids)}

    qid_text = dict(zip(queries["_id"].astype(str), queries["text"].fillna("")))
    qrels = qrels[qrels["score"] > 0].copy()
    qrels["q"] = qrels["query-id"].astype(str)
    qrels["d"] = qrels["corpus-id"].astype(str)
    gold: dict[str, set[str]] = {
        q: set(g["d"].tolist()) for q, g in qrels.groupby("q")
    }

    eligible = [q for q in sorted(gold) if q in qid_text]
    rng = np.random.default_rng(args.seed)
    take = min(args.n_queries, len(eligible))
    sample = sorted(rng.choice(eligible, size=take, replace=False).tolist())

    query_terms: dict[str, list[str]] = {}
    term_set: set[str] = set()
    for q in sample:
        uniq = list(dict.fromkeys(tokens(qid_text[q])))
        query_terms[q] = uniq
        term_set.update(uniq)

    # 倒排：仅保留抽样 query 中出现过的 term，避免全量词表内存开销。
    postings: dict[str, tuple[array, array]] = {
        t: (array("i"), array("i")) for t in term_set
    }
    dl = np.zeros(n_docs, dtype=np.int32)
    for i, text in enumerate(texts):
        toks = tokens(text)
        dl[i] = len(toks)
        if not toks:
            continue
        counts: dict[str, int] = {}
        for t in toks:
            if t in postings:
                counts[t] = counts.get(t, 0) + 1
        for t, c in counts.items():
            ids, tfs = postings[t]
            ids.append(i)
            tfs.append(c)

    avgdl = float(dl.mean()) if n_docs else 0.0
    idf = {
        t: math.log(1.0 + (n_docs - len(ids) + 0.5) / (len(ids) + 0.5))
        for t, (ids, _) in postings.items()
        if len(ids) > 0
    }

    ranks: list[int] = []
    per_query: list[dict] = []
    for q in sample:
        scores = np.zeros(n_docs, dtype=np.float64)
        for t in query_terms[q]:
            ids_arr, tfs_arr = postings.get(t, (array("i"), array("i")))
            if not len(ids_arr):
                continue
            ids = np.frombuffer(ids_arr, dtype=np.int32).astype(np.int64)
            tfs = np.frombuffer(tfs_arr, dtype=np.int32).astype(np.float64)
            denom = tfs + args.k1 * (1.0 - args.b + args.b * dl[ids] / max(avgdl, 1e-9))
            scores[ids] += idf[t] * tfs * (args.k1 + 1.0) / denom
        order = np.argsort(-scores, kind="stable")
        pos = {int(idx): r for r, idx in enumerate(order, start=1)}
        g = gold[q]
        gold_idx = [doc_index[d] for d in g if d in doc_index]
        rank = min((pos[i] for i in gold_idx), default=10**6)
        ranks.append(rank)
        per_query.append({
            "query_id": q,
            "n_gold": len(g),
            "rank_first_gold": rank,
        })

    n_gold_mean = float(np.mean([len(gold[q]) for q in sample]))
    rand = {
        "recall@1": round(float(np.mean([random_hit_at_k(n_docs, len(gold[q]), 1) for q in sample])), 6),
        "recall@3": round(float(np.mean([random_hit_at_k(n_docs, len(gold[q]), 3) for q in sample])), 6),
        "recall@5": round(float(np.mean([random_hit_at_k(n_docs, len(gold[q]), 5) for q in sample])), 6),
        "mrr": round(float(np.mean([random_mrr(n_docs, len(gold[q])) for q in sample])), 6),
    }

    report = {
        "dataset": "mteb/T2Retrieval (HF, Apache-2.0), dev split parquet",
        "n": {
            "n_docs": n_docs,
            "n_queries_total": int(queries["_id"].nunique()),
            "n_qrels_rows": int(len(qrels)),
            "n_queries_sampled": take,
            "n_gold_pairs_sampled": int(sum(len(gold[q]) for q in sample)),
            "docs_with_text": int((dl > 0).sum()),
            "avg_doc_tokens": round(float(dl.mean()), 2),
        },
        "sampling": {
            "method": "uniform over queries that have qrels, without replacement",
            "seed": args.seed,
            "corpus": "full split (no doc sampling)",
            "query_ids": sample,
        },
        "method": {
            "tokenizer": "latin/digit >=2 chars + CJK character bigrams (same as scripts/eval_replacement.py tokens())",
            "bm25": {"k1": args.k1, "b": args.b, "avgdl": round(avgdl, 2)},
            "rank": "full corpus scoring for each sampled query",
        },
        "results": {
            "bm25": metrics(ranks),
            "random_expected": rand,
        },
        "gold_stats": {
            "mean_gold_per_query": round(n_gold_mean, 3),
            "max_gold_per_query": int(max(len(gold[q]) for q in sample)),
        },
        "per_query": per_query,
        "boundary": "200/22,812 queries sampled; corpus is the MTEB T2Retrieval dev split "
        "(118,605 passages), not the full T2Ranking 2M-passage corpus. BM25 is a lexical "
        "baseline, not a Chinese semantic retrieval ceiling. Passages are web QA text, "
        "not academic citations, so this only sanity-checks the retrieval harness.",
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["n"], ensure_ascii=False))
    print(json.dumps(report["results"], ensure_ascii=False))


if __name__ == "__main__":
    main()
