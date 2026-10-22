"""Tests for the command-line entry point."""
from __future__ import annotations

import pytest

from citeguard import cli
from citeguard.metadata_verify import Candidate, VerifyResult

REFS_TEXT = (
    "[1] 张三. 题名一[J]. 期刊, 2020, 31(2): 10-20.\n"
    "[2] 李四. 题名二[J]. 期刊, 2021, 65(3): 5-9.\n"
)


def _fake_verify_many(refs, progress=True, use_arxiv=True, progress_cb=None):
    return [
        VerifyResult(status="Exact", best=Candidate(source="crossref", title=r.title))
        for r in refs
    ]


def test_cli_refs_only_writes_report(tmp_path, monkeypatch, capsys):
    refs_file = tmp_path / "refs.txt"
    refs_file.write_text(REFS_TEXT, encoding="utf-8")
    monkeypatch.setattr(cli, "verify_many", _fake_verify_many)

    rc = cli.main(["--input", str(refs_file), "--refs-only", "--out", str(tmp_path / "out")])

    assert rc == 0
    for name in ("report.json", "report.md", "report.html"):
        assert (tmp_path / "out" / name).exists()
    assert "parsed 2 references" in capsys.readouterr().out


def test_cli_missing_input_returns_2(tmp_path):
    assert cli.main(["--input", str(tmp_path / "nope.txt")]) == 2


def test_cli_no_references_returns_3(tmp_path):
    refs_file = tmp_path / "short.txt"
    refs_file.write_text("短文本", encoding="utf-8")
    assert cli.main(["--input", str(refs_file), "--refs-only", "--out", str(tmp_path / "o")]) == 3


def test_cli_max_refs_limits_parsing(tmp_path, monkeypatch):
    refs_file = tmp_path / "refs.txt"
    refs_file.write_text(REFS_TEXT, encoding="utf-8")
    monkeypatch.setattr(cli, "verify_many", _fake_verify_many)

    rc = cli.main(
        ["--input", str(refs_file), "--refs-only", "--out", str(tmp_path / "out"), "--max-refs", "1"]
    )

    assert rc == 0
    import json

    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert report["stats"]["total"] == 1


def test_cli_no_verify_flag_works(tmp_path):
    refs_file = tmp_path / "refs.txt"
    refs_file.write_text(REFS_TEXT, encoding="utf-8")
    assert cli.main(["--input", str(refs_file), "--refs-only", "--no-verify", "--out", str(tmp_path / "o")]) == 0
