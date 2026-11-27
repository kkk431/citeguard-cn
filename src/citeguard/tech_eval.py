"""Batch-0 evaluation harness.

This module does **not** run models.  It freezes the evidence we already have
into one reproducible scorecard, so every later "improvement" can be compared
against the same numbers (and the same source files) instead of a memory of a
previous run.  New live evaluations belong in separate opt_* JSON files.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = ROOT / "data" / "experiments"


class HarnessError(RuntimeError):
    """A required frozen result file is missing or malformed."""


def _load(name: str) -> dict:
    path = EXPERIMENTS / name
    if not path.exists():
        raise HarnessError(f"missing evaluation source: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HarnessError(f"expected an object in {path}")
    return data


def _status_counts(rows: list[dict]) -> dict[str, int]:
    counts = Counter(str(r.get("status") or "Unknown") for r in rows)
    return {k: int(counts.get(k, 0)) for k in ("Exact", "Minor", "Unverified", "Unknown", "Major")}


def _constant_majority_baseline(counts: dict[str, int]) -> dict[str, float]:
    """Macro-F1 of always predicting the majority support label.

    This is the honest floor for a 4-way classifier: it makes the product's
    macro-F1 look less flattering than accuracy, which is the point.
    """
    total = sum(counts.values())
    if not total:
        return {"accuracy": 0.0, "macro_f1": 0.0, "label": ""}
    label, n = max(counts.items(), key=lambda kv: kv[1])
    # Only the predicted class has non-zero precision/recall.
    f1 = 2 * n / (total + n) if total + n else 0.0
    return {"accuracy": round(n / total, 4), "macro_f1": round(f1 / 4, 4), "label": label}


def collect(experiments: Path | None = None) -> dict[str, Any]:
    """Return one scorecard from frozen result files.

    Every section records the source file and the sample size, so a later
    reader can tell a real 409-reference result from a 60-item dev result.
    """
    global EXPERIMENTS
    old = EXPERIMENTS
    if experiments is not None:
        EXPERIMENTS = Path(experiments)
    try:
        human = _load("human_audit_100.json")
        real = _load("verify_real.json")
        library = _load("library_real.json")
        parse = _load("parse_real.json")
        cmap = _load("citemap_audit_105/agreement.json")
        fulltext = _load("citemap_atomic_fulltext_v3_summary.json")
        mutation = _load("real_mutation_eval.json")
        calibration = _load("support_calibration.json")
        replacement = _load("replacement_eval.json")
        release = _load("release300.json")
    finally:
        EXPERIMENTS = old

    human_product = human.get("product") or {}
    human_counts = {k: int(v) for k, v in (human.get("majority_counts") or {}).items()}
    real_rows = real.get("rows") or []
    real_counts = _status_counts(real_rows)
    library_summary = library.get("summary") or {}
    parse_summary = parse.get("summary") or {}
    fulltext_verdicts = fulltext.get("verdicts") or {}
    mutation_summary = mutation.get("summary") or {}
    cal100 = (calibration.get("claimsupport_100") or {})
    cal300 = (calibration.get("claimsupport_300") or {})
    repl = (replacement.get("results") or {})

    sections = {
        "support_human_100": {
            "source": "data/experiments/human_audit_100.json",
            "n": int(human.get("n_items") or 0),
            "annotators": len(human.get("annotators") or []),
            "fleiss_kappa": human.get("fleiss_kappa"),
            "accuracy": human_product.get("accuracy"),
            "macro_f1": human_product.get("macro_f1"),
            "cohen_kappa": human_product.get("cohen_kappa"),
            "mismatches": len(human_product.get("mismatches") or []),
            "constant_majority_baseline": _constant_majority_baseline(human_counts),
        },
        "support_constructed_300": {
            "source": "data/experiments/release300.json",
            "n": int(release.get("n") or 0),
            "accuracy": (release.get("metrics") or {}).get("accuracy"),
            "macro_f1": (release.get("metrics") or {}).get("macro_f1"),
            "errors": int(release.get("errors") or 0),
        },
        "real_references_409": {
            "source": "data/experiments/verify_real.json",
            "n": len(real_rows),
            "status": real_counts,
            "major_rate": round(real_counts["Major"] / len(real_rows), 4) if real_rows else None,
        },
        "local_library_409": {
            "source": "data/experiments/library_real.json",
            "n": len(library.get("rows") or []),
            "status": library_summary.get("status") or {},
            "definite_rate": library_summary.get("definite_rate"),
        },
        "parse_529": {
            "source": "data/experiments/parse_real.json",
            "papers": parse_summary.get("papers"),
            "pdf_refs": parse_summary.get("pdf_refs"),
            "clean_ratio": parse_summary.get("pdf_clean_ratio"),
        },
        "citemap_105": {
            "source": "data/experiments/citemap_audit_105/agreement.json",
            "cells": cmap.get("cells_in_key"),
            "resolved": cmap.get("cells_resolved"),
            "fleiss_kappa": cmap.get("fleiss_kappa"),
            "accuracy": (cmap.get("accuracy") or {}).get("rate"),
            "machine_evidence_precision": (cmap.get("evidence_precision") or {}).get("rate"),
        },
        "fulltext_25_of_30": {
            "source": "data/experiments/citemap_atomic_fulltext_v3_summary.json",
            "papers": fulltext.get("fulltext_papers"),
            "papers_total": fulltext.get("fulltext_total"),
            "pairs": fulltext.get("pairs"),
            "verdicts": fulltext_verdicts,
            "audited_positive_full_hits": fulltext.get("audited_positive_full_hits"),
            "audited_positive_n": fulltext.get("audited_positive_n"),
        },
        "mutation_200": {
            "source": "data/experiments/real_mutation_eval.json",
            "sample_size": mutation_summary.get("sample_size"),
            "cases": len(mutation.get("cases") or []),
            "fabricated": len(mutation.get("fabricated") or []),
            "summary": {k: mutation_summary.get(k) for k in ("catch_rate", "precision", "recall") if k in mutation_summary},
        },
        "calibration": {
            "source": "data/experiments/support_calibration.json",
            "n100": cal100.get("n"),
            "ece100": cal100.get("ece"),
            "n300": cal300.get("n"),
            "ece300": cal300.get("ece"),
        },
        "retrieval_baselines": {
            "source": "data/experiments/replacement_eval.json",
            "dataset": replacement.get("dataset"),
            "results": repl,
            "boundary": replacement.get("boundary"),
        },
    }

    # Existing model baselines (the same 60-item held-out split, except where noted).
    model_baselines = {
        "hosted_deepseek_v10": 0.9597,
        "local_qwen3_14b_v10": 0.9574,
        "local_qwen3_14b_4bit": 0.9588,
        "local_qwen3_8b_bf16": 0.8515,
        "lora_qwen3_1p7b_test60": 0.9721,
        "lora_base_qwen3_1p7b_test60": 0.4935,
        "note": "Different splits/settings are not directly comparable; see each source JSON.",
    }
    return {
        "schema": "citeguard.tech_eval.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "model_baselines": model_baselines,
        "gates": {
            "real_false_major_zero": real_counts["Major"] == 0,
            "human_n_100": sections["support_human_100"]["n"] == 100,
            "parse_clean_1_0": parse_summary.get("pdf_clean_ratio") == 1.0,
            "citemap_105_cells": cmap.get("cells_in_key") == 105,
            "fulltext_25_of_30": fulltext.get("fulltext_papers") == 25 and fulltext.get("fulltext_total") == 30,
        },
    }


def check(scorecard: dict) -> list[str]:
    """Return human-readable violations; empty means the harness is usable."""
    problems: list[str] = []
    sections = scorecard.get("sections") or {}
    required = ("support_human_100", "real_references_409", "parse_529", "citemap_105", "fulltext_25_of_30")
    for name in required:
        if not sections.get(name):
            problems.append(f"missing section {name}")
    gates = scorecard.get("gates") or {}
    for name, ok in gates.items():
        if not ok:
            problems.append(f"gate failed: {name}")
    if sections.get("real_references_409", {}).get("status", {}).get("Major") != 0:
        problems.append("real references have Major > 0")
    return problems


def to_markdown(scorecard: dict) -> str:
    lines = ["# Batch-0 评测基线", "", f"生成：{scorecard.get('generated_at', '')}", ""]
    lines += ["| 数据 | n | 关键指标 | 来源 |", "| --- | ---: | --- | --- |"]
    for name, sec in (scorecard.get("sections") or {}).items():
        n = sec.get("n") or sec.get("cells") or sec.get("pairs") or ""
        if name == "support_human_100":
            metric = f"acc={sec.get('accuracy')} macro-F1={sec.get('macro_f1')} κ={sec.get('fleiss_kappa')}"
        elif name == "real_references_409":
            metric = " / ".join(f"{k} {v}" for k, v in (sec.get("status") or {}).items())
        elif name == "parse_529":
            metric = f"clean={sec.get('clean_ratio')}"
        elif name == "citemap_105":
            metric = f"κ={sec.get('fleiss_kappa'):.4f} evidence P={sec.get('machine_evidence_precision'):.4f}"
        elif name == "fulltext_25_of_30":
            metric = f"{sec.get('papers')}/{sec.get('papers_total')} papers, {sec.get('pairs')} pairs"
        else:
            metric = "见 JSON"
        lines.append(f"| {name} | {n} | {metric} | `{sec.get('source', '')}` |")
    lines += ["", "## 门禁", ""]
    for k, v in (scorecard.get("gates") or {}).items():
        lines.append(f"- {'✅' if v else '❌'} {k}")
    return "\n".join(lines) + "\n"
