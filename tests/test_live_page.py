"""CiteGuard Live 产品内试用页：模板渲染、静态资源与路由测试。

路由本身由 ``web/app.py`` 提供；本文件同时做 Jinja2 直接渲染（不依赖网络）
和 TestClient 页面断言，避免页面 DOM id 与路由接入脱节。
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
TEMPLATE_PATH = TEMPLATES_DIR / "live.html"
JS_PATH = STATIC_DIR / "js" / "live.js"
CSS_PATH = STATIC_DIR / "css" / "live.css"

CORE_IDS = [
    "live-claim",
    "live-count",
    "live-page-title",
    "live-page-url",
    "live-btn",
    "live-result",
    "live-placeholder",
    "live-loading",
    "live-error",
    "live-error-msg",
    "live-retry",
    "live-output",
    "live-label",
    "live-confidence-text",
    "live-meter",
    "live-confidence-bar",
    "live-reason",
    "live-evidence",
    "live-evidence-title",
    "live-quote",
    "live-candidate-count",
    "live-candidates",
]


def _request(version: str = "1.7.3", offline: bool = False) -> SimpleNamespace:
    app = SimpleNamespace(version=version, state=SimpleNamespace(offline=offline))
    return SimpleNamespace(app=app)


def _render(**context: object) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    defaults = {"request": _request(), "active": "live"}
    defaults.update(context)
    return env.get_template("live.html").render(**defaults)


@pytest.fixture
def client(isolated_project):
    from fastapi.testclient import TestClient

    import web.app as webapp

    return TestClient(webapp.app)


def test_route_serves_live_page(client) -> None:
    response = client.get("/live")
    assert response.status_code == 200
    html = response.text
    assert "live-claim" in html
    assert "live-result" in html
    assert "section-tabs" in html
    assert "Live 单句核验" in html
    assert 'aria-current="page"' in html


def test_route_serves_local_static_assets(client) -> None:
    for path in ("/static/css/live.css", "/static/js/live.js"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text.strip(), path


def test_template_extends_base_layout() -> None:
    html = _render()
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'class="rail"' in html
    assert '<main id="main">' in html
    assert "<title>Live 单句核验" in html
    assert "引证卫士 CiteGuard" in html


def test_template_renders_core_containers() -> None:
    html = _render()
    for element_id in CORE_IDS:
        assert f'id="{element_id}"' in html, element_id
    assert html.count('id="live-claim"') == 1
    assert html.count('id="live-result"') == 1


def test_section_tabs_are_tool_group() -> None:
    html = _render()
    assert "section-tabs" in html
    for href in ("/figure", "/compare", "/discover", "/citemap", "/live"):
        assert f'href="{href}"' in html, href
    assert "图表核验" in html
    assert "多篇对比" in html
    assert "文献发现" in html
    assert "CiteMap" in html
    assert "Live 单句核验" in html
    assert html.count('class="section-tab on"') == 1


def test_empty_result_explains_four_labels() -> None:
    html = _render()
    for label in ("支持", "部分支持", "矛盾", "无证据"):
        assert label in html
    assert "不是“假”" in html
    assert "四档结果怎么看" in html
    assert "置信度" in html


def test_scope_and_boundary_copy() -> None:
    html = _render()
    assert "检索 OpenAlex/Crossref 摘要，不读全文；证据句逐字来自摘要" in html
    assert "不是事实核查" in html
    assert "不读全文" in html
    assert "不做事实核查" in html
    assert "逐字" in html


def test_optional_context_is_collapsed_in_details() -> None:
    html = _render()
    assert "<details" in html
    assert 'for="live-page-title"' in html
    assert 'for="live-page-url"' in html
    assert 'maxlength="300"' in html
    assert 'maxlength="2048"' in html
    assert 'maxlength="500"' in html


def test_three_examples_are_present() -> None:
    html = _render()
    examples = re.findall(r'class="live-example"', html)
    assert len(examples) == 3
    assert html.count("data-claim=") == 3
    assert "AI 教育" in html
    assert "医学影像" in html
    assert "公平性" in html


def test_page_has_no_external_cdn() -> None:
    html = _render()
    assert not re.search(r'<script[^>]+src="https?://', html, re.I)
    assert not re.search(r'<link[^>]+href="https?://', html, re.I)
    for path in (JS_PATH, CSS_PATH):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for marker in ("cdn.", "unpkg", "jsdelivr", "fonts.googleapis", "cdnjs"):
            assert marker not in lowered, (path.name, marker)
    assert "/static/css/live.css" in html
    assert "/static/js/live.js" in html


def test_js_contract_and_safety() -> None:
    js = JS_PATH.read_text(encoding="utf-8")
    assert 'const API = "/api/live/check"' in js
    assert 'method: "POST"' in js
    assert "claim: claim" in js
    assert "page_title: pageTitle" in js
    assert "page_url: pageUrl" in js
    assert "textContent" in js
    assert "innerHTML" not in js
    assert "event.ctrlKey || event.metaKey" in js
    assert "MAX_CANDIDATES = 5" in js
    assert ".sort(" in js
    assert 'fetch(API' in js
    assert 'response.status' in js


def test_css_is_scoped_and_uses_theme_variables() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    for var in ("--surface", "--line", "--muted", "--accent"):
        assert f"var({var}" in css, var
    assert ":root" not in css
    assert "body.theme-light" not in css
    assert "url(http" not in css
    assert ".live-page" in css
    assert "@media (max-width: 1020px)" in css
    assert "@media (max-width: 720px)" in css
