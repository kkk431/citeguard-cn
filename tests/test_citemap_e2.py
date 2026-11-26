"""CiteMap E2 使用层：引导、图例、全文筛选、单断言焦点与空态。

这些测试刻意不启动浏览器：模板由 Jinja2 直接渲染，交互契约用源码断点
检查；真实页面另有 1440 / 1280 截图与 JSON 记录。
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
TEMPLATE_PATH = TEMPLATES_DIR / "citemap.html"
JS_PATH = PROJECT_ROOT / "web" / "static" / "js" / "citemap.js"
CSS_PATH = PROJECT_ROOT / "web" / "static" / "css" / "citemap.css"


def _render() -> str:
    app = SimpleNamespace(version="1.7.3", state=SimpleNamespace(offline=False))
    request = SimpleNamespace(app=app)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return env.get_template("citemap.html").render(
        request=request,
        active="citemap",
        topics=[],
        current_topic="ai_education",
        payload=None,
    )


def test_three_step_guide_and_legend_are_present() -> None:
    html = _render()
    assert 'id="ctm-guide"' in html
    assert 'id="ctm-steps"' in html
    assert html.count('class="ctm-step"') == 3
    for text in ("选主题", "看断言", "打开证据"):
        assert text in html
    assert html.count("ctm-legend-key") >= 4
    for text in ("人工证据", "机器候选", "未发现证据", "全文证据"):
        assert text in html
    assert "不是证据" in html
    assert "≠ 断言为假" in html
    assert "仍属机器层" in html


def test_filter_and_focus_containers_are_present() -> None:
    html = _render()
    for element_id in (
        "ctm-fulltext-toggle",
        "ctm-filter-note",
        "ctm-claim-focus",
        "ctm-claim-focus-list",
        "ctm-focus-status",
        "ctm-focus-clear",
        "ctm-list-empty",
    ):
        assert f'id="{element_id}"' in html, element_id
    assert 'aria-pressed="false">仅全文证据' in html
    assert 'id="ctm-focus-clear" hidden' in html
    assert "点一条断言，跨论文查看支持 / 反驳证据" in html
    assert "机器候选不是人工证据" in html


def test_js_contract_for_filter_focus_and_machine_boundaries() -> None:
    source = JS_PATH.read_text(encoding="utf-8")
    for token in (
        "fulltextOnly",
        "focusClaimId",
        "function isFulltextEvidence",
        "function isMachineClaim",
        "function isHumanEvidence",
        "function filterFulltext",
        "function renderClaimFocus",
        "function renderFocusDetail",
        "function onFulltextToggle",
        "function onFocusClick",
        "ctm-fulltext-toggle",
        "ctm-claim-focus-list",
        "ctm-focus-clear",
        "机器全文候选",
        "机器原子候选",
        "未发现证据 · ≠ 断言为假",
        "dataset.layer",
        "机器候选不是人工证据",
    ):
        assert token in source, token
    assert "innerHTML" not in source
    assert "insertAdjacentHTML" not in source
    assert "document.write" not in source
    # 全文筛选只能收窄，不能把机器候选改写成人工证据。
    assert "isHumanEvidence(ev)" in source
    assert "人工示例" in source


def test_css_defines_visible_usage_layer_states() -> None:
    source = CSS_PATH.read_text(encoding="utf-8")
    for token in (
        ".ctm-steps",
        ".ctm-step",
        ".ctm-legend",
        "position: sticky",
        ".ctm-filter-note",
        ".ctm-claim-focus",
        ".ctm-claim-focus-btn",
        ".ctm-list-empty",
        ".ctm-focus-paper",
        "@media (max-width: 1180px)",
        "@media (max-width: 720px)",
        "overflow-wrap: anywhere",
    ):
        assert token in source, token
    selectors = re.findall(r"(?m)^([.#][^{]+)\{", source)
    assert selectors
    for selector in selectors:
        assert selector.strip().startswith((".citemap-", ".ctm-", "#citemap-app")), selector
