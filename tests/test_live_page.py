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
    "live-prewarm-status",
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
    assert "/api/live/prewarm" in js
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


# ---------------------------------------------------------------------------
# t25 spike：页面参考文献列表 → [n] 映射（不联网，纯函数）
# ---------------------------------------------------------------------------

ARXIV_STYLE_HTML = """<!doctype html>
<html><head><title>Demo paper</title></head><body>
<article class="ltx_document">
<h1 class="ltx_title">Demo paper</h1>
<p>Prior work studies retrieval [1]. Several systems combine modules [2, 3] and more [4–5].</p>
<p>We follow the setup in [5].</p>
<section class="ltx_bibliography"><h2>References</h2>
<ol class="ltx_bibliography">
<li class="ltx_bibitem" id="bib.bib1"><span class="ltx_tag ltx_tag_bibitem">[1]</span><span class="ltx_bibblock">A. Alpha. <i>Alpha study</i>. 2020. doi:10.1000/alpha</span></li>
<li class="ltx_bibitem" id="bib.bib2"><span class="ltx_tag ltx_tag_bibitem">[2]</span><span class="ltx_bibblock">B. Beta. <i>Beta study</i>. 2021.</span></li>
<li class="ltx_bibitem" id="bib.bib3"><span class="ltx_tag ltx_tag_bibitem">[3]</span><span class="ltx_bibblock">C. Gamma. <i>Gamma study</i>. 2022.</span></li>
<li class="ltx_bibitem" id="bib.bib4"><span class="ltx_tag ltx_tag_bibitem">[4]</span><span class="ltx_bibblock">D. Delta. <i>Delta study</i>. 2023.</span></li>
<li class="ltx_bibitem" id="bib.bib5"><span class="ltx_tag ltx_tag_bibitem">[5]</span><span class="ltx_bibblock">E. Epsilon. <i>Epsilon study</i>. 2024.</span></li>
</ol></section>
</article></body></html>"""

GENERIC_REFERENCES_HTML = """<!doctype html>
<html><head><title>Generic page</title></head><body>
<article>
<p>We cite [1], [2] and [3] in this paragraph.</p>
<section class="references"><h2>References</h2>
<ol>
<li>3. Third source. doi:10.1000/third</li>
<li>1. First source. doi:10.1000/first</li>
<li>2. Second source. doi:10.1000/second</li>
</ol></section>
</article></body></html>"""

NO_REFERENCES_HTML = """<!doctype html>
<html><head><title>No references</title></head><body>
<article><h1>No references</h1>
<p>Claim one [1] and claim two [2] are never defined here.</p></article>
</body></html>"""


@pytest.fixture(scope="module")
def live_page():
    pytest.importorskip("readability")
    from citeguard import live_page as module

    return module


def test_arxiv_style_page_maps_every_marker(live_page) -> None:
    model = live_page.build_page_model(ARXIV_STYLE_HTML, "https://arxiv.org/html/demo")

    assert model["reference_count"] == 5
    assert model["markers_total"] == 4
    assert model["markers_mapped"] == 4
    assert model["mapped_ratio"] == 1.0
    assert model["unmapped_markers"] == []
    assert model["extractor"]["name"] == "readability-lxml"
    assert model["extractor"]["license"] == "Apache-2.0"

    first = model["samples"][0]
    assert first["marker"] == "[1]"
    assert "Alpha study" in first["references"][0]["title"]
    assert first["references"][0]["doi"] == "10.1000/alpha"

    located = live_page.locate_claim("As shown before [2].", model)
    assert located[0]["mapped"] is True
    assert "Beta study" in located[0]["references"][0]["title"]


def test_page_without_reference_list_reports_unmapped(live_page) -> None:
    model = live_page.build_page_model(NO_REFERENCES_HTML)

    assert model["reference_count"] == 0
    assert model["markers_total"] == 2
    assert model["markers_mapped"] == 0
    assert model["mapped_ratio"] == 0.0
    assert model["samples"] == []
    assert model["unmapped_markers"] == ["[1]", "[2]"]


def test_out_of_order_labels_still_map_by_number(live_page) -> None:
    model = live_page.build_page_model(GENERIC_REFERENCES_HTML)

    assert sorted(reference["index"] for reference in model["references"]) == [1, 2, 3]
    by_index = {reference["index"]: reference for reference in model["references"]}
    assert "First source" in by_index[1]["title"]
    assert "Second source" in by_index[2]["title"]
    assert "Third source" in by_index[3]["title"]

    located = live_page.locate_claim("Only the second [2] source applies.", model)
    assert located[0]["numbers"] == [2]
    assert located[0]["mapped"] is True
    assert "Second source" in located[0]["references"][0]["title"]


def test_full_width_brackets_and_lists(live_page) -> None:
    markers = live_page.find_markers("甲［1］乙【2，3】丙［4–6］丁")
    assert [marker["numbers"] for marker in markers] == [[1], [2, 3], [4, 5, 6]]

    html = """<!doctype html><html><body><article>
    <p>本文采用［1］与【2，3】两类方法。</p>
    <section class="references"><ol>
    <li>1. 文献一. 2020.</li><li>2. 文献二. 2021.</li><li>3. 文献三. 2022.</li>
    </ol></section></article></body></html>"""
    model = live_page.build_page_model(html)
    assert model["markers_total"] == 2
    assert model["markers_mapped"] == 2
    assert model["mapped_ratio"] == 1.0
    assert live_page.locate_claim("见【3】。", model)[0]["mapped"] is True


def test_missing_marker_is_reported_not_raised(live_page) -> None:
    model = live_page.build_page_model(GENERIC_REFERENCES_HTML)

    located = live_page.locate_claim("A dangling marker [9].", model)
    assert located[0]["numbers"] == [9]
    assert located[0]["mapped"] is False
    assert located[0]["references"] == []


def test_reference_matches_doi_and_title(live_page) -> None:
    reference = {"title": "Conducting realistic experiments in software engineering", "doi": ""}

    assert not live_page.reference_matches(reference, "https://doi.org/10.1109/ISESE.2002.1166921", "")
    assert live_page.reference_matches(
        {**reference, "doi": "https://doi.org/10.1109/ISESE.2002.1166921"},
        "10.1109/isese.2002.1166921",
        "",
    )
    assert live_page.reference_matches(reference, "", "Conducting realistic experiments in software engineering")
    assert not live_page.reference_matches(reference, "", "A completely different study")

def test_live_page_api_reads_allowlisted_page(client, monkeypatch) -> None:
    from citeguard import live_page

    monkeypatch.setattr(live_page, "fetch_html", lambda url, **kwargs: GENERIC_REFERENCES_HTML)
    resp = client.post("/api/live/page", json={"page_url": "https://arxiv.org/html/2401.00001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["reference_count"] == 3
    assert data["markers_total"] >= 2
    assert data["markers_mapped"] >= 2
    assert data["mapped_ratio"] == 1.0
    assert data["mapped_sources"] >= 2
    assert data["reference_sentences"] >= 0
    assert len(data["sample"]) >= 1
    assert "body_text" not in data


def test_live_page_api_rejects_other_hosts(client) -> None:
    resp = client.post("/api/live/page", json={"page_url": "https://example.com/article"})
    assert resp.status_code == 400
    assert "arXiv" in resp.json()["detail"]


def test_live_page_api_requires_url(client) -> None:
    resp = client.post("/api/live/page", json={})
    assert resp.status_code == 400


def test_redirect_guard_blocks_non_allowlisted_host(live_page) -> None:
    handler = live_page._AllowedRedirectHandler(("arxiv.org",))
    request = __import__("urllib.request", fromlist=["Request"]).Request("https://arxiv.org/html/1")
    try:
        handler.redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1/latest/meta-data")
    except RuntimeError as exc:
        assert "非白名单" in str(exc)
    else:
        raise AssertionError("redirect to a private host must be rejected")


# ---------------------------------------------------------------------------
# t27：PMC 锚点 / 作者年定位、锚点与纯文本去重、无法映射时不猜测
# ---------------------------------------------------------------------------

PMC_NUMERIC_HTML = """<!doctype html>
<html><head><title>PMC numeric demo</title></head><body>
<article>
<p>The first review <a href="#REF1">1</a> and the second review <a href="#REF2">2</a> agree.</p>
<p>A later paragraph cites the first review again <a href="#REF1">1</a>.</p>
<section id="ref-list1"><ol>
<li id="REF1">1. Sheikh H. Mission AI. 2023. doi:10.1000/ref1</li>
<li id="REF2">2. Jeblick K. Simplified radiology reports. 2024. doi:10.1000/ref2</li>
</ol></section>
</article></body></html>"""

PMC_AUTHOR_YEAR_HTML = """<!doctype html>
<html><head><title>PMC author-year demo</title></head><body>
<article>
<p>Motivation is central <a href="#B3">Annamalai et al., 2023a</a> to this design.</p>
<p>Later, (Ryan and Deci, 2020) frames the analysis.</p>
<ol class="ref-list">
<li id="B1">Ryan R. M., Deci E. L. (2020). Self-determination theory. doi:10.1000/ryan2020</li>
<li id="B2">Bhatt S. P. (2021). Teacher development. doi:10.1000/bhatt2021</li>
<li id="B3">Annamalai N., Eltahir M. E. (2023a). ChatGPT and self-determination theory. doi:10.1000/annamalai2023</li>
</ol>
</article></body></html>"""

DEDUPE_HTML = """<!doctype html>
<html><head><title>Dedupe demo</title></head><body>
<article>
<p>Anchored citation <a href="#bib.bib1">[1]</a> in one sentence.</p>
<p>Plain citation [1] in another sentence.</p>
<section class="ltx_bibliography"><ol class="ltx_bibliography">
<li class="ltx_bibitem" id="bib.bib1"><span class="ltx_tag ltx_tag_bibitem">[1]</span><span class="ltx_bibblock">A. Alpha. <i>Alpha study</i>. 2020.</span></li>
</ol></section>
</article></body></html>"""


def test_pmc_numeric_anchors_map_and_keep_marker_in_sentence(live_page) -> None:
    model = live_page.build_page_model(PMC_NUMERIC_HTML, "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/")

    assert model["reference_count"] == 2
    assert [reference["index"] for reference in model["references"]] == [1, 2]
    assert model["markers_total"] == 3
    assert model["markers_mapped"] == 3
    assert model["unmapped_markers"] == []
    assert model["reference_sentences"] >= 1

    located = live_page.locate_claim("The first review [1] and the second [2].", model)
    assert [item["numbers"] for item in located] == [[1], [2]]
    assert all(item["mapped"] for item in located)


def test_pmc_author_year_anchor_and_plain_text_resolve(live_page) -> None:
    model = live_page.build_page_model(PMC_AUTHOR_YEAR_HTML, "https://pmc.ncbi.nlm.nih.gov/articles/PMC2/")

    assert model["reference_count"] == 3
    by_index = {reference["index"]: reference for reference in model["references"]}
    assert "Ryan" in by_index[1]["raw"]
    assert "Annamalai" in by_index[3]["raw"]

    located = live_page.locate_claim(
        "Motivation is central (Annamalai et al., 2023a) and (Ryan and Deci, 2020).",
        model,
    )
    assert [item["kind"] for item in located] == ["author-year", "author-year"]
    assert all(item["mapped"] for item in located)
    assert "Annamalai" in located[0]["references"][0]["raw"]
    assert "Ryan" in located[1]["references"][0]["raw"]


def test_anchor_and_plain_marker_are_not_double_counted(live_page) -> None:
    model = live_page.build_page_model(DEDUPE_HTML)

    assert model["markers_total"] == 2
    assert model["markers_mapped"] == 2
    markers = [marker["text"] for marker in live_page.find_markers(model["body_text"])]
    assert markers == ["[1]", "[1]"]


def test_ambiguous_author_year_stays_unmapped(live_page) -> None:
    html = """<!doctype html><html><head><title>Ambiguous</title></head><body>
    <article><p>Cited as (Wang, 2020) without a suffix.</p>
    <ol class="ref-list">
    <li id="B1">Wang A. (2020a). First paper. doi:10.1000/wang-a</li>
    <li id="B2">Wang B. (2020b). Second paper. doi:10.1000/wang-b</li>
    </ol></article></body></html>"""
    model = live_page.build_page_model(html)
    located = live_page.locate_claim("Cited as (Wang, 2020).", model)
    assert located[0]["numbers"] == []
    assert located[0]["mapped"] is False
    assert located[0]["references"] == []


def test_reference_sentences_and_mapped_sources_are_reported(live_page) -> None:
    model = live_page.build_page_model(ARXIV_STYLE_HTML, "https://arxiv.org/html/demo")

    assert model["mapped_sources"] == 5
    assert model["reference_sentences"] >= 2
    assert model["reference_sentences"] <= len(live_page.sentence_split(model["body_text"]))
