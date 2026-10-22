"""Shared pytest configuration and fixtures for CiteGuard-CN.

Design rules for this suite:
- **Fully offline**: every HTTP call is replaced by a fake transport
  (``tests/helpers.py``); no test touches OpenAlex / Crossref / arXiv / DeepSeek.
- **No API key required**: ``DEEPSEEK_API_KEY`` is cleared for every test, so the
  claim-support judge degrades to ``not_checked`` exactly as in production.
- **No writes into the repository**: fixtures redirect ``data/jobs``,
  ``data/cache`` and ``data/uploads`` into ``tmp_path``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]  # citeguard/
SRC = ROOT / "src"

# Make ``citeguard`` and ``web`` importable regardless of how pytest is invoked.
for _p in (str(ROOT), str(SRC), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    """Force the key-free, sleep-free, offline behaviour for every test."""
    from citeguard import config

    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(config, "API_SLEEP", 0.0)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    yield


@pytest.fixture
def isolated_project(tmp_path, monkeypatch):
    """Redirect all mutable project directories (jobs/cache/uploads) to tmp_path.

    Imported lazily so tests that only touch ``citeguard`` core do not require
    FastAPI/web dependencies to be importable.
    """
    from citeguard import config, jobs

    data = tmp_path / "data"
    for sub in ("jobs", "cache", "uploads"):
        (data / sub).mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "CACHE_DIR", data / "cache")
    monkeypatch.setattr(jobs, "JOBS_DIR", data / "jobs")
    monkeypatch.setattr(jobs.manager, "_jobs", {})

    import web.app as webapp

    monkeypatch.setattr(webapp, "UPLOAD_DIR", data / "uploads")
    return data


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Redirect only the HTTP cache directory (used by metadata/support tests)."""
    from citeguard import config

    cache = tmp_path / "cache"
    cache.mkdir(parents=True)
    monkeypatch.setattr(config, "CACHE_DIR", cache)
    return cache


@pytest.fixture(scope="session")
def sample_paper_text():
    return (ROOT / "web" / "static" / "samples" / "sample_paper.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def sample_parts(sample_paper_text):
    from citeguard.pdf_extract import split_references

    return split_references(sample_paper_text)


@pytest.fixture(scope="session")
def sample_refs(sample_parts):
    from citeguard.reference_parser import parse_reference_list

    _body, refs_text = sample_parts
    return parse_reference_list(refs_text)
