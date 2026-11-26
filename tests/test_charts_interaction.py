"""G3 交互契约测试：图表 hover/图例/缩放，CiteMap 悬停/过滤/缩放。

这些测试只读静态资源，校验「配置与绑定存在」而不是替代真实浏览器。
真实渲染结果由 ``docs/optimization/g3_chart_interaction.md`` 记录的
Playwright Edge 证据覆盖（1440/1280，控制台无脚本错误，105 节点 <5ms）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    path = ROOT / relative
    assert path.is_file(), f"missing asset: {relative}"
    return path.read_text(encoding="utf-8")


CHARTS_JS = _read("web/static/js/charts.js")
GRAPH_JS = _read("web/static/js/citemap_graph.js")
GRAPH_CSS = _read("web/static/css/citemap_graph.css")


def test_charts_js_binds_hover_legend_and_zoom() -> None:
    """ECharts option 必须启用悬停强调、图例多选与 Ctrl+滚轮缩放。"""
    assert "function interactions(option)" in CHARTS_JS
    assert 'entry.emphasis.focus = entry.type === "pie" ? "self" : "series"' in CHARTS_JS
    assert "entry.blur = {" in CHARTS_JS
    assert 'option.legend.selectedMode = "multiple"' in CHARTS_JS
    assert 'zoomOnMouseWheel: "ctrl"' in CHARTS_JS
    assert 'filterMode: "none"' in CHARTS_JS
    # 横向条形图的类目轴在 yAxis 上，缩放必须指向正确的轴。
    assert 'zoomAxis = "xAxisIndex"' in CHARTS_JS
    assert 'zoomAxis = "yAxisIndex"' in CHARTS_JS
    assert "zoom[zoomAxis] = 0" in CHARTS_JS


def test_charts_js_hint_and_double_click_reset() -> None:
    """提示文案与双击重置必须同时存在，且不依赖 report.js。"""
    assert 'parts.push("Ctrl+滚轮缩放")' in CHARTS_JS
    assert "cg-chart-hint" in CHARTS_JS
    assert "function ensureHint(el, option)" in CHARTS_JS
    assert "chart.on(\"dblclick\", function () { resetZoom(chart, option); })" in CHARTS_JS
    assert 'chart.dispatchAction({ type: "dataZoom", start: 0, end: 100 })' in CHARTS_JS
    assert "chart.__cgBound" in CHARTS_JS


def test_charts_js_keeps_public_surface_and_no_remote_deps() -> None:
    """draw/refresh/resize 等原有入口不变，且不引入 CDN。"""
    for token in (
        "window.CGCharts = {",
        "mount: mount",
        "refresh: refresh",
        "resize: resize",
        "tokens: tokens",
    ):
        assert token in CHARTS_JS
    for remote in ("cdn.", "unpkg", "jsdelivr", "cdnjs"):
        assert remote not in CHARTS_JS.lower()


def test_citemap_graph_has_zoom_pan_and_legend_filter() -> None:
    """SVG 地图必须支持缩放、平移、双击重置和点击图例过滤。"""
    for token in (
        "const ZOOM_MIN = 0.55;",
        "const ZOOM_MAX = 2.5;",
        'svg.addEventListener("wheel", onWheel, { passive: false })',
        'svg.addEventListener("dblclick", onDoubleClick)',
        "function zoomAt(factor, clientX, clientY)",
        "function resetView()",
        "function toggleFilter(level)",
        'key.setAttribute("aria-pressed", state.filters[level] ? "true" : "false")',
        "function wireLegend()",
        "function applyFilters()",
        'path.classList.toggle("is-filtered", state.filters[level] === false)',
    ):
        assert token in GRAPH_JS


def test_citemap_graph_hover_highlights_connected_cluster() -> None:
    """悬停要同时点亮节点与相邻边/对端节点，而不是只加 CSS hover。"""
    for token in (
        "function hoverNode(node)",
        "function hoverEdge(path)",
        "state.adjacency",
        'svg.classList.add("is-hovering")',
        'svg.classList.remove("is-hovering")',
        "setHot(node, true)",
        "setHot(path, true)",
    ):
        assert token in GRAPH_JS


def test_citemap_graph_reports_render_time_and_105_node_benchmark() -> None:
    """真实渲染耗时写入 dataset，105 节点基准必须标明 synthetic。"""
    for token in (
        "state.renderMs",
        'panel.dataset.renderMs = state.renderMs.toFixed(2)',
        'svg.dataset.renderMs = state.renderMs.toFixed(2)',
        '用时 " + state.renderMs.toFixed(1) + " ms',
        "function buildSyntheticGraph(count)",
        "function benchmark(count)",
        "synthetic: true",
        "render_ms:",
        "window.CGMapGraph = {",
        "benchmark: benchmark",
        "resetView: resetView",
    ):
        assert token in GRAPH_JS


def test_citemap_graph_preserves_detail_open_behavior() -> None:
    """新增交互不能破坏原有「点击看证据原文」。"""
    for token in (
        "function selectPaper(paper)",
        "function selectEdge(edge)",
        "ctm-graph-detail",
        "bindNode(group, function () { selectPaper(paper); })",
    ):
        assert token in GRAPH_JS


def test_citemap_graph_css_defines_interaction_states() -> None:
    """CSS 需覆盖工具栏、提示、过滤、高亮与 reduced-motion。"""
    for token in (
        ".ctm-graph-tools {",
        ".ctm-graph-tool {",
        ".ctm-graph-zoom {",
        ".ctm-graph-hint {",
        ".ctm-graph-key.is-off {",
        ".ctm-edge.is-filtered {",
        ".ctm-edge.is-hot {",
        ".ctm-node.is-hot .ctm-node-box {",
        ".ctm-graph-svg.is-hovering .ctm-edge:not(.is-hot)",
        "touch-action: none;",
        "@media (prefers-reduced-motion: reduce)",
    ):
        assert token in GRAPH_CSS
