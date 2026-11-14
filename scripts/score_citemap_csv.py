"""Score CiteMap CSV verification packs.

Inputs are the reviewer CSVs produced by ``build_citemap_audit_csv.py`` and the
organizer key.  The script never invents human labels: blank cells are reported
as uncovered, and disagreements are left for adjudication.

Usage:
    python scripts/score_citemap_csv.py \
        --key dist/citemap_audit/_organizer_only_key.csv \
        --reviewer dist/citemap_audit/reviewer_A.csv \
        --reviewer dist/citemap_audit/reviewer_B.csv \
        --out dist/citemap_audit/_results
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

VERDICTS = {
    "正确": "correct",
    "有问题": "issue",
    "跳过": "skip",
    "correct": "correct",
    "issue": "issue",
    "skip": "skip",
}
ISSUES = {
    "引用句不存在",
    "断言错配",
    "立场错",
    "方法或样本错",
    "论文信息错",
    "其他",
}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_key(path: Path) -> dict[str, dict]:
    rows = read_rows(path)
    return {row["cell_id"]: row for row in rows}


def normalise_verdict(raw: str) -> str | None:
    raw = (raw or "").strip()
    return VERDICTS.get(raw)


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b) if x in {"correct", "issue"} and y in {"correct", "issue"}]
    n = len(pairs)
    if not n:
        return None
    po = sum(x == y for x, y in pairs) / n
    ca = Counter(x for x, _ in pairs)
    cb = Counter(y for _, y in pairs)
    labels = set(ca) | set(cb)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in labels)
    if pe >= 1:
        return 1.0
    return (po - pe) / (1 - pe)


def fleiss_kappa(ratings: list[list[str]]) -> float | None:
    # ratings: one list per item, containing correct/issue (skip already removed)
    usable = [r for r in ratings if len(r) >= 2]
    if not usable:
        return None
    n_items = len(usable)
    counts = [Counter(r) for r in usable]
    labels = sorted({k for c in counts for k in c})
    if len(labels) == 1:
        return 1.0
    n_raters = sum(len(r) for r in usable) / n_items
    if n_raters < 2:
        return None
    p_i = []
    for c in counts:
        total = sum(c.values())
        p_i.append((sum(v * v for v in c.values()) - total) / (total * (total - 1)))
    p_bar = sum(p_i) / n_items
    p_e = sum((sum(c[k] for c in counts) / (n_items * n_raters)) ** 2 for k in labels)
    if p_e >= 1:
        return 1.0
    return (p_bar - p_e) / (1 - p_e)


def wilson_ci(successes: int, n: int, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [max(0.0, centre - half), min(1.0, centre + half)]


def score(key: dict[str, dict], reviewers: list[dict[str, str]]) -> tuple[dict, list[dict], list[dict]]:
    cell_ids = sorted(key)
    per_cell: dict[str, dict] = {}
    issues: list[str] = []
    disagreement_rows = []

    for cell_id in cell_ids:
        ratings = []
        for reviewer in reviewers:
            raw = reviewer.get(cell_id) or {}
            verdict = normalise_verdict(raw.get("verify_verdict", ""))
            if raw and raw.get("verify_verdict", "").strip() and verdict is None:
                issues.append(f"{cell_id}: unknown verdict {raw.get('verify_verdict')!r}")
            ratings.append(verdict)
        non_skip = [r for r in ratings if r in {"correct", "issue"}]
        if not non_skip:
            continue
        counts = Counter(non_skip)
        if counts["correct"] > counts["issue"]:
            majority = "correct"
        elif counts["issue"] > counts["correct"]:
            majority = "issue"
        else:
            majority = "tie"
        per_cell[cell_id] = {
            "ratings": ratings,
            "majority": majority,
            "n_ratings": len(non_skip),
            "kind": key[cell_id].get("cell_kind", ""),
        }
        if len(set(non_skip)) > 1 or majority == "tie":
            row = {
                "cell_id": cell_id,
                "topic_id": key[cell_id].get("topic_id", ""),
                "paper_id": key[cell_id].get("paper_id", ""),
                "claim_id": key[cell_id].get("claim_id", ""),
                "cell_kind": key[cell_id].get("cell_kind", ""),
                "machine_stance": key[cell_id].get("machine_stance", ""),
            }
            for i, reviewer in enumerate(reviewers, 1):
                raw = reviewer.get(cell_id) or {}
                row[f"reviewer_{i}_verdict"] = raw.get("verify_verdict", "")
                row[f"reviewer_{i}_issue"] = raw.get("issue_type", "")
                row[f"reviewer_{i}_note"] = raw.get("verify_note", "")
            row["final_verdict"] = ""
            row["final_issue_type"] = ""
            row["adjudicator"] = ""
            row["adjudication_note"] = ""
            disagreement_rows.append(row)

    resolved = {k: v for k, v in per_cell.items() if v["majority"] in {"correct", "issue"}}
    correct = sum(v["majority"] == "correct" for v in resolved.values())
    issue = sum(v["majority"] == "issue" for v in resolved.values())
    evidence = [v for v in resolved.values() if v["kind"] == "机器证据"]
    no_evidence = [v for v in resolved.values() if v["kind"] == "无机器证据"]
    ev_correct = sum(v["majority"] == "correct" for v in evidence)
    ev_issue = sum(v["majority"] == "issue" for v in evidence)
    ne_correct = sum(v["majority"] == "correct" for v in no_evidence)
    ne_issue = sum(v["majority"] == "issue" for v in no_evidence)

    pairwise = []
    for i in range(len(reviewers)):
        for j in range(i + 1, len(reviewers)):
            ids = [
                cid
                for cid, v in per_cell.items()
                if v["ratings"][i] in {"correct", "issue"} and v["ratings"][j] in {"correct", "issue"}
            ]
            kappa = cohen_kappa(
                [per_cell[c]["ratings"][i] for c in ids],
                [per_cell[c]["ratings"][j] for c in ids],
            )
            pairwise.append({"pair": f"{i + 1}-{j + 1}", "n": len(ids), "cohen_kappa": kappa})

    all_ratings = [
        [r for r in v["ratings"] if r in {"correct", "issue"}]
        for v in per_cell.values()
    ]
    complete = [v for v in per_cell.values() if all(r is not None for r in v["ratings"])]
    agreement = (
        sum(len(set(r for r in v["ratings"] if r in {"correct", "issue"})) <= 1 for v in complete)
        / len(complete)
        if complete
        else None
    )
    items_rows = []
    for cell_id, v in per_cell.items():
        row = {
            "cell_id": cell_id,
            "topic_id": key[cell_id].get("topic_id", ""),
            "paper_id": key[cell_id].get("paper_id", ""),
            "claim_id": key[cell_id].get("claim_id", ""),
            "cell_kind": key[cell_id].get("cell_kind", ""),
            "machine_stance": key[cell_id].get("machine_stance", ""),
            "majority": v["majority"],
        }
        for i, rating in enumerate(v["ratings"], 1):
            row[f"reviewer_{i}"] = rating or ""
        items_rows.append(row)
    result = {
        "reviewers": len(reviewers),
        "cells_in_key": len(cell_ids),
        "cells_with_any_rating": len(per_cell),
        "cells_resolved": len(resolved),
        "cells_tied": sum(v["majority"] == "tie" for v in per_cell.values()),
        "agreement_all_reviewers": agreement,
        "pairwise": pairwise,
        "fleiss_kappa": fleiss_kappa(all_ratings) if len(reviewers) >= 3 else None,
        "accuracy": {
            "n": len(resolved),
            "correct": correct,
            "issue": issue,
            "rate": (correct / len(resolved)) if resolved else None,
            "wilson_95": wilson_ci(correct, len(resolved)),
        },
        "evidence_precision": {
            "n": len(evidence),
            "correct": ev_correct,
            "issue": ev_issue,
            "rate": (ev_correct / len(evidence)) if evidence else None,
            "wilson_95": wilson_ci(ev_correct, len(evidence)),
        },
        "no_evidence_false_positive": {
            "n": len(no_evidence),
            "correct": ne_correct,
            "issue": ne_issue,
            "rate": (ne_issue / len(no_evidence)) if no_evidence else None,
            "wilson_95": wilson_ci(ne_issue, len(no_evidence)),
        },
        "parser_issues": issues,
        "disagreements": len(disagreement_rows),
    }
    return result, disagreement_rows, items_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--reviewer", action="append", required=True, help="repeat for A/B/C")
    ap.add_argument("--out", default="dist/citemap_audit/_results")
    args = ap.parse_args()

    key = read_key(Path(args.key))
    reviewers: list[dict[str, str]] = []
    for path in args.reviewer:
        rows = read_rows(Path(path))
        reviewers.append({row["cell_id"]: row for row in rows})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result, disagreement_rows, items_rows = score(key, reviewers)
    (out / "agreement.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (out / "adjudication.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fields = list(disagreement_rows[0].keys()) if disagreement_rows else ["cell_id"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(disagreement_rows)
    with (out / "merged.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fields = list(items_rows[0].keys()) if items_rows else ["cell_id"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(items_rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
