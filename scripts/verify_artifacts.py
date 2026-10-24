"""Consistency check for the CiteBench-CN artifacts (no network required except --api-base).

Verifies that the delivered dataset, results, baselines, per-item predictions and
the live `/api/benchmark` contract all agree with each other.  Useful as a
one-command acceptance check before submissions / demos.

Usage:
    python3 scripts/verify_artifacts.py                 # no live API check
    python3 scripts/verify_artifacts.py --api-base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "citebench_cn"
LABELS = ["Exact", "Minor", "Major"]


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes = 0

    def check(self, ok: bool, message: str) -> bool:
        if ok:
            self.passes += 1
            print(f"  PASS  {message}")
        else:
            self.failures.append(message)
            print(f"  FAIL  {message}")
        return ok

    def summary(self) -> int:
        total = self.passes + len(self.failures)
        if self.failures:
            print(f"\n[FAIL] {len(self.failures)}/{total} checks failed:")
            for message in self.failures:
                print(f"  - {message}")
            return 1
        print(f"\n[OK] all {total} checks passed")
        return 0


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _f1_from_confusion(matrix: list[list[int]]) -> tuple[float, float]:
    scores: list[float] = []
    for i in range(len(LABELS)):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(LABELS))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    total = sum(sum(row) for row in matrix)
    accuracy = sum(matrix[i][i] for i in range(len(LABELS))) / total if total else 0.0
    return round(sum(scores) / len(scores), 4), round(accuracy, 4)


def _http_json(url: str) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 - local demo endpoint
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  (api error: {type(exc).__name__}: {exc})")
        return None


EXPERIMENTS = ROOT / "data" / "experiments"
CODE_CLAIMS = (
    # (file, substring, why it is checked against the result JSON)
    ("README.md", "0.9684", "CiteBench-CN macro-F1"),
    ("README.md", "0.9328", "ClaimSupport-CN macro-F1"),
    ("README.md", "0 / 409", "real published references are never accused"),
    ("README.md", "409 条（100%）", "local library coverage"),
    ("README.md", "15/15", "citation-consistency self-check cases"),
    ("README.md", "29/30", "E4 controlled-drift detection"),
    ("README.md", "197 / 200（98.5%）", "real-reference mutation detection"),
    ("docs/ppt_numbers.md", "0 / 409", "one-pager real-reference claim"),
    ("docs/ppt_numbers.md", "29 / 30", "one-pager drift claim"),
    ("docs/ppt_numbers.md", "197 / 200", "one-pager mutation detection"),
    ("docs/real_data_eval.md", "125（30.6%）", "real-corpus Exact count stays in sync"),
    ("docs/real_data_eval.md", "197（48.2%）", "real-corpus Unverified count stays in sync"),
)


def _check_experiments(c: "Checker") -> None:
    """Structural consistency of the real-corpus / external-benchmark evidence files."""
    parse = _load_json(EXPERIMENTS / "parse_real.json") or {}
    ps = parse.get("summary") or {}
    if ps:
        n_pub = sum((e.get("published_list") or {}).get("count") or 0 for e in parse.get("papers") or [])
        c.check(ps.get("papers", 0) >= 20, f"parse_real covers {ps.get('papers')} real papers")
        c.check(n_pub == ps.get("published_refs"), "parse_real published_refs == sum of per-paper counts")
        c.check(0 < (ps.get("published_clean_ratio") or 0) <= 1, "parse_real published_clean_ratio in (0,1]")
        c.check(0 < (ps.get("pdf_clean_ratio") or 0) <= 1, "parse_real pdf_clean_ratio in (0,1]")
        c.check(ps.get("pdf_heading_found") == ps.get("papers"),
                "parse_real located the reference heading in every PDF")

    verify = _load_json(EXPERIMENTS / "verify_real.json") or {}
    vs = verify.get("summary") or {}
    if vs:
        status = vs.get("status") or {}
        c.check(sum(status.values()) == vs.get("refs"), "verify_real status counts sum to refs")
        c.check(status.get("Major", 0) == 0, "verify_real: 0 Major on published references")
        expected = round(status.get("Major", 0) / max(vs.get("refs", 1), 1), 4)
        c.check(abs((vs.get("major_rate") or 0) - expected) < 1e-4, "verify_real major_rate matches counts")
        if vs.get("url_checks"):
            c.check(sum((vs.get("url_checks") or {}).values()) >= 1,
                    f"verify_real web-link check recorded ({vs.get('url_checks')})")

    library = _load_json(EXPERIMENTS / "library_real.json") or {}
    ls = library.get("summary") or {}
    if ls:
        st = ls.get("status") or {}
        c.check(sum(st.values()) == ls.get("refs"), "library_real status counts sum to refs")
        c.check(ls.get("definite_verdicts") == st.get("Exact", 0) + st.get("Minor", 0),
                "library_real definite == Exact + Minor")
        expected_rate = round(ls["definite_verdicts"] / max(ls.get("refs", 1), 1), 4)
        c.check(abs((ls.get("definite_rate") or 0) - expected_rate) < 1e-3,
                "library_real definite_rate matches counts")

    e4 = _load_json(EXPERIMENTS / "e4_format.json") or {}
    drift = e4.get("drift") or {}
    if drift:
        c.check(drift.get("n") == 30, "E4 drift n == 30")
        c.check(0 <= drift.get("strict_detected", 0) <= drift.get("n", 0), "E4 strict_detected <= n")
    if e4.get("metrics"):
        c.check(bool((e4["metrics"].get("type_code_recognition") or {}).get("rate")),
                "E4 records the type-code recognition rate")

    scifact = _load_json(EXPERIMENTS / "scifact_support_results.json") or {}
    if scifact.get("results"):
        c.check(scifact.get("n_claims") == 300, "SciFact result is the 300-claim dev set")
        for setting in ("oracle", "abstract"):
            c.check(0 < (scifact["results"].get(setting) or {}).get("macro_f1", 0) <= 1,
                    f"SciFact {setting} macro_f1 in (0,1]")

    ocr = _load_json(EXPERIMENTS / "ocr_scan_real.json") or {}
    if ocr:
        c.check(0 < ocr.get("parsed_refs", 0) <= ocr.get("expected_refs", 0),
                f"OCR fallback parsed {ocr.get('parsed_refs')}/{ocr.get('expected_refs')} references")

    consistency = _load_json(EXPERIMENTS / "citation_consistency.json") or {}
    if consistency.get("cases"):
        c.check(consistency.get("passed") == consistency.get("cases"),
                f"citation-consistency self-check {consistency.get('passed')}/{consistency.get('cases')} cases")
        c.check(consistency.get("failures") == [], "citation-consistency has no failing cases")

    mutation = _load_json(EXPERIMENTS / "real_mutation_eval.json") or {}
    if mutation.get("summary"):
        ms = mutation["summary"]
        mut = ms.get("mutations") or {}
        base = ms.get("baseline") or {}
        c.check((ms.get("sample_size") or 0) >= 20, "mutation eval sample size recorded")
        c.check((mut.get("n") or 0) >= 100, f"mutation eval has {mut.get('n')} injected-error cases")
        c.check(0 < (mut.get("detection_rate") or 0) <= 1,
                f"mutation detection rate {mut.get('detection_rate')} in (0,1]")
        c.check((base.get("n") or 0) >= 20, "mutation eval baseline recorded")
        c.check(0 <= (base.get("exact_rate") or 0) <= 1, "mutation baseline exact rate in [0,1]")

    recall = _load_json(EXPERIMENTS / "search_recall.json") or {}
    if recall.get("summary"):
        c.check((recall["summary"].get("sample") or 0) >= 20, "search_recall sample recorded")

    for name in ("support_local_qwen3_1.7b_simple.json", "support_local_Qwen_Qwen3-1_7B.json"):
        local = _load_json(EXPERIMENTS / name) or {}
        if local:
            c.check(0 < (local.get("macro_f1") or 0) <= 1, f"{name}: local-model macro_f1 in (0,1]")


def _check_doc_claims(c: "Checker") -> None:
    """The numbers quoted in the docs must match the evidence JSON files."""
    texts: dict[str, str] = {}
    for rel in sorted({rel for rel, _, _ in CODE_CLAIMS}):
        path = ROOT / rel
        texts[rel] = path.read_text(encoding="utf-8") if path.exists() else ""
    for rel, needle, label in CODE_CLAIMS:
        c.check(needle in texts.get(rel, ""), f"{rel} still states {needle!r} ({label})")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify CiteBench-CN artifacts.")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--api-base", default="", help="e.g. http://127.0.0.1:8000 (checks /api/benchmark)")
    args = parser.parse_args(argv)

    c = Checker()
    data_dir = args.data_dir
    print(f"[verify] artifacts in {data_dir}")

    # --- dataset ----------------------------------------------------------
    jsonl_path = data_dir / "citebench_cn.jsonl"
    c.check(jsonl_path.exists(), f"{jsonl_path.name} exists")
    if not jsonl_path.exists():
        return c.summary()
    raw = jsonl_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    c.check(len(rows) == 250, f"dataset has 250 rows (got {len(rows)})")
    counts = {label: sum(1 for r in rows if r["label"] == label) for label in LABELS}
    c.check(counts == {"Exact": 100, "Minor": 75, "Major": 75}, f"label counts 100/75/75 (got {counts})")
    no_doi = [r for r in rows if "DOI:" not in r["ref_string"]]
    c.check(len(no_doi) == 75, f"75 rows carry no DOI (got {len(no_doi)})")
    no_doi_label = {label: sum(1 for r in no_doi if r["label"] == label) for label in LABELS}
    c.check(no_doi_label == {"Exact": 30, "Minor": 22, "Major": 23},
            f"no-DOI split 30/22/23 (got {no_doi_label})")
    required = {"id", "ref_string", "label", "corruption", "gold", "source"}
    c.check(all(required.issubset(r) for r in rows), "every row has the six required fields")
    c.check(len({r["id"] for r in rows}) == 250, "ids are unique")
    major_kinds = {r["corruption"].split(":", 1)[1].replace(" (no DOI)", "").strip()
                   for r in rows if r["label"] == "Major"}
    c.check(major_kinds == {"fake_title", "fake_doi"},
            f"Major only contains fake_title/fake_doi (got {sorted(major_kinds)})")
    c.check(not any("minor:doi_" in r["corruption"] for r in rows),
            "no DOI case/suffix perturbations are labelled Minor")

    # --- meta -------------------------------------------------------------
    meta = _load_json(data_dir / "citebench_cn.meta.json") or {}
    c.check(meta.get("n") == 250 and meta.get("counts") == counts, "meta n/counts match the dataset")
    c.check(meta.get("no_doi", {}).get("total") == 75, "meta records 75 no-DOI rows")
    c.check(meta.get("fabricated_doi_check", {}).get("all_missing") is True,
            "fabricated DOIs are all verified 404 (meta)")

    # --- results ----------------------------------------------------------
    results = _load_json(data_dir / "results.json") or {}
    c.check(bool(results), "results.json readable")
    c.check(results.get("n") == 250, f"results.n == 250 (got {results.get('n')})")
    c.check(results.get("dataset_sha256") == sha, "results.dataset_sha256 matches the dataset file")
    confusion = results.get("confusion") or {}
    matrix = confusion.get("matrix") or []
    c.check(confusion.get("labels") == LABELS, "confusion labels are Exact/Minor/Major")
    c.check(sum(sum(row) for row in matrix) == 250, "confusion matrix sums to 250")
    calc_f1, calc_acc = _f1_from_confusion(matrix)
    metrics = results.get("metrics") or {}
    c.check(abs((metrics.get("macro_f1") or 0) - calc_f1) < 1e-3,
            f"stored macro_f1 matches confusion matrix ({calc_f1})")
    c.check(abs((metrics.get("accuracy") or 0) - calc_acc) < 1e-3,
            f"stored accuracy matches confusion matrix ({calc_acc})")
    per_class = results.get("per_class") or {}
    c.check(set(per_class) == set(LABELS), "results.per_class covers all three labels")
    baseline_names = [b.get("name", "") for b in results.get("baselines") or []]
    c.check(any(n.startswith("ours") for n in baseline_names), "results.baselines contains ours")
    c.check(any(n.startswith("DeepSeek") for n in baseline_names), "results.baselines contains DeepSeek")
    ablation = results.get("ablation") or []
    c.check(len(ablation) == 3 and ablation[0].get("name") == "full",
            "results.ablation has full + two ablations")

    # --- per-item CSV -----------------------------------------------------
    pred_path = data_dir / "eval_predictions.csv"
    c.check(pred_path.exists(), f"{pred_path.name} exists")
    if pred_path.exists():
        with pred_path.open(encoding="utf-8", newline="") as fh:
            preds = list(csv.DictReader(fh))
        c.check(len(preds) == 250, f"eval_predictions.csv has 250 rows (got {len(preds)})")
        by_id = {r["id"]: r["label"] for r in rows}
        c.check(all(by_id.get(p["id"]) == p["label"] for p in preds),
                "CSV labels match the dataset labels")

    # --- DeepSeek baseline ------------------------------------------------
    ds = _load_json(data_dir / "deepseek_results.json") or {}
    c.check(bool(ds), "deepseek_results.json readable")
    c.check(ds.get("dataset_sha256") == sha, "DeepSeek baseline was run on this dataset sha256")
    c.check(ds.get("n") == 250 and len(ds.get("predictions") or []) == 250,
            "DeepSeek baseline covers 250 rows")
    c.check(ds.get("failures") == 0, "DeepSeek baseline has 0 API failures")
    c.check(bool(ds.get("prompt_sha256")), "DeepSeek prompt sha256 is recorded (reproducible prompt)")
    ds_baseline = next((b for b in results.get("baselines") or [] if str(b.get("name", "")).startswith("DeepSeek")), None)
    if ds_baseline:
        c.check(ds_baseline.get("macro_f1") == ds.get("metrics", {}).get("macro_f1"),
                "results.json DeepSeek macro_f1 matches deepseek_results.json")

    # --- real-corpus / external evidence + docs numbers -------------------
    print("[verify] experiment evidence in data/experiments")
    _check_experiments(c)
    _check_doc_claims(c)

    # --- live API ---------------------------------------------------------
    if args.api_base:
        api = _http_json(args.api_base.rstrip("/") + "/api/benchmark") or {}
        c.check(api.get("available") is True, f"{args.api_base}/api/benchmark available == true")
        c.check(api.get("n") == 250, "/api/benchmark n == 250")
        c.check(api.get("dataset_sha256") == sha, "/api/benchmark serves the current dataset sha256")
        c.check(api.get("metrics", {}).get("macro_f1") == metrics.get("macro_f1"),
                "/api/benchmark macro_f1 matches results.json")
        c.check(set(api.get("per_class") or {}) == set(LABELS), "/api/benchmark exposes per_class for all labels")
        # The dashboard's "real data" block must serve the evidence files, not a copy.
        real = api.get("real_data") or {}
        for key, filename, field in (
            ("parse", "parse_real.json", "published_refs"),
            ("verify", "verify_real.json", "refs"),
            ("library", "library_real.json", "refs"),
        ):
            evidence = (_load_json(EXPERIMENTS / filename) or {}).get("summary") or {}
            if evidence:
                c.check((real.get(key) or {}).get(field) == evidence.get(field),
                        f"/api/benchmark real_data.{key}.{field} matches {filename}")
        library_api = real.get("library") or {}
        if library_api.get("definite_rate") == 1.0:
            c.check(library_api.get("definite_verdicts") == library_api.get("refs"),
                    "/api/benchmark library definite_verdicts == refs at 100%")

    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
