"""D3/D4 report UI contract: readable diffs and scoped exports."""

from __future__ import annotations

from pathlib import Path

from citeguard.annotate import annotation_plan, needs_annotation

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "web" / "templates" / "report.html"
REPORT_JS = ROOT / "web" / "static" / "js" / "report.js"
DIFF_CSS = ROOT / "web" / "static" / "css" / "report_diff.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _js_has(js: str, text: str) -> bool:
    """JS may store Chinese as literal text or as ``\\uXXXX`` escapes."""
    if text in js:
        return True
    escaped = "".join(ch if ord(ch) < 128 else "\\u%04x" % ord(ch) for ch in text)
    return escaped in js


def _ref(*, index: int = 1, status: str = "Exact", support: str = "", issue: bool = False) -> dict:
    return {
        "index": index,
        "raw": f"[{index}] ZHANG San. A study of citation practice[J]. Journal of Tests, 2020, 12(3): 45-50.",
        "parsed": {"title": "A study of citation practice", "doc_type": "J", "year": 2020},
        "verify": {"status": status},
        "support": {"label": support},
        "compliance": {"issues": [{"level": "error", "field": "doi", "message": "缺少 DOI"}] if issue else []},
    }


def test_report_template_wires_diff_styles_and_export_scope():
    html = _read(TEMPLATE)

    assert 'href="/static/css/report_diff.css' in html
    assert 'id="diff-result" role="region" aria-live="polite"' in html
    assert 'id="diff-help"' in html
    assert 'id="export-scope"' in html
    assert '<option value="problems">' in html
    assert '<option value="fixed">' in html
    assert '<option value="all">' in html
    assert 'id="annotated-help"' in html
    assert "未映射" in html


def test_report_js_renders_field_level_diff_and_resolved_counts():
    js = _read(REPORT_JS)

    assert 'resolved: "\\u5df2\\u89e3\\u51b3"' in js
    assert "s.resolved != null ? s.resolved : s.fixed" in js
    assert 'class="diff-fields"' in js
    assert 'class="diff-old"' in js
    assert 'class="diff-new"' in js
    assert 'class="diff-arrow"' in js
    assert "item.fixed" in js and "item.new" in js and "item.still" in js
    assert 'class="diff-item diff-kind-' in js
    assert "first.focus({ preventScroll: true })" in js


def test_report_js_explains_empty_diff_and_keyboard_path():
    js = _read(REPORT_JS)

    assert _js_has(js, "两份报告没有可见差异")
    assert _js_has(js, "差异只比较已保存的报告字段")
    assert _js_has(js, "用 Tab 选择差异条目")
    assert _js_has(js, "请先选择一份旧报告")
    assert _js_has(js, "下一步：确认旧报告仍存在")


def test_report_js_scopes_csv_and_gives_export_failure_next_step():
    js = _read(REPORT_JS)

    assert "function isProblemItem" in js
    assert "function isFixedItem" in js
    assert "function exportScope" in js
    assert "function exportFailure" in js
    assert "function triageFor" in js
    assert "|| triageFor(item)" in js
    assert "EXPORT_SCOPE_LABELS" in js
    assert _js_has(js, "仅已修条目")
    assert _js_has(js, "当前范围")
    assert _js_has(js, "请切换范围")
    assert _js_has(js, "CSV 导出失败")


def test_report_diff_css_is_responsive_and_prevents_overflow():
    css = _read(DIFF_CSS)

    assert ".diff-item > summary" in css
    assert "overflow-wrap: anywhere" in css
    assert "min-width: 0" in css
    assert "@media (max-width: 900px)" in css
    assert "print" in css
    assert ".export-help" in css


def test_annotation_plan_counts_only_entries_that_need_notes():
    report = {
        "references": [
            _ref(index=1, status="Exact"),
            _ref(index=2, status="Minor", issue=True),
            _ref(index=3, status="Exact", support="partial"),
            _ref(index=4, status="Major"),
        ],
        "citations": {"items": [{"key": "ZHANG 2020", "page": 1, "ref_numbers": [1]}]},
    }

    plan = annotation_plan(report)

    assert plan["references"] == 3
    assert plan["indexes"] == [2, 3, 4]
    assert plan["citations"] == 1
    assert "未映射" in plan["note"]
    assert needs_annotation(report["references"][0]) is False
    assert needs_annotation(report["references"][2]) is True
