import io
import json
import pytest

from citeguard import client as client_mod
from citeguard.client import CiteGuardClient, CiteGuardError


class _FakeResp:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_health(monkeypatch):
    monkeypatch.setattr(client_mod.urllib.request, "urlopen", lambda req, timeout: _FakeResp({"ok": True, "version": "0.9.79"}))
    assert CiteGuardClient("http://x").health()["version"] == "0.9.79"


def test_check_support(monkeypatch):
    payload = {"ok": True, "label": "contradict", "confidence": 0.96, "reason": "数字不一致",
               "audit": {"fully_covered": False}, "numeric": {"checked": True, "note": "+12% vs +3%"},
               "prompt_version": "v10"}
    monkeypatch.setattr(client_mod.urllib.request, "urlopen", lambda req, timeout: _FakeResp(payload))
    r = CiteGuardClient("http://x").check_support("a", "b")
    assert r.label == "contradict" and r.confidence == 0.96
    assert r.numeric["checked"] is True
    assert r.audit["fully_covered"] is False


def test_batch(monkeypatch):
    payload = {"ok": True, "results": [{"i": 0, "label": "support"}, {"i": 1, "label": "no_evidence"}]}
    monkeypatch.setattr(client_mod.urllib.request, "urlopen", lambda req, timeout: _FakeResp(payload))
    out = CiteGuardClient("http://x").check_support_batch([{"claim": "a", "evidence": "b"}])
    assert [x["label"] for x in out] == ["support", "no_evidence"]


def test_http_error_becomes_citeguard_error(monkeypatch):
    import urllib.error

    def boom(req, timeout):
        raise urllib.error.HTTPError("http://x", 503, "offline",
                                     {}, io.BytesIO(json.dumps({"ok": False, "code": "offline", "error": "离线模式"}).encode()))

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", boom)
    with pytest.raises(CiteGuardError) as ei:
        CiteGuardClient("http://x").check_support("a", "b")
    assert ei.value.status == 503 and ei.value.code == "offline"
