"""万方开放平台客户端的最小单测（不发真实网络请求）。"""

from __future__ import annotations

import io
import json

import pytest

from citeguard import config, wanfang


class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_search_parses_records(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data.decode("utf-8"))
        payload = {"documents": [{"resourceType": "Periodical", "uid": "u1", "Periodical": {"Id": "dbc1", "Title": ["人工智能教育应用"], "PublishYear": 2021}}]}
        return _FakeResponse(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    monkeypatch.setattr(config, "WANFANG_APP_KEY", "key-123")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    rows = wanfang.search("Title:人工智能", rows=2)
    assert rows[0]["Title"] == ["人工智能教育应用"]
    assert rows[0]["Id"] == "dbc1"
    assert captured["body"]["collections"] == ["OpenPeriodicalChi"]
    assert captured["headers"]["X-app-key"] == "key-123"
    assert captured["url"].startswith("https://")


def test_not_subscribed_is_actionable(monkeypatch):
    import urllib.error

    def fake_urlopen(request, timeout=0):
        body = json.dumps(
            {
                "code": "AUTH_NOT_SUBSCRIBED",
                "message": "尚未订阅接口「万方文献检索」",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(body))

    monkeypatch.setattr(config, "WANFANG_APP_KEY", "key-123")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(wanfang.WanfangNotSubscribed) as excinfo:
        wanfang.search("人工智能")
    assert "ai.wfdata.com/api-detail?id=17" in str(excinfo.value)


def test_missing_key(monkeypatch):
    monkeypatch.setattr(config, "WANFANG_APP_KEY", "")
    assert not wanfang.available()
    with pytest.raises(wanfang.WanfangNotConfigured):
        wanfang.search("人工智能")


def test_record_to_candidate_fields():
    record = {
        "Id": "dbc1",
        "Title": "人工智能教育应用",
        "Creator": ["张三", "李四"],
        "PublishYear": "2021",
        "PeriodicalTitle": "现代教育技术",
        "Volum": "31",
        "Issue": "4",
        "Page": "1-8",
        "DOI": "10.3969/j.issn.1009-8097.2021.04.001",
        "Abstract": "摘要",
    }
    fields = wanfang.record_to_candidate_fields(record)
    assert fields["title"] == "人工智能教育应用"
    assert fields["authors"] == "张三; 李四"
    assert fields["year"] == 2021
    assert fields["venue"] == "现代教育技术"
    assert fields["doi"].startswith("10.3969/")
    assert fields["url"].endswith("/dbc1")
