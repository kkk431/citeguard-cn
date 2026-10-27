"""Tests for the shared analysis pipeline (metadata verification mocked)."""
from __future__ import annotations

from pathlib import Path

import json
import threading
import time

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


def _refs():
    from citeguard.reference_parser import parse_reference_list

    return parse_reference_list(
        "[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20.\n"
        "[2] 李四. 另一个题名[J]. 期刊, 2021, 32(3): 5-9.\n"
    )


def test_support_skips_unreliable_title_match(monkeypatch):
    refs = _refs()
    monkeypatch.setattr(pipeline, "build_claims", lambda body, intext, refs: {r.index: "claim" for r in refs})
    monkeypatch.setattr(pipeline, "judge_available", lambda: True)
    calls = []

    def fake_judge(*args, **kwargs):
        calls.append(args)
        return {"label": "support", "confidence": 0.9, "reason": "", "evidence": ""}

    monkeypatch.setattr(pipeline, "judge_support", fake_judge)
    results = [
        # Weak Crossref hit: the abstract is probably another paper's.
        VerifyResult(
            status="Unverified",
            title_sim=0.42,
            best=Candidate(source="crossref", title="无关论文", abstract="某个摘要"),
        ),
        VerifyResult(
            status="Exact",
            title_sim=0.99,
            best=Candidate(source="crossref", title=refs[1].title, abstract="真实摘要"),
        ),
    ]

    out, meta = pipeline._judge_support("正文", [], refs, results, cap=10, step=lambda *a: None)

    assert out[0]["label"] == "not_checked"
    assert "匹配度不足" in out[0]["reason"]
    assert "0.42" in out[0]["reason"]
    assert out[1]["label"] == "support"
    assert len(calls) == 1  # only the trustworthy match was judged
    assert meta["skipped_unreliable_match"] == 1
    assert meta["judged"] == 1


def test_support_trusts_high_similarity_even_if_unverified(monkeypatch):
    refs = _refs()
    monkeypatch.setattr(pipeline, "build_claims", lambda body, intext, refs: {r.index: "claim" for r in refs})
    monkeypatch.setattr(pipeline, "judge_available", lambda: True)
    monkeypatch.setattr(
        pipeline,
        "judge_support",
        lambda *a, **k: {"label": "partial", "confidence": 0.6, "reason": "", "evidence": ""},
    )
    results = [
        VerifyResult(
            status="Unverified",
            title_sim=0.93,
            best=Candidate(source="openalex", title=refs[0].title, abstract="摘要"),
        ),
        VerifyResult(status="Unknown"),
    ]

    out, meta = pipeline._judge_support("正文", [], refs, results, cap=10, step=lambda *a: None)

    assert out[0]["label"] == "partial"
    assert out[1]["label"] == "not_checked"
    assert meta["skipped_unreliable_match"] == 1
    assert meta["judged"] == 1


def test_report_includes_citation_consistency(monkeypatch, isolated_project):
    monkeypatch.setattr(pipeline, "verify_many", _fake_verify_many)
    text = (
        "本文讨论引文核验[1]。\n\n"
        "## 参考文献\n"
        "[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20.\n"
        "[2] 李四. 另一个题名[J]. 期刊, 2021, 32(3): 5-9.\n"
    )
    report = pipeline.run_job("jobcc", text=text)
    cc = report["citation_consistency"]
    assert cc["numeric_style"] is True
    assert cc["uncited_numbers"] == [2]
    assert cc["missing_numbers"] == []


def test_support_judges_concurrently_and_keeps_order(monkeypatch):
    refs = _refs() + _refs()  # 4 refs
    monkeypatch.setattr(
        pipeline, "build_claims", lambda body, intext, refs: {r.index: "claim" for r in refs}
    )
    monkeypatch.setattr(pipeline, "judge_available", lambda: True)
    monkeypatch.setattr(pipeline.config, "SUPPORT_WORKERS", 3)

    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def fake_judge(claim, abstract, title="", doi=""):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.15)
        with lock:
            state["active"] -= 1
        return {"label": "support", "confidence": 0.9, "reason": "", "evidence": ""}

    monkeypatch.setattr(pipeline, "judge_support", fake_judge)
    results = [
        VerifyResult(
            status="Exact",
            title_sim=0.99,
            best=Candidate(source="crossref", title=r.title, abstract="摘要"),
        )
        for r in refs
    ]

    out, meta = pipeline._judge_support("正文", [], refs, results, cap=10, step=lambda *a: None)

    assert state["peak"] >= 2  # the pool actually overlapped calls
    assert meta["workers"] == 3
    assert meta["judged"] == 4
    assert [r["label"] for r in out] == ["support"] * 4
    assert [r["claim"] for r in out] == ["claim"] * 4


def test_support_cap_keeps_first_n_eligible(monkeypatch):
    refs = _refs() + _refs()  # 4 refs
    monkeypatch.setattr(
        pipeline, "build_claims", lambda body, intext, refs: {r.index: "claim" for r in refs}
    )
    monkeypatch.setattr(pipeline, "judge_available", lambda: True)
    monkeypatch.setattr(pipeline.config, "SUPPORT_WORKERS", 1)
    calls = []

    def fake_judge(claim, abstract, title="", doi=""):
        calls.append(title)
        return {"label": "partial", "confidence": 0.5, "reason": "", "evidence": ""}

    monkeypatch.setattr(pipeline, "judge_support", fake_judge)
    results = [
        VerifyResult(
            status="Exact",
            title_sim=0.99,
            best=Candidate(source="crossref", title=r.title, abstract="摘要"),
        )
        for r in refs
    ]

    out, meta = pipeline._judge_support("正文", [], refs, results, cap=2, step=lambda *a: None)

    assert len(calls) == 2
    assert meta["judged"] == 2
    assert meta["candidates"] == 4
    assert meta["skipped_by_cap"] == 2
    assert [r["label"] for r in out] == ["partial", "partial", "not_checked", "not_checked"]


def test_body_figure_claims_groups_and_caps():
    body = (
        "如图 1 所示，方法 A 的准确率高于方法 B。图 1 还显示 2025 年达到峰值。"
        "表 2 给出了各组的样本量。图 3 是整体流程图。图 4 是另一张图。"
    )
    groups = pipeline._body_figure_claims(body)
    assert [number for number, _ in groups] == ["1", "2", "3"]
    assert len(groups[0][1]) == 2
    assert groups[0][1][0].startswith("如图 1")


def test_figure_checks_are_opt_in(monkeypatch):
    text = (
        "正文提到如图 1 所示，方法有效。\n\n参考文献\n"
        "[1] 张三. 题名[J]. 期刊, 2020, 1(2): 3-4.\n"
    )
    monkeypatch.setattr(pipeline, "verify_many", lambda refs, **kw: [
        VerifyResult(status="Unknown") for _ in refs
    ])
    plain = pipeline.analyze_text(text, online=True)
    assert "figure_checks" not in plain

    called = {}

    def fake_check(body, pdf_path, step):
        called["pdf"] = pdf_path
        return [{"number": "1", "page": 2, "items": [{"claim": "方法有效", "verdict": "supported"}]}]

    monkeypatch.setattr(pipeline, "_check_body_figures", fake_check)
    report = pipeline.analyze_text(
        text, online=True, figure_checks=True, pdf_path="paper.pdf"
    )
    assert called["pdf"] == "paper.pdf"
    assert report["figure_checks"][0]["number"] == "1"


def test_offline_demo_pack(monkeypatch):
    from citeguard import config, pipeline
    from citeguard.local_library import Library, parse_library_text

    root = Path(__file__).resolve().parents[1] / "samples" / "offline_demo"
    text = (root / "paper.txt").read_text(encoding="utf-8")
    lib = Library(parse_library_text((root / "library.ris").read_text(encoding="utf-8"), "library.ris"))
    monkeypatch.setattr(config, "OFFLINE", True)
    report = pipeline.analyze_text(text, "paper.txt", online=False, library=lib)
    statuses = [r["verify"]["status"] for r in report["references"]]
    assert len(statuses) == 11
    assert statuses.count("Exact") == 10
    assert statuses[-1] == "Unknown"
    assert statuses.count("Exact") == 10
