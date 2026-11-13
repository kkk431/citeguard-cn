"""CiteMap 主题页：模板渲染、静态资源与接口契约测试。

这些测试不依赖 FastAPI 路由，直接用 Jinja2 渲染模板；路由由队长接入后，
可用同一组 DOM id / 文案做端到端断言。
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

jinja2 = pytest.importorskip("jinja2")
from jinja2 import Environment, FileSystemLoader  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"
STATIC_DIR = PROJECT_ROOT / "web" / "static"
TEMPLATE_PATH = TEMPLATES_DIR / "citemap.html"
JS_PATH = STATIC_DIR / "js" / "citemap.js"
CSS_PATH = STATIC_DIR / "css" / "citemap.css"

CORE_IDS = [
    "citemap-app",
    "ctm-topic-switch",
    "ctm-status",
    "ctm-loading",
    "ctm-error",
    "ctm-error-msg",
    "ctm-retry",
    "ctm-empty",
    "ctm-empty-msg",
    "ctm-layout",
    "ctm-topic-title",
    "ctm-topic-question",
    "ctm-topic-stats",
    "ctm-paper-list",
    "ctm-paper-count",
    "ctm-detail",
    "ctm-detail-empty",
    "ctm-detail-body",
]


def _request(version: str = "1.7.3", offline: bool = False) -> SimpleNamespace:
    app = SimpleNamespace(version=version, state=SimpleNamespace(offline=offline))
    return SimpleNamespace(app=app)


def _render(**context: object) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    defaults = {
        "request": _request(),
        "active": "",
        "topics": [],
        "current_topic": "",
        "payload": None,
    }
    defaults.update(context)
    return env.get_template("citemap.html").render(**defaults)


def test_template_renders_with_base_layout() -> None:
    html = _render(current_topic="ai_education")
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'class="rail"' in html
    assert '<main id="main">' in html
    assert "<title>CiteMap · 证据地图" in html


def test_template_renders_core_containers_and_copy() -> None:
    html = _render(current_topic="ai_education")
    for element_id in CORE_IDS:
        assert f'id="{element_id}"' in html, element_id

    assert "CiteMap · 证据地图" in html
    assert "2 个主题" in html
    assert "30 篇开放论文" in html
    assert "10 条人工示例" in html
    assert "不是全量结论" in html
    assert "verified=false" in html
    assert "开放获取" in html


def test_template_topic_switch_and_initial_topic() -> None:
    html = _render(current_topic="medical_imaging")
    assert 'id="citemap-app"' in html
    assert 'data-topic="medical_imaging"' in html
    assert 'data-topic-id="ai_education"' in html
    assert 'data-topic-id="medical_imaging"' in html
    assert "AI 教育" in html
    assert "医学影像" in html
    assert html.count('aria-pressed="true"') == 1

    empty = _render()
    assert 'data-topic=""' in empty
    assert empty.count('aria-pressed="true"') == 0


def test_template_uses_payload_topic_when_current_topic_missing() -> None:
    html = _render(payload={"topic": {"topic_id": "medical_imaging"}})
    assert 'data-topic="medical_imaging"' in html


def test_template_uses_topics_context_for_switch_and_default() -> None:
    topics = [
        {"topic_id": "medical_imaging", "name_zh": "医学影像"},
        {"topic_id": "ai_education", "name_zh": "AI 教育"},
    ]
    html = _render(topics=topics)
    assert 'data-topic="medical_imaging"' in html
    assert 'data-topic-id="medical_imaging"' in html
    assert 'data-topic-id="ai_education"' in html
    assert html.count('aria-pressed="true"') == 1
    assert html.index('data-topic-id="medical_imaging"') < html.index('data-topic-id="ai_education"')


def test_template_escapes_initial_topic() -> None:
    html = _render(current_topic='"><script>alert(1)</script>')
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)" in html


def test_template_states_are_present() -> None:
    html = _render(current_topic="ai_education")
    assert re.search(r'id="ctm-error"[^>]*\bhidden\b', html)
    assert re.search(r'id="ctm-empty"[^>]*\bhidden\b', html)
    assert re.search(r'id="ctm-layout"[^>]*\bhidden\b', html)
    assert re.search(r'id="ctm-detail-body"[^>]*\bhidden\b', html)
    assert 'id="ctm-loading"' in html
    assert 'id="ctm-retry"' in html
    assert "主题加载失败" in html


def test_template_assets_mount_after_base_scripts() -> None:
    html = _render(current_topic="ai_education")
    assert "/static/css/citemap.css?v=1.7.3" in html
    assert "/static/js/citemap.js?v=1.7.3" in html
    assert html.index("citemap.js") > html.index("/static/js/app.js")
    assert 'src="/static/js/citemap.js?v=1.7.3" defer' in html


def test_template_ids_are_unique() -> None:
    html = _render(current_topic="ai_education")
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))


def test_static_files_exist() -> None:
    for path in (TEMPLATE_PATH, JS_PATH, CSS_PATH):
        assert path.is_file(), path
        assert path.stat().st_size > 0, path


def test_js_uses_citemap_api_and_url_sync() -> None:
    source = JS_PATH.read_text(encoding="utf-8")
    assert '(function () {' in source
    assert '"use strict";' in source
    assert '"/api/citemap/topics"' in source
    assert '"/api/citemap/" + encodeURIComponent(topicId)' in source
    assert 'fetch(url' in source
    assert 'credentials: "same-origin"' in source
    assert "history.replaceState" in source
    assert 'url.searchParams.set("topic", topicId)' in source
    assert "window.addEventListener(\"popstate\"" in source
    assert "app.dataset.topic = topicId" in source


def test_js_is_xss_safe_and_uses_dom_text() -> None:
    source = JS_PATH.read_text(encoding="utf-8")
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "insertAdjacentHTML" not in source
    assert "document.write" not in source
    assert "eval(" not in source
    assert "safeHref" in source
    assert "encodeURIComponent" in source


def test_js_renders_required_paper_and_evidence_fields() -> None:
    source = JS_PATH.read_text(encoding="utf-8")
    for field in (
        "paper.title",
        "paper.year",
        "paper.venue",
        "paper.license",
        "paper.doi",
        "paper.cn_affiliated",
        "paper.oa_url",
        "paper.authors",
    ):
        assert field in source, field

    for field in (
        "ev.quote",
        "ev.locator",
        "ev.stance",
        "ev.confidence",
        "ev.method",
        "ev.sample",
        "ev.summary",
        "ev.verified",
        "gap.description",
        "gap.related_claim_ids",
        "gap.rationale",
    ):
        assert field in source, field

    assert "toFixed(2)" in source
    assert "ctm-confidence" in source
    assert "人工示例" in source
    assert "仅摘要" in source


def test_js_handles_loading_empty_error_and_retry() -> None:
    source = JS_PATH.read_text(encoding="utf-8")
    assert "setView(\"loading\")" in source
    assert "setView(\"empty\")" in source
    assert "setView(\"error\")" in source
    assert "showEmpty" in source
    assert "showError" in source
    assert 'els.retry.addEventListener("click", init)' in source
    assert "aria-busy" in source
    assert "无法连接 CiteMap 接口" in source
    assert "HTTP " in source


def test_css_uses_theme_variables_and_single_column_breakpoint() -> None:
    source = CSS_PATH.read_text(encoding="utf-8")
    assert "@media (max-width: 1180px)" in source
    assert "grid-template-columns: minmax(0, 1fr);" in source
    assert "var(--surface)" in source
    assert "var(--surface-2)" in source
    assert "var(--accent)" in source
    assert "var(--ok)" in source
    assert "var(--warn)" in source
    assert "var(--bad)" in source
    assert "#citemap-app [hidden]" in source
    assert "prefers-reduced-motion" in source


def test_css_is_page_scoped() -> None:
    source = CSS_PATH.read_text(encoding="utf-8")
    selectors = re.findall(r"(?m)^([.#][^{]+)\{", source)
    assert selectors
    for selector in selectors:
        selector = selector.strip()
        assert selector.startswith((".citemap-", ".ctm-", "#citemap-app")), selector
