"""Offline HTTP doubles and small builders shared by the test modules.

Nothing here performs I/O. ``install_fake_get`` replaces ``requests.get`` on the
module under test (``monkeypatch`` restores the original afterwards), so the real
parsing / verification logic runs unchanged against deterministic fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code: int = 200, payload=None, text: Optional[str] = None) -> None:
        self.status_code = status_code
        self._payload = payload
        if text is not None:
            self.text = text
        else:
            self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        if self._payload is None:
            raise ValueError("fake response has no JSON body")
        return self._payload


def install_fake_get(monkeypatch, module, handler: Callable[[str, dict], FakeResponse]) -> list[dict]:
    """Patch ``module.requests.get`` with ``handler`` and record every call."""
    calls: list[dict] = []

    def fake_get(url, params=None, timeout=None, headers=None, **kwargs):  # noqa: ANN001
        calls.append({"url": url, "params": dict(params or {})})
        return handler(url, dict(params or {}))

    monkeypatch.setattr(module.requests, "get", fake_get)
    return calls


def install_fake_post(monkeypatch, module, handler: Callable[[str, dict], FakeResponse]) -> list[dict]:
    """Patch ``module.requests.post`` with ``handler`` and record every call."""
    calls: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):  # noqa: ANN001, A002
        calls.append({"url": url, "json": json or {}, "headers": headers or {}})
        return handler(url, json or {})

    monkeypatch.setattr(module.requests, "post", fake_post)
    return calls


def _split_name(name: str) -> dict:
    parts = [p for p in name.replace(",", " ").split() if p]
    if not parts:
        return {}
    if len(parts) == 1:
        return {"family": parts[0]}
    return {"given": " ".join(parts[:-1]), "family": parts[-1]}


def crossref_message(ref, *, year: Optional[int] = None, title: Optional[str] = None,
                     abstract: str = "A deterministic abstract supplied by the test double.") -> dict:
    """Build a Crossref ``message`` object that mirrors a parsed ``Reference``."""
    issued_year = ref.year if year is None else year
    return {
        "title": [ref.title if title is None else title],
        "author": [_split_name(a) for a in ref.authors],
        "issued": {"date-parts": [[issued_year]]},
        "container-title": [ref.venue] if ref.venue else [],
        "volume": ref.volume,
        "issue": ref.issue,
        "page": ref.pages,
        "abstract": f"<jats:p>{abstract}</jats:p>",
        "DOI": ref.doi,
    }


def crossref_records(refs, *, skip_prefixes=("10.9999",)) -> dict[str, dict]:
    """Map DOI -> Crossref message for every reference that should resolve.

    References sharing a DOI reuse the first record (this is how the sample
    paper triggers genuine year drift for a duplicated DOI).
    """
    records: dict[str, dict] = {}
    for ref in refs:
        if not ref.doi or ref.doi.startswith(skip_prefixes):
            continue
        key = ref.doi[:-2] if ref.doi.endswith("_c") else ref.doi
        records.setdefault(key, crossref_message(ref))
    return records


def doi_from_url(url: str) -> Optional[str]:
    if "/works/" not in url:
        return None
    tail = url.split("/works/", 1)[1]
    if tail.startswith("https://doi.org/"):
        tail = tail[len("https://doi.org/"):]
    return tail.strip("/") or None


def make_doi_handler(records: dict[str, dict]):
    """Crossref DOI resolver: known DOIs -> 200, everything else -> 404.

    OpenAlex DOI lookups intentionally 404 so each check yields one candidate,
    keeping the assertions focused on the verification logic.
    """

    def handler(url: str, params: dict) -> FakeResponse:
        doi = doi_from_url(url)
        if doi and "api.crossref.org" in url and doi in records:
            return FakeResponse(200, {"message": records[doi]})
        return FakeResponse(404, {"status": "not found"})

    return handler


def openalex_work(ref, *, title: Optional[str] = None, year: Optional[int] = None,
                  abstract: str = "openalex abstract") -> dict:
    """Build an OpenAlex work object matching a parsed ``Reference``."""
    words = abstract.split()
    inverted: dict[str, list[int]] = {}
    for i, w in enumerate(words):
        inverted.setdefault(w, []).append(i)
    first, _, last = ref.pages.partition("-")
    return {
        "id": f"https://openalex.org/W{abs(hash((ref.title, ref.year))) % 10**9}",
        "doi": f"https://doi.org/{ref.doi}" if ref.doi else "",
        "title": ref.title if title is None else title,
        "publication_year": ref.year if year is None else year,
        "authorships": [{"author": {"display_name": a}} for a in ref.authors],
        "primary_location": {"source": {"display_name": ref.venue}},
        "biblio": {"volume": ref.volume, "issue": ref.issue, "first_page": first, "last_page": last},
        "abstract_inverted_index": inverted,
    }


def deepseek_support_response(label: str = "support", reason: str = "mock reason",
                              evidence: str = "mock evidence") -> FakeResponse:
    content = json.dumps(
        {"label": label, "confidence": 0.9, "reason": reason, "evidence": evidence},
        ensure_ascii=False,
    )
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def wait_for_job(client, job_id: str, timeout: float = 60.0, interval: float = 0.02) -> dict:
    """Poll ``/api/jobs/<id>`` until the background analysis finishes."""
    import time

    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last.get("status") in {"done", "error"}:
            return last
        time.sleep(interval)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s: {last!r}")


def wait_until(predicate: Callable[[], bool], timeout: float = 10.0, interval: float = 0.02) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False
