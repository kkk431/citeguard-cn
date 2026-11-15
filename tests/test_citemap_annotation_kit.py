from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from score_citemap_single_qc import score  # noqa: E402


def test_build_annotation_kit(tmp_path: Path) -> None:
    out = tmp_path / "kit"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_citemap_annotation_kit.py"),
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
    main = list(csv.DictReader((out / "main_105.csv").open(encoding="utf-8-sig")))
    qc = list(csv.DictReader((out / "qc_21.csv").open(encoding="utf-8-sig")))
    assert len(main) == 105
    assert len(qc) == 21
    assert len({r["cell_id"] for r in main}) == 105
    assert {r["cell_id"] for r in qc} <= {r["cell_id"] for r in main}
    assert all(r["decision"] == "" for r in main + qc)
    assert len({r["cell_id"] for r in qc}) == 21


def test_single_qc_scoring() -> None:
    main = {f"c{i}": ("support" if i % 2 else "partial") for i in range(21)}
    qc = dict(main)
    out = score(main, qc)
    assert out["overlap_completed"] == 21
    assert out["agreement"] == 1.0
    assert out["cohen_kappa"] == 1.0

    qc2 = dict(main)
    qc2["c0"] = "no_evidence"
    out2 = score(main, qc2)
    assert 0.0 < out2["agreement"] < 1.0
    assert out2["cohen_kappa"] is not None
    assert out2["confusion"]["partial->no_evidence"] == 1
