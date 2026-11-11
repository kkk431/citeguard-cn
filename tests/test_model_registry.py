"""Model registry: switching the support judge without env edits."""
from __future__ import annotations

from citeguard import model_registry, support


def test_defaults_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("CITEGUARD_MODEL_REGISTRY", str(tmp_path / "reg.json"))
    data = model_registry.load_registry()
    assert data["active"] is None
    assert {m["id"] for m in data["models"]} >= {"hosted-deepseek", "local-qwen3-14b", "local-qwen3-14b-4bit", "local-lora-1.7b"}

    model_registry.set_active("local-qwen3-14b")
    saved = model_registry.load_registry()
    assert saved["active"] == "local-qwen3-14b"
    assert (tmp_path / "reg.json").exists()


def test_judge_endpoint_follows_active_model(tmp_path, monkeypatch):
    monkeypatch.setenv("CITEGUARD_MODEL_REGISTRY", str(tmp_path / "reg.json"))
    monkeypatch.setenv("CITEGUARD_JUDGE_API_KEY", "test-key")
    base, model, key = support.judge_endpoint()
    assert "api.deepseek.com" in base
    assert model == "deepseek-chat"
    assert key == "test-key"

    model_registry.set_active("hosted-deepseek")
    base, model, _ = support.judge_endpoint()
    assert base == "https://api.deepseek.com/v1"
    assert model == "deepseek-chat"

    model_registry.set_active("local-qwen3-14b")
    base, model, _ = support.judge_endpoint()
    assert base == "http://127.0.0.1:8097/v1"
    assert model == "qwen3-14b"

    model_registry.set_active("local-lora-1.7b")
    base, model, _ = support.judge_endpoint()
    assert base == "http://127.0.0.1:8100/v1"
    assert model == "support-lora"


def test_unknown_model_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("CITEGUARD_MODEL_REGISTRY", str(tmp_path / "reg.json"))
    try:
        model_registry.set_active("nope")
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
