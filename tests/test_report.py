"""Tests for report assembly and rendering (JSON / Markdown / HTML)."""
from __future__ import annotations

import json

from citeguard.gbt7714 import ComplianceResult, Issue
from citeguard.metadata_verify import Candidate, VerifyResult
from citeguard.reference_parser import parse_intext_citations, parse_reference
from citeguard.report import build_report, render_html, render_markdown, save_report

REF = parse_reference(
    "[1] 张三. 题名[J]. 期刊, 2020, 31(2): 10-20. DOI: 10.1234/x."
)
BODY = "正文引用[1]。"
INLINE = parse_intext_citations(BODY)


def _verified(status: str, url: str = "https://example.org/evidence") -> VerifyResult:
    return VerifyResult(
        status=status,
        best=Candidate(source="crossref", title=REF.title, doi=REF.doi, url=url),
        title_sim=1.0,
        year_match=True,
        author_match=1.0,
        doi_status="resolved",
    )


def _report(verify=None, compliance=None, support=None):
    return build_report(
        "paper.txt",
        BODY,
        [REF],
        verify if verify is not None else [_verified("Exact")],
        compliance if compliance is not None else [ComplianceResult(score=88)],
        INLINE,
        support,
    )


def test_build_report_stats_and_structure():
    report = _report()
    stats = report["stats"]
    assert stats["total"] == 1
    assert stats["Exact"] == 1
    assert stats["Minor"] == stats["Major"] == stats["Unknown"] == 0
    assert stats["intext_citations"] == 1
    assert stats["avg_compliance"] == 88
    assert stats["risk_index"] == 0.0
    assert report["input"] == "paper.txt"
    assert report["disclaimer"]
    item = report["references"][0]
    assert item["index"] == 1
    assert item["parsed"]["title"] == REF.title
    assert item["verify"]["status"] == "Exact"
    assert item["compliance"]["score"] == 88


def test_build_report_risk_index_counts_minor_half():
    report = _report(verify=[_verified("Major")], compliance=[ComplianceResult(score=100)])
    assert report["stats"]["Major"] == 1
    assert report["stats"]["risk_index"] == 100.0


def test_build_report_support_counts():
    report = _report(support=[{"label": "partial"}])
    assert report["stats"]["support"]["partial"] == 1
    assert report["stats"]["support"]["not_checked"] == 0

    report_none = _report(support=[None])
    assert report_none["stats"]["support"]["not_checked"] == 1


def test_review_summary_clean_report_is_ok():
    review = _report()["review_summary"]
    assert review["level"] == "ok"
    assert "可送审" in review["decision"]
    assert review["issues"] == []
    assert "不替代同行评审" in review["note"]


def test_review_summary_flags_retracted_reference():
    result = _verified("Exact")
    result.retracted = True
    review = _report(verify=[result])["review_summary"]
    assert review["level"] == "blocker"
    assert review["retracted"] == 1
    assert any(x["kind"] == "已撤稿" for x in review["issues"])


def test_review_summary_flags_major_match():
    review = _report(verify=[_verified("Major")])["review_summary"]
    assert review["level"] == "blocker"
    assert review["blockers"] >= 1
    assert "修改" in review["decision"]


def test_review_summary_flags_uncited_number():
    report = build_report(
        "paper.txt",
        BODY,
        [REF],
        [_verified("Exact")],
        [ComplianceResult(score=100)],
        [],
        citation_consistency={
            "numeric_style": True,
            "citations": 0,
            "distinct_numbers": 0,
            "missing_numbers": [],
            "uncited_numbers": [1],
            "order_inversions": 0,
            "note": "",
        },
    )
    review = report["review_summary"]
    assert review["level"] == "minor"
    assert any(x["kind"] == "未被引用" for x in review["issues"])


def test_review_summary_exported_in_markdown_and_html():
    report = _report(verify=[_verified("Major")])
    md = render_markdown(report)
    page = render_html(report)
    assert "审稿视角" in md and "建议修改" in md
    assert "审稿视角" in page and "建议修改" in page


def test_markdown_verdict_mentions_contradictions():
    md = render_markdown(_report(support=[{"label": "contradict"}]))
    assert "矛盾" in md
    html = render_html(_report(support=[{"label": "contradict"}]))
    assert "矛盾" in html


def test_render_markdown_contains_table_rows():
    md = render_markdown(_report())
    assert md.startswith("# 引证卫士 CiteGuard-CN")
    assert "| 1 |" in md
    assert "真实且元数据一致" in md
    assert "https://example.org/evidence" in md


def test_render_html_escapes_untrusted_text():
    ref = parse_reference("[1] <script>alert(1)</script>. 题名[J]. 期刊, 2020.")
    report = build_report(
        "<img src=x onerror=alert(1)>",
        BODY,
        [ref],
        [_verified("Exact")],
        [ComplianceResult(score=90, issues=[Issue("error", "title", "<b>bad</b>")])],
        INLINE,
    )
    page = render_html(report)
    assert "&lt;script&gt;" in page
    assert "&lt;img" in page
    assert "<script>alert(1)</script>" not in page
    assert "&lt;b&gt;bad&lt;/b&gt;" in page


def test_render_html_contains_status_badge():
    page = render_html(_report(verify=[_verified("Major")]))
    assert "疑似虚构或错配" in page
    assert 'href="https://example.org/evidence"' in page


def test_save_report_writes_all_formats(tmp_path):
    report = _report()
    paths = save_report(report, tmp_path / "out")

    for fmt in ("json", "md", "html"):
        assert (tmp_path / "out" / f"report.{fmt}").exists()
    refs_path = tmp_path / "out" / "report.refs.txt"
    assert refs_path.exists()
    refs_text = refs_path.read_text(encoding="utf-8")
    assert refs_text.startswith("[1] 张三. 题名[J].")
    assert json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))["stats"]["total"] == 1
    assert "# 引证卫士" in (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "<!doctype html>" in (tmp_path / "out" / "report.html").read_text(encoding="utf-8")
    assert set(paths) == {"json", "md", "html", "refs"}


def test_report_contains_formatted_reference_list():
    report = _report()

    assert report["formatted_reference_list"][0]["index"] == 1
    assert report["formatted_reference_list"][0]["entry"].startswith("张三. 题名[J].")
    md = render_markdown(report)
    assert "GB/T 7714-2025 参考文献表" in md
    assert "[1] 张三. 题名[J]." in md
    html = render_html(report)
    assert "GB/T 7714-2025 参考文献表（按原文重排）" in html


def test_empty_reference_list_report():
    report = build_report("empty.txt", "", [], [], [], [])
    assert report["stats"]["total"] == 0
    assert report["stats"]["risk_index"] == 0.0
    assert report["references"] == []
