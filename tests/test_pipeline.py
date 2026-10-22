"""Tests for the shared analysis pipeline (metadata verification mocked)."""
from __future__ import annotations

import json

import pytest

from citeguard import pipeline
from citeguard.metadata_verify import Candidate, VerifyResult

TEXT = (
    "本文讨论引文核验[1]。\n\n"
    "## 参考文献\n"
    "[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/x.\n"
)


def _fake_verify_many(refs, progress_cb=None, **kwargs):
    if progress_cb:
        for i in range(1, len(refs) + 1):
            progress_cb(i, len(refs))
    return [VerifyResult(status="Exact", best=Candidate(source="crossref", title=refs[0].title)) for _ in refs]


def test_run_job_from_text(monkeypatch, isolated_project):
    monkeypatch.setattr(pipeline, "verify_many", _fake_verify_many)

    report = pipeline.run_job("jobtext", text=TEXT)

    assert report["job_id"] == "jobtext"
    assert report["stats"]["total"] == 1
    assert report["stats"]["Exact"] == 1
    assert report["stats"]["intext_citations"] == 1
    assert report["stats"]["support"]["not_checked"] == 1  # no API key -> degraded
    out_dir = isolated_project / "jobs" / "jobtext"
    for name in ("report.json", "report.md", "report.html"):
        assert (out_dir / name).exists()
    assert json.loads((out_dir / "report.json").read_text(encoding="utf-8"))["job_id"] == "jobtext"


def test_run_job_from_file_deletes_upload(monkeypatch, isolated_project, tmp_path):
    monkeypatch.setattr(pipeline, "verify_many", _fake_verify_many)
    upload = tmp_path / "paper.txt"
    upload.write_text(TEXT, encoding="utf-8")

    report = pipeline.run_job("jobfile", file_path=str(upload))

    assert report["input"] == "paper.txt"
    assert not upload.exists()  # privacy: uploaded paper is not retained


def test_run_job_rejects_empty_text(isolated_project):
    with pytest.raises(ValueError):
        pipeline.run_job("empty", text="   ")


def test_run_job_rejects_unparseable_references(isolated_project):
    with pytest.raises(ValueError):
        pipeline.run_job("norefs", text="短文本")
