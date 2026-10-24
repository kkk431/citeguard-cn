"""Tests for the optional figure-claim check (OpenAI-compatible vision endpoint)."""
from __future__ import annotations

import requests

from citeguard import config, figure_check


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_not_configured(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "")
    result = figure_check.check_figure(b"\x89PNG", "image/png", "这个结论成立吗？")
    assert result["ok"] is False
    assert result["code"] == "not_configured"


def test_rejects_bad_mime(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    result = figure_check.check_figure(b"text", "text/plain", "图表里的结论是否成立？")
    assert result["code"] == "bad_mime"


def test_rejects_short_claim(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    result = figure_check.check_figure(b"img", "image/png", "短")
    assert result["code"] == "bad_claim"


def test_rejects_oversized_image(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    monkeypatch.setattr(config, "VL_MAX_FIGURE_MB", 1)
    result = figure_check.check_figure(b"x" * (1024 * 1024 + 1), "image/png", "这个结论成立吗？")
    assert result["code"] == "too_large"


def test_success_parses_json_code_fence(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    monkeypatch.setattr(config, "VL_MODEL", "qwen2.5-vl-7b")
    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        return FakeResponse(200, _completion('```json\n{"verdict":"supported","reason":"数值与柱子一致"}\n```'))

    monkeypatch.setattr(figure_check.requests, "post", fake_post)
    result = figure_check.check_figure(b"img", "image/jpeg", "方法1 的准确率最高，约为 95%。")
    assert result["ok"] is True
    assert result["verdict"] == "supported"
    assert result["reason"] == "数值与柱子一致"
    assert result["model"] == "qwen2.5-vl-7b"
    assert calls["url"] == "http://gpu:8099/v1/chat/completions"
    assert calls["json"]["model"] == "qwen2.5-vl-7b"
    text = calls["json"]["messages"][0]["content"][1]["text"]
    assert "方法1" in text
    assert "Authorization" not in calls["headers"]


def test_sends_bearer_when_key_configured(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    monkeypatch.setattr(config, "VL_API_KEY", "secret")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["headers"] = headers
        return FakeResponse(200, _completion('{"verdict":"contradicted","reason":"年份不对"}'))

    monkeypatch.setattr(figure_check.requests, "post", fake_post)
    result = figure_check.check_figure(b"img", "image/png", "2023 年的发文量最高。")
    assert result["ok"] is True
    assert result["verdict"] == "contradicted"
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_http_error(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    monkeypatch.setattr(figure_check.requests, "post", lambda *a, **k: FakeResponse(502))
    result = figure_check.check_figure(b"img", "image/png", "这个结论成立吗？")
    assert result["code"] == "http_error"


def test_unreachable(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")

    def boom(*args, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(figure_check.requests, "post", boom)
    result = figure_check.check_figure(b"img", "image/png", "这个结论成立吗？")
    assert result["code"] == "unreachable"


def test_bad_response(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    monkeypatch.setattr(figure_check.requests, "post", lambda *a, **k: FakeResponse(200, {"choices": []}))
    result = figure_check.check_figure(b"img", "image/png", "这个结论成立吗？")
    assert result["code"] == "bad_response"


def test_figure_page_and_api(monkeypatch):
    from fastapi.testclient import TestClient

    import web.app as webapp

    monkeypatch.setattr(config, "VL_ENDPOINT", "")
    client = TestClient(webapp.app)
    page = client.get("/figure")
    assert page.status_code == 200
    assert "没有配置视觉模型服务" in page.text
    blocked = client.post(
        "/api/figure-check",
        files={"image": ("a.png", b"img", "image/png")},
        data={"claim": "这个结论成立吗？"},
    )
    assert blocked.status_code == 503

    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    monkeypatch.setattr(
        figure_check,
        "check_figure",
        lambda data, mime, claim, context="": {"ok": True, "verdict": "insufficient", "reason": "图中没有该数据", "model": "m", "latency_ms": 12},
    )
    ok = client.post(
        "/api/figure-check",
        files={"image": ("a.png", b"img", "image/png")},
        data={"claim": "这个结论成立吗？"},
    )
    assert ok.status_code == 200
    assert ok.json()["verdict"] == "insufficient"


def test_context_is_included_and_truncated(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return FakeResponse(200, _completion('{"verdict":"supported","reason":"正文一致"}'))

    monkeypatch.setattr(figure_check.requests, "post", fake_post)
    long_context = "这段正文说 2025 年发文量最高。" * 500
    result = figure_check.check_figure(b"img", "image/png", "2025 年的发文量最高。", long_context)
    assert result["ok"] is True
    assert result["context_chars"] == figure_check.MAX_CONTEXT_CHARS
    prompt = captured["json"]["messages"][0]["content"][1]["text"]
    assert "正文/图注摘录（可能不完整）" in prompt
    assert prompt.count("这段正文说") <= 500
    assert len(prompt) < figure_check.MAX_CONTEXT_CHARS + 2000


def test_context_omitted_keeps_figure_only_prompt(monkeypatch):
    monkeypatch.setattr(config, "VL_ENDPOINT", "http://gpu:8099/v1")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return FakeResponse(200, _completion('{"verdict":"insufficient","reason":"缺少坐标轴"}'))

    monkeypatch.setattr(figure_check.requests, "post", fake_post)
    figure_check.check_figure(b"img", "image/png", "结论足够长的测试句子。")
    prompt = captured["json"]["messages"][0]["content"][1]["text"]
    assert "正文/图注摘录（可能不完整）" not in prompt

def test_figure_api_rejects_non_pdf_paper(monkeypatch):
    from fastapi.testclient import TestClient
    from web import app as webapp

    monkeypatch.setattr(figure_check, "available", lambda: True)
    monkeypatch.setattr(
        figure_check,
        "check_figure",
        lambda *a, **k: {"ok": True, "verdict": "supported", "reason": "x", "model": "m", "latency_ms": 1},
    )
    client = TestClient(webapp.app)
    resp = client.post(
        "/api/figure-check",
        files={
            "image": ("a.png", b"img", "image/png"),
            "paper": ("paper.txt", b"hello", "text/plain"),
        },
        data={"claim": "这个结论成立吗？"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "paper_not_pdf"


def test_figure_api_reads_pdf_page_as_context(monkeypatch):
    from fastapi.testclient import TestClient
    from web import app as webapp

    monkeypatch.setattr(figure_check, "available", lambda: True)
    monkeypatch.setattr(
        webapp,
        "extract_page_text",
        lambda path, page: "第 3 页正文：方法1 的准确率约 95%。",
    )
    captured = {}

    def fake_check(payload, content_type, claim, context=""):
        captured["context"] = context
        return {"ok": True, "verdict": "supported", "reason": "一致", "model": "m", "latency_ms": 5}

    monkeypatch.setattr(figure_check, "check_figure", fake_check)
    client = TestClient(webapp.app)
    resp = client.post(
        "/api/figure-check",
        files={
            "image": ("a.png", b"img", "image/png"),
            "paper": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf"),
        },
        data={"claim": "方法1 的准确率最高，约为 95%。", "page": "3", "context": "手动补充"},
    )
    assert resp.status_code == 200
    assert resp.json()["context_source"] == "pdf_page:3"
    assert captured["context"].startswith("第 3 页正文")
    assert "手动补充" in captured["context"]

def test_figure_api_auto_locates_figure_page(monkeypatch):
    from fastapi.testclient import TestClient
    from web import app as webapp

    monkeypatch.setattr(figure_check, "available", lambda: True)
    monkeypatch.setattr(webapp, "find_figure_page", lambda path, number: (3, "图1 方法1 的准确率（%）"))
    monkeypatch.setattr(webapp, "extract_page_text", lambda path, page: "第 3 页正文：方法1 的准确率约 95%。")
    captured = {}

    def fake_check(payload, content_type, claim, context=""):
        captured["context"] = context
        return {"ok": True, "verdict": "supported", "reason": "一致", "model": "m", "latency_ms": 5}

    monkeypatch.setattr(figure_check, "check_figure", fake_check)
    client = TestClient(webapp.app)
    resp = client.post(
        "/api/figure-check",
        files={
            "image": ("a.png", b"img", "image/png"),
            "paper": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf"),
        },
        data={"claim": "如图 1 所示，方法1 的准确率最高。"},
    )
    assert resp.status_code == 200
    assert resp.json()["context_source"] == "pdf_auto:3"
    assert captured["context"].startswith("图注：图1")


def test_figure_api_reports_missing_figure_caption(monkeypatch):
    from fastapi.testclient import TestClient
    from web import app as webapp

    monkeypatch.setattr(figure_check, "available", lambda: True)
    monkeypatch.setattr(webapp, "find_figure_page", lambda path, number: None)
    client = TestClient(webapp.app)
    resp = client.post(
        "/api/figure-check",
        files={
            "image": ("a.png", b"img", "image/png"),
            "paper": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf"),
        },
        data={"claim": "如图 1 所示，结论成立。"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "page_not_found"
    assert "图 1" in resp.json()["error"]
