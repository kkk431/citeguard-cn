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
        lambda data, mime, claim: {"ok": True, "verdict": "insufficient", "reason": "图中没有该数据", "model": "m", "latency_ms": 12},
    )
    ok = client.post(
        "/api/figure-check",
        files={"image": ("a.png", b"img", "image/png")},
        data={"claim": "这个结论成立吗？"},
    )
    assert ok.status_code == 200
    assert ok.json()["verdict"] == "insufficient"
