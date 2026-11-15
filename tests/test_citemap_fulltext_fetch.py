from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_citemap_fulltext import europepmc_text, jats_text  # noqa: E402

JATS = b"""<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front><article-meta><title-group><article-title>Deep learning for diagnosis</article-title></title-group></article-meta></front>
  <body>
    <sec><title>Results</title>
      <p>The model reached 91.2% accuracy on the held-out set.</p>
      <p>Performance was lower on external data.</p>
    </sec>
  </body>
  <back><ref-list><ref><mixed-citation>Smith J. 2020. Something else.</mixed-citation></ref></ref-list></back>
</article>"""


def test_jats_text_keeps_body_and_drops_references() -> None:
    text = jats_text(JATS)
    assert "Deep learning for diagnosis" in text
    assert "91.2% accuracy" in text
    assert "Smith J. 2020" not in text


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, content: bytes = b""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content

    def json(self) -> dict:
        return self._payload


def test_europepmc_text_returns_pmcid_and_text(monkeypatch) -> None:
    calls = []
    long_jats = JATS.replace(
        b"</body>",
        b"<p>" + b"Model performance was consistent across cohorts. " * 120 + b"</p></body>",
    )

    def fake_get(url: str, **kwargs):
        calls.append(url)
        if "search" in url:
            return _Response(200, {"resultList": {"result": [{"pmcid": "PMC123"}]}})
        return _Response(200, content=long_jats)

    monkeypatch.setattr("fetch_citemap_fulltext.requests.get", fake_get)
    result = europepmc_text("10.1000/example")
    assert result is not None
    text, pmcid = result
    assert pmcid == "PMC123"
    assert "91.2% accuracy" in text
    assert any("PMC123/fullTextXML" in url for url in calls)


def test_europepmc_text_returns_none_without_pmcid(monkeypatch) -> None:
    monkeypatch.setattr(
        "fetch_citemap_fulltext.requests.get",
        lambda url, **kwargs: _Response(200, {"resultList": {"result": [{}]}}),
    )
    assert europepmc_text("10.1000/missing") is None
