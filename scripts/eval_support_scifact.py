"""Evaluate the claim-support judge on SciFact (external public benchmark).

SciFact (Wadden et al., 2020) is an English scientific claim-verification
dataset: each claim is annotated against cited abstracts as SUPPORT / REFUTE /
NOT_ENOUGH_INFO, plus evidence sentence indices.

This script reuses the *product* judge (``citeguard.support.judge_support``,
i.e. the two-stage Chinese prompt) zero-shot on English claims, and maps its
four labels to SciFact's three: partial -> SUPPORT, no_evidence -> NOT ENOUGH
INFO. Two settings are reported:
  - ``oracle``: only the annotated evidence sentences + title are shown
    (comparable to "label prediction with gold rationale");
  - ``abstract``: the whole cited abstract is shown (closer to the product
    scenario, harder).

The raw SciFact files are NOT redistributed with this repository: download them
from https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz and
extract under data/experiments/scifact_raw/ (git-ignored).
Licences: claims/evidence annotations CC BY 4.0; corpus abstracts ODC-By 1.0;
code Apache-2.0. Attribution: Wadden et al., "Fact or Fiction: Verifying
Scientific Claims", EMNLP 2020.

Usage:
    DEEPSEEK_API_KEY=... PYTHONPATH=src python scripts/eval_support_scifact.py --limit 40
    DEEPSEEK_API_KEY=... PYTHONPATH=src python scripts/eval_support_scifact.py --setting both
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import citeguard.config as config  # noqa: E402
from citeguard.support import judge_support  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "experiments" / "scifact_raw" / "data"
OUT = ROOT / "data" / "experiments" / "scifact_support_results.json"
LABELS = ["SUPPORT", "CONTRADICT", "NOT_ENOUGH_INFO"]
LOCK = threading.Lock()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing SciFact file: {path} (download instructions in the docstring)")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
        doc_id = cited[0]
        doc = corpus.get(doc_id)
        if not doc:
            continue
        ev = (row.get("evidence") or {}).get(str(doc_id)) or (row.get("evidence") or {}).get(doc_id)
        labels = [e.get("label") for e in (ev or []) if e.get("label")]
        full = evidence_text(doc, None)
        if labels:
            if "CONTRADICT" in labels:
                gold = "CONTRADICT"
            elif "SUPPORT" in labels:
                gold = "SUPPORT"
            else:
                gold = "NOT_ENOUGH_INFO"
            sent_ids: list[int] = []
            for e in ev or []:
                sent_ids.extend(e.get("sentences") or [])
            oracle = evidence_text(doc, sent_ids) if sent_ids else full
        else:
            # No annotated rationale: "oracle" has nothing to use, so fall back
            # to the whole abstract (same input as the abstract setting).
            gold = "NOT_ENOUGH_INFO"
            oracle = full
        examples.append(
            {
                "id": row.get("id"),
                "claim": (row.get("claim") or "").strip(),
                "gold": gold,
                "oracle_evidence": oracle,
                "abstract_evidence": full,
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
    if label in {"support", "partial"}:
        return "SUPPORT"
    if label == "contradict":
        return "CONTRADICT"
    return "NOT_ENOUGH_INFO"


def run_setting(examples: list[dict], setting: str, workers: int) -> dict:
    key = "oracle_evidence" if setting == "oracle" else "abstract_evidence"
    preds: list[str] = [""] * len(examples)
    raw_labels: list[str] = [""] * len(examples)

    def work(i: int) -> None:
        ex = examples[i]
        out = judge_support(ex["claim"], ex[key])
        label = (out or {}).get("label", "not_checked")
        with LOCK:
            raw_labels[i] = label
            preds[i] = map_label(label)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, range(len(examples))))

    result = metrics(examples, preds)
    result.update(
        {
            "setting": setting,
            "n": len(examples),
            "raw_label_counts": {label: raw_labels.count(label) for label in set(raw_labels)},
            "failures": sum(1 for label in raw_labels if label in {"", "not_checked"}),
        }
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA))
    ap.add_argument("--limit", type=int, default=0, help="limit claims (0 = all 300 dev claims)")
    ap.add_argument("--setting", choices=("oracle", "abstract", "both"), default="both")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    if not config.DEEPSEEK_API_KEY:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2
    data_dir = Path(args.data_dir)
    claims = load_jsonl(data_dir / "claims_dev.jsonl")
    corpus = {row["doc_id"]: row for row in load_jsonl(data_dir / "corpus.jsonl")}
    if args.limit:
        claims = claims[: args.limit]
    examples = build_examples(claims, corpus)
    print(f"SciFact dev claims: {len(claims)}; usable claim-doc pairs: {len(examples)}")

    settings = ("oracle", "abstract") if args.setting == "both" else (args.setting,)
    started = time.time()
    results = {setting: run_setting(examples, setting, args.workers) for setting in settings}
    payload = {
        "dataset": "SciFact (Wadden et al., EMNLP 2020)",
        "license": {
            "claims_and_evidence": "CC BY 4.0",
            "corpus_abstracts": "ODC-By 1.0",
            "code": "Apache-2.0",
        },
        "note": (
            "Zero-shot evaluation of the product judge (two-stage Chinese prompt) on English SciFact; "
            "partial is mapped to SUPPORT and no_evidence to NOT_ENOUGH_INFO. "
            "Not comparable with fine-tuned SciFact systems (no training on SciFact)."
        ),
        "n_claims": len(claims),
        "n_examples": len(examples),
        "elapsed_sec": round(time.time() - started, 1),
        "results": results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for setting, result in results.items():
        print(
            f"  {setting:8s} macro-F1={result['macro_f1']:.4f} acc={result['accuracy']:.4f} "
            f"n={result['n']} failures={result['failures']}"
        )
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
