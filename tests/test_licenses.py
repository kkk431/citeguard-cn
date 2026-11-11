"""许可证边界回归：核心分发不得引入 AGPL 依赖。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_requirements_exclude_pymupdf():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pymupdf" not in text
    assert "fitz" not in text


def test_dockerfile_uses_core_requirements_only():
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "requirements.txt" in dockerfile
    assert "requirements-optional-layout" not in dockerfile


def test_optional_layout_file_marks_agpl():
    text = (ROOT / "requirements-optional-layout.txt").read_text(encoding="utf-8")
    assert "pymupdf" in text.lower()
    assert "AGPL" in text


def test_license_and_evidence_docs_exist():
    for name in ("licenses.md", "evidence_index.md", "plan_national.md"):
        assert (ROOT / "docs" / name).is_file(), name
