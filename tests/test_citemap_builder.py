from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _inverted(text: str) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for pos, word in enumerate(text.split()):
        out.setdefault(word, []).append(pos)
    return out


def _work(idx: int, sentence: str) -> dict:
    return {
        "id": f"https://openalex.org/W{1000000 + idx}",
        "doi": f"https://doi.org/10.5555/dyn.{idx}",
        "title": f"Dynamic paper {idx}: evidence for the topic",
        "publication_year": 2020 + idx,
        "authorships": [
            {
                "author": {"display_name": f"Author {idx}"},
                "institutions": [{"country_code": "CN" if idx % 2 else "US"}],
            }
        ],
        "primary_location": {
            "source": {"display_name": "Journal of Dynamic Evidence"},
            "license": "cc-by",
        },
        "best_oa_location": {"pdf_url": f"https://example.org/{idx}.pdf", "license": "cc-by"},
        "open_access": {"is_oa": True, "oa_status": "gold"},
        "cited_by_count": 100 - idx,
        "language": "en",
        "abstract_inverted_index": _inverted(sentence),
    }


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "evidence_map"
    root.mkdir()
    (root / "index.json").write_text(
        json.dumps({"schema_version": "1.0", "generated_at": "2026-01-01", "topics": []}),
        encoding="utf-8",
    )
    return root


def test_build_from_topic_writes_valid_machine_map(data_dir, monkeypatch):
    from citeguard import citemap_builder, evidence_map

    sentences = [
        "We find that generative AI improves access to tutoring for rural students in the sample.",
        "Results show a significant increase in teacher feedback quality after the intervention.",
        "Our results suggest that AI use is associated with reduced grading time for instructors.",
        "This study finds that the tool improved learning outcomes, but the effect is small.",
        "We conclude that equity benefits depend on school resources and teacher training.",
    ]
    works = [_work(i, s) for i, s in enumerate(sentences)]
    monkeypatch.setattr(citemap_builder, "search_works", lambda query, limit=15: works)

    result = citemap_builder.build_from_topic(
        "动态测试主题", question="机器证据是否能覆盖这个主题？", limit=5, data_dir=data_dir
    )

    assert result["papers"] == 5
    assert result["claims"] == 5
    assert result["evidence"] == 5
    topic_dir = data_dir / "dynamic" / result["topic_id"]
    corpus = json.loads((topic_dir / "corpus.json").read_text(encoding="utf-8"))
    extraction = json.loads((topic_dir / "extractions.json").read_text(encoding="utf-8"))
    evidence_map.CorpusManifest.from_dict(corpus)
    evidence_map.EvidenceMap.from_dict(extraction)
    assert len(corpus["papers"]) == 5
    assert all(e["verified"] is False for e in extraction["evidence"])
    assert all(e["extracted_by"] == "machine:abstract-finding" for e in extraction["evidence"])
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    assert index["topics"][0]["machine"] is True
    assert index["topics"][0]["topic_id"] == result["topic_id"]


def test_build_from_topic_rejects_thin_results(data_dir, monkeypatch):
    from citeguard import citemap_builder

    monkeypatch.setattr(citemap_builder, "search_works", lambda query, limit=15: [])
    with pytest.raises(ValueError, match="不足 5 篇"):
        citemap_builder.build_from_topic("空主题", data_dir=data_dir)


def test_generate_api_wires_builder(monkeypatch):
    from web import app as web_app
    from citeguard import citemap_builder

    monkeypatch.setattr(
        citemap_builder,
        "build_from_topic",
        lambda topic, **kwargs: {"topic_id": "dyn-test", "papers": 5, "claims": 5, "evidence": 5},
    )
    client = TestClient(web_app.app)
    response = client.post("/api/citemap/generate", json={"topic": "测试主题", "limit": 5})
    assert response.status_code == 200
    assert response.json()["topic_id"] == "dyn-test"
    assert response.json()["machine"] is True

    assert client.post("/api/citemap/generate", json={"topic": "   "}).status_code == 400


def test_build_from_dois_uses_the_user_list(data_dir, monkeypatch):
    from citeguard import citemap_builder

    sentences = [
        "We find that the intervention improved outcomes in the sampled schools.",
        "Results show a significant reduction in waiting time for patients.",
        "Our results suggest that the model is associated with better triage.",
        "This study finds that accuracy improved, but the sample is small.",
        "We conclude that the effect depends on implementation context.",
    ]
    works = [_work(20 + i, s) for i, s in enumerate(sentences)]
    monkeypatch.setattr(citemap_builder, "lookup_dois", lambda dois: works)
    result = citemap_builder.build_from_dois(
        "自己的论文", [f"10.5555/own.{i}" for i in range(5)], limit=5, data_dir=data_dir
    )
    assert result["papers"] == 5
    corpus = json.loads(
        (data_dir / "dynamic" / result["topic_id"] / "corpus.json").read_text(encoding="utf-8")
    )
    assert "用户提供 DOI" in corpus["source"]


def test_generate_api_accepts_doi_list(monkeypatch):
    from web import app as web_app
    from citeguard import citemap_builder

    seen = {}

    def fake_dois(topic, dois, **kwargs):
        seen["dois"] = list(dois)
        return {"topic_id": "dyn-doi", "papers": 5, "claims": 5, "evidence": 5}

    monkeypatch.setattr(citemap_builder, "build_from_dois", fake_dois)
    client = TestClient(web_app.app)
    response = client.post(
        "/api/citemap/generate",
        json={"topic": "自选论文", "dois": [f"10.1/{i}" for i in range(5)]},
    )
    assert response.status_code == 200
    assert seen["dois"] and len(seen["dois"]) == 5
