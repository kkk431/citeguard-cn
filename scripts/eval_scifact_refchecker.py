r"""Run the official RefChecker LLMChecker on our SciFact dev pairs.

Protocol (same inputs as scripts/eval_support_scifact.py "oracle evidence"):
  claim    -> RefChecker "claim"
  evidence -> RefChecker "reference"
  labels   -> Entailment=SUPPORT, Contradiction=CONTRADICT, Neutral=NOT_ENOUGH_INFO

The script intentionally uses upstream RefChecker code (pip package layout from a
git clone) rather than re-implementing its prompts. Only the OpenAI-compatible
endpoint is changed, so the comparison is "their checker, our data, our model".

Usage:
  set PYTHONPATH=out\refchecker
  out\rcenv\Scripts\python.exe scripts\eval_scifact_refchecker.py --limit 20
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

LABELS = ["SUPPORT", "CONTRADICT", "NOT_ENOUGH_INFO"]
DEFAULT_DATA = ROOT / "data" / "experiments" / "scifact_raw" / "data"
DEFAULT_OUT = ROOT / "data" / "experiments" / "scifact_refchecker_deepseek.json"


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def evidence_text(doc: dict, sent_ids: list[int] | None) -> str:
    abstract = doc.get("abstract") or []
    title = doc.get("title") or ""
    if sent_ids is not None:
        sentences = [abstract[i] for i in sent_ids if 0 <= i < len(abstract)]
        body = " ".join(sentences)
    else:
        body = " ".join(abstract)
    return f"{title}. {body}".strip()[:1800]


def build_examples(claims: list[dict], corpus: dict[int, dict]) -> list[dict]:
    examples: list[dict] = []
    for row in claims:
        cited = row.get("cited_doc_ids") or []
        if not cited:
            continue
        doc = corpus.get(cited[0])
        if not doc:
            continue
        ev = (row.get("evidence") or {}).get(str(cited[0])) or (row.get("evidence") or {}).get(cited[0])
        labels = [e.get("label") for e in (ev or []) if e.get("label")]
        if "CONTRADICT" in labels:
            gold = "CONTRADICT"
        elif "SUPPORT" in labels:
            gold = "SUPPORT"
        else:
            gold = "NOT_ENOUGH_INFO"
        sent_ids: list[int] = []
        for e in ev or []:
            sent_ids.extend(e.get("sentences") or [])
        oracle = evidence_text(doc, sent_ids) if sent_ids else evidence_text(doc, None)
        examples.append(
            {
                "id": row.get("id"),
                "claim": (row.get("claim") or "").strip(),
                "gold": gold,
                "oracle_evidence": oracle,
                "abstract_evidence": evidence_text(doc, None),
            }
        )
    return examples


def metrics(rows: list[dict], preds: list[str]) -> dict:
    index = {label: i for i, label in enumerate(LABELS)}
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for row, pred in zip(rows, preds):
        matrix[index[row["gold"]]][index[pred]] += 1
    f1s, per = [], {}
    for i, label in enumerate(LABELS):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(LABELS))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1s.append(f1)
        per[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(matrix[i]),
            "predicted": sum(matrix[r][i] for r in range(len(LABELS))),
        }
    n = len(rows) or 1
    return {
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "accuracy": round(sum(matrix[i][i] for i in range(len(LABELS))) / n, 4),
        "confusion": matrix,
        "per_class": per,
    }


def map_label(label: str) -> str:
    label = (label or "").strip().lower()
    if label.startswith("entail"):
        return "SUPPORT"
    if label.startswith("contradict"):
        return "CONTRADICT"
    return "NOT_ENOUGH_INFO"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = all dev pairs")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--model", default="openai/deepseek-chat")
    ap.add_argument("--api-base", default=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--dataset", choices=["scifact", "claimsupport"], default="scifact")
    args = ap.parse_args()

    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        print("missing DEEPSEEK_API_KEY / OPENAI_API_KEY", file=sys.stderr)
        return 2
    os.environ["OPENAI_API_KEY"] = key

    from refchecker import LLMChecker, LLMExtractor

    if args.dataset == "claimsupport":
        rows = load_jsonl(ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl")
        mapping = {"support": "SUPPORT", "contradict": "CONTRADICT", "partial": "NOT_ENOUGH_INFO", "no_evidence": "NOT_ENOUGH_INFO"}
        examples = [
            {
                "id": row["id"],
                "claim": row["claim"],
                "gold": mapping[row["label"]],
                "oracle_evidence": row.get("evidence") or "",
                "abstract_evidence": row.get("evidence") or "",
            }
            for row in rows
            if row.get("label") in mapping
        ]
    else:
        claims = load_jsonl(DEFAULT_DATA / "claims_dev.jsonl")
        corpus = {row["doc_id"]: row for row in load_jsonl(DEFAULT_DATA / "corpus.jsonl")}
        examples = build_examples(claims, corpus)
    if args.limit:
        examples = examples[: args.limit]
    print(f"examples: {len(examples)}")

    started = time.time()
    extractor = LLMExtractor(model=args.model, batch_size=args.batch_size, api_base=args.api_base)
    extractions = extractor.extract_claim_triplets([e["claim"] for e in examples], max_new_tokens=400)
    if not extractions or len(extractions) != len(examples):
        print("RefChecker extraction failed", file=sys.stderr)
        return 3

    batch_claims = []
    for extraction in extractions:
        triples = [c.content for c in (extraction.claims or []) if getattr(c, "format", "") == "triplet"]
        if not triples:
            triples = [("unknown", "is", "unknown")]
        batch_claims.append(triples)

    checker = LLMChecker(model=args.model, batch_size=args.batch_size, api_base=args.api_base)
    references = [e["oracle_evidence"] for e in examples]
    results = checker.check(batch_claims, references, batch_questions=[""] * len(examples), is_joint=True, joint_check_num=5)
    if not results or len(results) != len(examples):
        print(f"unexpected RefChecker output: {type(results)} len={len(results) if results else 0}", file=sys.stderr)
        return 3

    def flatten_labels(value):
        out = []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            for item in value:
                out.extend(flatten_labels(item))
        return out

    rows, preds = [], []
    for example, triples, group in zip(examples, batch_claims, results):
        labels = flatten_labels(group)[: len(triples)]
        if any(lab.lower().startswith("entail") for lab in labels):
            pred = "SUPPORT"
        elif any(lab.lower().startswith("contradict") for lab in labels):
            pred = "CONTRADICT"
        else:
            pred = "NOT_ENOUGH_INFO"
        raw = {"triples": triples, "labels": labels}
        preds.append(pred)
        rows.append(
            {
                "id": example["id"],
                "claim": example["claim"],
                "gold": example["gold"],
                "pred": pred,
                "refchecker_raw": raw,
            }
        )
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checker": "amazon-science/RefChecker LLMChecker (official code)",
        "model": args.model,
        "api_base": args.api_base,
        "protocol": "claim vs oracle evidence (SciFact dev, same inputs as eval_support_scifact.py)",
        "n": len(rows),
        "elapsed_s": round(time.time() - started, 1),
        "metrics": metrics(rows, preds),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
