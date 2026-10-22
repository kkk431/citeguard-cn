"""Tests for scripts/package_deliverable.py (clean archive rules)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from helpers import ROOT

_SCRIPT = ROOT / "scripts" / "package_deliverable.py"
_spec = importlib.util.spec_from_file_location("package_deliverable", _SCRIPT)
packaging = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(packaging)


def _make_tree(root: Path) -> None:
    files = {
        "README.md": "# demo",
        ".env": "DEEPSEEK_API_KEY=sk-secret",
        ".env.example": "DEEPSEEK_API_KEY=",
        "src/citeguard/__init__.py": "",
        "src/citeguard/__pycache__/mod.cpython-312.pyc": "junk",
        "tests/test_something.py": "def test(): pass",
        "data/citebench_cn/results.json": "{}",
        "data/citebench_cn/cache/abc.json": "{}",
        "data/jobs/job1.json": "{}",
        "data/cache/x.json": "{}",
        "data/uploads/u.txt": "secret paper",
        "data/experiments/cache_e4/page.json": "{}",
        "data/experiments/manual_cache/page.json": "{}",
        "dist/old.zip": "zip",
        ".pylibs/requests/__init__.py": "",
        ".git/config": "gitconfig",
        "debug.log": "log",
        "root_mod.pyc": "pyc",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.mark.parametrize(
    "rel, excluded",
    [
        (".env", True),
        (".env.example", False),
        ("data/jobs/abc.json", True),
        ("data/cache/abc.json", True),
        ("data/uploads/paper.pdf", True),
        ("data/citebench_cn/results.json", False),
        ("data/citebench_cn/cache/x.json", True),
        ("src/citeguard/__pycache__/m.pyc", True),
        ("src/citeguard/__init__.py", False),
        (".pylibs/six.py", True),
        ("dist/pkg.zip", True),
        ("app.log", True),
        (".git/HEAD", True),
        ("tests/test_a.py", False),
    ],
)
def test_should_exclude_matrix(rel, excluded):
    assert packaging.should_exclude(rel) is excluded


def test_collect_files_skips_runtime_and_secrets(tmp_path):
    _make_tree(tmp_path)

    rels = {rel for _abs, rel in packaging.collect_files(tmp_path)}

    assert "README.md" in rels
    assert ".env.example" in rels
    assert "src/citeguard/__init__.py" in rels
    assert "data/citebench_cn/results.json" in rels
    assert ".env" not in rels
    assert not any(rel.startswith("data/jobs/") for rel in rels)
    assert not any(rel.startswith("data/cache/") for rel in rels)
    assert not any(rel.startswith("data/uploads/") for rel in rels)
    assert not any("__pycache__" in rel for rel in rels)
    assert not any(rel.startswith(".pylibs/") for rel in rels)
    assert not any(rel.startswith("dist/") for rel in rels)
    assert not any("cache" in rel for rel in rels)
    assert not any(rel.endswith(".log") or rel.endswith(".pyc") for rel in rels)


def test_build_zip_writes_clean_archive(tmp_path, capsys):
    project = tmp_path / "mini"
    _make_tree(project)

    result = packaging.build_zip(root=project, out_dir=tmp_path / "dist", name="demo.zip")

    assert result["zip_path"].exists()
    assert result["zip_path"].name == "demo.zip"
    assert result["zip_size"] > 0
    assert len(result["sha256"]) == 64

    import zipfile

    with zipfile.ZipFile(result["zip_path"]) as zf:
        names = set(zf.namelist())
    assert "mini/README.md" in names
    assert "mini/.env.example" in names
    assert "mini/data/citebench_cn/results.json" in names
    assert "mini/.env" not in names
    assert not any("data/jobs" in name or "data/cache" in name or "data/uploads" in name for name in names)
    assert not any("__pycache__" in name or name.endswith(".pyc") or name.endswith(".log") for name in names)

    out = capsys.readouterr().out
    assert "files:" in out
    assert "total uncompressed" in out
    assert "sha256" in out


def test_build_zip_refuses_empty_tree(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RuntimeError):
        packaging.build_zip(root=empty, out_dir=tmp_path / "dist", name="x.zip", print_manifest=False)


def test_main_quiet_mode(tmp_path, capsys):
    _make_tree(tmp_path)

    rc = packaging.main(
        ["--root", str(tmp_path), "--out", str(tmp_path / "dist"), "--name", "q.zip", "--quiet"]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "wrote" in out
    assert (tmp_path / "dist" / "q.zip").exists()
