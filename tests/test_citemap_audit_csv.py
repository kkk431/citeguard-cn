from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from score_citemap_csv import (  # noqa: E402
    cohen_kappa,
    fleiss_kappa,
    normalise_verdict,
    score,
    wilson_ci,
)


def test_build_citemap_audit_csv(tmp_path: Path) -> None:
    out = tmp_path / "audit"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_citemap_audit_csv.py"),
            "--out",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    for reviewer in ("A", "B", "C"):
        rows = list(csv.DictReader((out / f"reviewer_{reviewer}.csv").open(encoding="utf-8-sig")))
        assert len(rows) == 60
        assert all(not row["verify_verdict"] for row in rows)
    full = list(csv.DictReader((out / "full_grid_105_optional.csv").open(encoding="utf-8-sig")))
    assert len(full) == 105
    assert (out / "_organizer_only_key.csv").exists()
    key = list(csv.DictReader((out / "_organizer_only_key.csv").open(encoding="utf-8-sig")))
    assert len(key) == 165
    assert sum(row["sampled_60"] == "1" for row in key) == 60


def test_verdict_aliases_and_intervals() -> None:
    assert normalise_verdict("正确") == "correct"
    assert normalise_verdict("issue") == "issue"
    assert normalise_verdict("maybe") is None
    lo, hi = wilson_ci(9, 10)
    assert lo < 0.9 < hi
    assert 0.0 <= lo <= hi <= 1.0


def test_kappa_helpers() -> None:
    assert cohen_kappa(["correct", "issue", "correct"], ["correct", "issue", "issue"]) is not None
    perfect = fleiss_kappa([["correct", "correct"], ["issue", "issue"]])
    assert perfect == 1.0


def test_score_two_reviewers() -> None:
    key = {
        "c1": {"cell_kind": "机器证据", "topic_id": "t", "paper_id": "p", "claim_id": "q", "machine_stance": "support"},
        "c2": {"cell_kind": "无机器证据", "topic_id": "t", "paper_id": "p", "claim_id": "q", "machine_stance": ""},
        "c3": {"cell_kind": "机器证据", "topic_id": "t", "paper_id": "p", "claim_id": "q", "machine_stance": "contradict"},
    }
    a = {
        "c1": {"verify_verdict": "正确"},
        "c2": {"verify_verdict": "正确"},
        "c3": {"verify_verdict": "正确"},
    }
    b = {
        "c1": {"verify_verdict": "正确"},
        "c2": {"verify_verdict": "有问题", "issue_type": "断言错配"},
        "c3": {"verify_verdict": "跳过"},
    }
    result, disagreements, items = score(key, [a, b])
    assert result["cells_resolved"] == 2
    assert result["evidence_precision"]["n"] == 2
    assert result["evidence_precision"]["rate"] == 1.0
    assert result["no_evidence_false_positive"]["n"] == 0
    assert result["no_evidence_false_positive"]["rate"] is None
    assert len(disagreements) == 1
    assert len(items) == 3

