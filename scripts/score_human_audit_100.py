"""Score the completed 100-item, three-annotator blind audit.

Reads the raw annotator sheets (CSV, or an XLSX that was saved with a .csv
extension), the organizer key, the 300-item dataset and product predictions.
Writes ``data/experiments/human_audit_100.json`` with inter-annotator
agreement, product-vs-human confusion, accuracy/F1 and Wilson/bootstrap
intervals. No names are stored; annotators are A/B/C.
"""
from __future__ import annotations

import csv
import io
import json
import math
import random
import sys
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard import audit_kit  # noqa: E402

LABELS = ["support", "partial", "contradict", "no_evidence"]


def norm_claim(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return "".join(ch for ch in text.lower() if not ch.isspace())


def read_rows(path: Path) -> list[dict]:
    data = path.read_bytes()
    if data[:2] == b"PK":
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        return [{header[i]: ("" if row[i] is None else str(row[i])) for i in range(len(header))} for row in rows[1:] if any(v not in (None, "") for v in row)]
    for enc in ("utf-8-sig", "gb18030"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"cannot decode {path}")
    return list(csv.DictReader(io.StringIO(text)))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def macro_f1(conf: dict[str, dict[str, int]]) -> float:
    vals = []
    for lab in LABELS:
        tp = conf[lab][lab]
        fp = sum(conf[a][lab] for a in LABELS if a != lab)
        fn = sum(conf[lab][b] for b in LABELS if b != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        vals.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return sum(vals) / len(vals)


def cohen_kappa(y1: list[str], y2: list[str]) -> float:
    n = len(y1)
    if not n:
        return 0.0
    obs = sum(a == b for a, b in zip(y1, y2)) / n
    p1 = {lab: y1.count(lab) / n for lab in LABELS}
    p2 = {lab: y2.count(lab) / n for lab in LABELS}
    exp = sum(p1[lab] * p2[lab] for lab in LABELS)
    return (obs - exp) / (1 - exp) if exp != 1 else 1.0


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "data" / "audit" / "human_100"))
    ap.add_argument("--key", default=str(ROOT / "data" / "audit" / "audit_key_100.json"))
    ap.add_argument("--dataset", default=str(ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_300.jsonl"))
    ap.add_argument("--predictions", default=str(ROOT / "data" / "experiments" / "release300.json"))
    ap.add_argument("--out", default=str(ROOT / "data" / "experiments" / "human_audit_100.json"))
    args = ap.parse_args()

    raw = Path(args.raw)
    sheets = {}
    for name in ("A", "B", "C"):
        path = raw / f"audit_{name}.csv"
        rows = read_rows(path)
        sheets[name] = {r["item_id"]: {"human_label": (r.get("human_label") or "").strip(), "confidence_1_5": (r.get("confidence_1_5") or "").strip(), "note": (r.get("note") or "").strip()} for r in rows if r.get("item_id")}
    key = {k: v["label"] for k, v in json.loads(Path(args.key).read_text(encoding="utf-8"))["labels"].items()}
    human = audit_kit.score(sheets, key=key, min_coverage=1.0)
    gold = {item["item_id"]: item["final_label"] for item in human["items"]}

    dataset = {norm_claim(item["claim"]): item for item in (json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip())}
    predictions = {p["id"]: p["pred"] for p in json.loads(Path(args.predictions).read_text(encoding="utf-8"))["predictions"]}
    explain = {}
    for rows in sheets.values():
        for iid, row in rows.items():
            explain.setdefault(iid, row)
    # claims come from the blank sheet, not from annotator columns
    claim_by_id = {}
    blank = read_rows(ROOT / "data" / "audit" / "audit_sheet_100.csv")
    for row in blank:
        claim_by_id[row["item_id"]] = row["claim"]

    confusion = {a: {b: 0 for b in LABELS} for a in LABELS}
    pairs = []
    missing = []
    for iid in sorted(gold):
        ds = dataset.get(norm_claim(claim_by_id.get(iid, "")))
        pred = predictions.get(ds["id"]) if ds else None
        if pred not in LABELS:
            missing.append(iid)
            continue
        exp = gold[iid]
        confusion[exp][pred] += 1
        pairs.append((iid, ds["id"], exp, pred))
    n = len(pairs)
    correct = sum(exp == pred for _, _, exp, pred in pairs)
    acc = correct / n if n else 0
    f1 = macro_f1(confusion)
    y_exp = [exp for _, _, exp, _ in pairs]
    y_pred = [pred for _, _, _, pred in pairs]
    kappa = cohen_kappa(y_exp, y_pred)
    lo, hi = wilson(correct, n)

    rng = random.Random(20261115)
    boots = []
    for _ in range(2000):
        sample = [rng.randrange(n) for _ in range(n)]
        c = {a: {b: 0 for b in LABELS} for a in LABELS}
        for i in sample:
            _, _, exp, pred = pairs[i]
            c[exp][pred] += 1
        boots.append(macro_f1(c))
    boots.sort()
    boot_lo, boot_hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]

    report = {
        "n_items": human["items_total"],
        "annotators": human["annotators"],
        "coverage": human["coverage"],
        "fleiss_kappa": human["fleiss_kappa"],
        "pairwise_cohen_kappa": human["pairwise_cohen_kappa"],
        "majority_counts": human["majority_counts"],
        "ties": human["ties"],
        "disagreements": [(d["item_id"], d["final_label"], d["labels"], d.get("notes", "")) for d in human["disagreement_items"]],
        "constructed_key_agreement": human["constructed_key_comparison"],
        "product": {
            "mapped": n,
            "missing": missing,
            "accuracy": acc,
            "accuracy_wilson95": [lo, hi],
            "macro_f1": f1,
            "macro_f1_bootstrap95": [boot_lo, boot_hi],
            "cohen_kappa": kappa,
            "confusion_labels": LABELS,
            "confusion": [[confusion[a][b] for b in LABELS] for a in LABELS],
            "mismatches": [{"item_id": iid, "dataset_id": ds, "human": exp, "product": pred} for iid, ds, exp, pred in pairs if exp != pred],
            "predictions_source": "data/experiments/release300.json (same 300-item product run)",
        },
        "notes": "Human labels from three independent annotators (A/B/C) on the 100-item stratified blind kit; no names stored. Product predictions are the existing release300 run, not retuned on these items. Constructed key is a reference, not human ground truth.",
        "files": {"raw": [f"data/audit/human_100/audit_{name}.csv" for name in ("A", "B", "C")], "key": "data/audit/audit_key_100.json"},
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("n_items", "fleiss_kappa", "pairwise_cohen_kappa", "majority_counts", "ties")}, ensure_ascii=False, indent=2))
    print(json.dumps(report["product"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
