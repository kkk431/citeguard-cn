from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_evidence_matrix_is_current_and_complete():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_evidence_matrix.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "0 missing" in proc.stdout

    text = (ROOT / "docs" / "evidence_matrix.md").read_text(encoding="utf-8")
    assert text.startswith("# 对外数字 → 证据矩阵")
    assert "| 类别 | 对外说法 | 值 | 样本 | 证据 | 复现 |" in text
    assert "待补 / 不宣称" in text
    assert "100 条三人盲标" in text  # pending human audit is explicit
    assert "MISSING" not in text

    # No fabricated human numbers: pending rows never carry a kappa value.
    pending = text.split("## 待补 / 不宣称", 1)[1]
    assert "κ=" not in pending
    assert "Fleiss κ" not in pending
