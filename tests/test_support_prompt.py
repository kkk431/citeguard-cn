"""Custom support prompt (CITEGUARD_SUPPORT_PROMPT_FILE) behaviour."""
from __future__ import annotations

import importlib

import pytest

from citeguard import config


def test_custom_prompt_replaces_prompt_and_namespaces_cache(tmp_path, monkeypatch):
    prompt = tmp_path / "simple.txt"
    prompt.write_text("CUSTOM SUPPORT PROMPT", encoding="utf-8")
    monkeypatch.setattr(config, "SUPPORT_PROMPT_FILE", str(prompt))
    import citeguard.support as support

    reloaded = importlib.reload(support)
    try:
        assert reloaded.PROMPT == "CUSTOM SUPPORT PROMPT"
        # Built-in version + content hash, so cached verdicts never mix.
        assert reloaded.PROMPT_VERSION.startswith("4-")
    finally:
        monkeypatch.undo()
        importlib.reload(support)


def test_missing_prompt_file_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SUPPORT_PROMPT_FILE", str(tmp_path / "missing.txt"))
    import citeguard.support as support

    with pytest.raises(RuntimeError, match="CITEGUARD_SUPPORT_PROMPT_FILE"):
        importlib.reload(support)
    monkeypatch.undo()
    importlib.reload(support)
