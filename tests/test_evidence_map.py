"""Tests for the CiteMap evidence-map schema, corpus and extraction samples.

Module B1 of the 国一 flagship plan.  The tests are fully offline: they only read
the JSON files under ``data/evidence_map/`` and mutate in-memory copies.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from citeguard import evidence_map as em

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "evidence_map"
TOPICS = ("ai_education", "medical_imaging")
INDEX = DATA_DIR / "index.json"
VERIFICATION = DATA_DIR / "verification.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _corpus_path(topic: str) -> Path:
    return DATA_DIR / "corpus" / f"{topic}.json"


def _map_path(topic: str) -> Path:
    return DATA_DIR / "extractions" / f"{topic}.json"


@pytest.fixture(params=TOPICS)
def topic(request) -> str:
    return request.param


@pytest.fixture
def corpus(topic: str) -> em.CorpusManifest:
    return em.load_corpus(_corpus_path(topic), expected_papers=15)


@pytest.fixture
def evidence_map(topic: str, corpus: em.CorpusManifest) -> em.EvidenceMap:
    return em.load_map(_map_path(topic), corpus=corpus, expected_evidence=5)


@pytest.fixture
def corpus_dict(topic: str) -> dict:
    return copy.deepcopy(_read(_corpus_path(topic)))


@pytest.fixture
def map_dict(topic: str) -> dict:
    return copy.deepcopy(_read(_map_path(topic)))


# ---------------------------------------------------------------------------
# Schema constants and primitives
# ---------------------------------------------------------------------------


def test_schema_constants() -> None:
    assert em.SCHEMA_VERSION == "1.0"
    assert set(em.STANCES) == {"support", "contradict", "neutral"}
    assert set(em.GAP_KINDS) == {"evidence", "method", "sample", "outcome", "theory"}
    assert set(em.SEVERITIES) == {"low", "medium", "high"}
    assert set(em.RISK_OF_BIAS) == {"low", "some", "high", "unclear"}
    assert {member.value for member in em.Stance} == set(em.STANCES)


def test_stance_enum_accepts_wire_values() -> None:
    assert em.Stance("support") is em.Stance.SUPPORT
    assert em.Stance("contradict") is em.Stance.CONTRADICT
    assert em.Stance("neutral") is em.Stance.NEUTRAL
    with pytest.raises(ValueError):
        em.Stance("contradicts")


def test_normalize_doi_strips_resolver_prefixes() -> None:
    assert em.normalize_doi("10.1000/ABC") == "10.1000/ABC"
    assert em.normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/ABC"
    assert em.normalize_doi("http://dx.doi.org/10.1000/abc") == "10.1000/abc"
    assert em.normalize_doi("doi:10.1000/abc") == "10.1000/abc"
    with pytest.raises(em.EvidenceMapError, match="格式非法"):
        em.normalize_doi("not-a-doi")


# ---------------------------------------------------------------------------
# Corpus manifests (2 topics x 15 open-access papers)
# ---------------------------------------------------------------------------


def test_corpus_has_fifteen_papers(topic: str, corpus: em.CorpusManifest) -> None:
    assert len(corpus.papers) == 15
    assert corpus.topic.topic_id == topic
    assert corpus.topic.question.strip()
    assert corpus.topic.description.strip()


def test_corpus_identifiers_are_unique(corpus: em.CorpusManifest) -> None:
    paper_ids = [paper.paper_id for paper in corpus.papers]
    dois = [paper.doi.lower() for paper in corpus.papers]
    openalex_ids = [paper.openalex_id for paper in corpus.papers]
    assert len(set(paper_ids)) == 15
    assert len(set(dois)) == 15
    assert len(set(openalex_ids)) == 15


def test_paper_ids_follow_documented_order(topic: str, corpus: em.CorpusManifest) -> None:
    prefix = "edu" if topic == "ai_education" else "med"
    assert [paper.paper_id for paper in corpus.papers] == [
        f"{prefix}-{index:03d}" for index in range(1, 16)
    ]


def test_every_paper_has_open_license_and_bibliographic_metadata(
    corpus: em.CorpusManifest,
) -> None:
    for paper in corpus.papers:
        assert paper.license, paper.paper_id
        assert paper.license.startswith("cc-"), paper.paper_id
        assert paper.license not in em.LICENSE_UNKNOWN_VALUES
        assert paper.is_oa is True, paper.paper_id
        assert paper.url.startswith("https://doi.org/"), paper.paper_id
        assert paper.doi.startswith("10.") and "doi.org" not in paper.doi
        assert paper.openalex_id.startswith("W")
        assert paper.title.strip()
        assert paper.authors and all(author.strip() for author in paper.authors)
        assert 1990 <= paper.year <= 2030
        assert paper.venue.strip()
        assert paper.oa_status in em.OA_STATUSES
        assert paper.oa_status not in {"unknown", "closed"}
        assert paper.topic_id == corpus.topic.topic_id


def test_corpus_contains_chinese_affiliated_research(topic: str, corpus: em.CorpusManifest) -> None:
    cn_papers = [paper for paper in corpus.papers if paper.cn_affiliated]
    assert len(cn_papers) >= 8, topic
    # Each topic also keeps non-CN high-citation contrast papers.
    assert len(cn_papers) < 15, topic


def test_fulltext_flags_match_notes(corpus: em.CorpusManifest) -> None:
    for paper in corpus.papers:
        if paper.fulltext_available:
            assert paper.oa_url.startswith(("http://", "https://")), paper.paper_id
        else:
            assert paper.notes, paper.paper_id
            assert "PDF" in paper.notes, paper.paper_id


def test_manifest_metadata_matches_index(corpus: em.CorpusManifest) -> None:
    index = _read(INDEX)
    entry = next(item for item in index["topics"] if item["topic_id"] == corpus.topic.topic_id)
    assert entry["name_zh"] == corpus.topic.name_zh
    assert entry["name_en"] == corpus.topic.name_en
    assert entry["question"] == corpus.topic.question
    assert entry["papers"] == 15


def test_manifest_round_trip(corpus: em.CorpusManifest) -> None:
    parsed = em.parse_corpus(corpus.to_dict())
    assert parsed == corpus
    assert len(parsed.papers) == 15


def test_data_directory_contains_no_pdf_files() -> None:
    payloads = [path for path in DATA_DIR.rglob("*") if path.is_file()]
    assert payloads, "data/evidence_map must not be empty"
    assert {path.suffix for path in payloads} <= {".json", ".md"}
    assert not list(DATA_DIR.rglob("*.pdf"))


def test_readme_documents_copyright_policy() -> None:
    readme = (DATA_DIR / "README.md").read_text(encoding="utf-8")
    assert "PDF" in readme and "不" in readme
    assert "cc-by" in readme


def test_docs_document_schema_and_web_contract() -> None:
    docs = (DATA_DIR.parents[1] / "docs" / "evidence_map.md").read_text(encoding="utf-8")
    for needle in (
        "Stance",
        "confidence",
        "Gap",
        "fulltext_available",
        "GET /api/citemap",
    ):
        assert needle in docs
    assert "PDF" in docs and "许可" in docs


# ---------------------------------------------------------------------------
# Extraction samples (claims + evidence + method/sample + stance + gap)
# ---------------------------------------------------------------------------


def test_extraction_map_loads(topic: str, evidence_map: em.EvidenceMap) -> None:
    assert evidence_map.topic.topic_id == topic
    assert len(evidence_map.evidence) == 5
    assert len(evidence_map.gaps) >= 3
    assert evidence_map.extracted_at
    assert evidence_map.extractor
    assert evidence_map.protocol


def test_claims_are_complete_and_supported(topic: str, evidence_map: em.EvidenceMap) -> None:
    assert evidence_map.claims
    evidence_claim_ids = {item.claim_id for item in evidence_map.evidence}
    for claim in evidence_map.claims:
        assert claim.topic_id == topic
        assert claim.text.strip()
        assert claim.direction in em.DIRECTIONS
        assert claim.claim_id in evidence_claim_ids


def test_evidence_fields_are_complete(corpus: em.CorpusManifest, evidence_map: em.EvidenceMap) -> None:
    paper_ids = {paper.paper_id for paper in corpus.papers}
    for item in evidence_map.evidence:
        assert item.paper_id in paper_ids
        assert item.stance in {em.Stance.SUPPORT, em.Stance.CONTRADICT, em.Stance.NEUTRAL}
        assert len(item.summary.strip()) >= 20
        assert item.quote.strip()
        assert item.locator.strip()
        assert item.locator.startswith("Abstract")
        assert item.quote_lang == "en"
        assert 0.0 <= item.confidence <= 1.0
        assert item.extracted_by
        assert "人工" in item.extracted_by or "boundary" in item.extracted_by
        assert item.verified is False


def test_quotes_are_abstract_level_and_confidence_capped(evidence_map: em.EvidenceMap) -> None:
    for item in evidence_map.evidence:
        assert len(item.quote) > 20
        assert item.confidence <= 0.75
        assert "仅读" in item.notes
        assert item.locator


def test_stance_counts_cover_all_stances(evidence_map: em.EvidenceMap) -> None:
    counts = evidence_map.stance_counts()
    assert set(counts) == set(em.STANCES)
    assert sum(counts.values()) == 5
    assert counts["support"] >= 1
    assert counts["contradict"] >= 1


def test_method_and_sample_are_consistent(evidence_map: em.EvidenceMap) -> None:
    with_method = 0
    with_sample = 0
    for item in evidence_map.evidence:
        if item.method is not None:
            with_method += 1
            assert item.method.design.strip()
            assert item.method.risk_of_bias in em.RISK_OF_BIAS
            if item.sample is not None:
                with_sample += 1
                assert item.sample.size >= 1
                assert item.sample.unit.strip()
                assert item.sample.population.strip()
                if item.method.sample_size is not None:
                    assert item.method.sample_size == item.sample.size
    assert with_method == 5
    assert with_sample >= 3


def test_gaps_reference_known_claims(topic: str, evidence_map: em.EvidenceMap) -> None:
    known_claims = {claim.claim_id for claim in evidence_map.claims}
    for gap in evidence_map.gaps:
        assert gap.topic_id == topic
        assert gap.kind in em.GAP_KINDS
        assert gap.severity in em.SEVERITIES
        assert len(gap.description.strip()) >= 20
        assert gap.related_claim_ids
        assert set(gap.related_claim_ids) <= known_claims


def test_topic_metadata_is_identical_across_files(corpus: em.CorpusManifest, evidence_map: em.EvidenceMap) -> None:
    assert evidence_map.topic == corpus.topic


def test_extraction_map_round_trip(corpus: em.CorpusManifest, evidence_map: em.EvidenceMap) -> None:
    parsed = em.parse_map(evidence_map.to_dict(), corpus=corpus)
    assert parsed == evidence_map


def test_ten_human_extractions_across_topics() -> None:
    evidence_ids: list[str] = []
    for topic in TOPICS:
        corpus = em.load_corpus(_corpus_path(topic), expected_papers=15)
        evidence_map = em.load_map(_map_path(topic), corpus=corpus, expected_evidence=5)
        evidence_ids.extend(item.evidence_id for item in evidence_map.evidence)
    assert len(evidence_ids) == 10
    assert len(set(evidence_ids)) == 10


# ---------------------------------------------------------------------------
# Index, verification and web payload
# ---------------------------------------------------------------------------


def test_index_lists_two_topics_with_computed_counts() -> None:
    index = _read(INDEX)
    assert index["schema_version"] == em.SCHEMA_VERSION
    summaries = em.list_topics(DATA_DIR)
    assert [summary["topic_id"] for summary in summaries] == [
        entry["topic_id"] for entry in index["topics"]
    ]
    assert len(summaries) == 2
    assert {summary["topic_id"] for summary in summaries} == set(TOPICS)
    for summary, entry in zip(summaries, index["topics"]):
        assert summary["papers"] == 15
        assert summary["claims"] == entry["claims"]
        assert summary["evidence"] == 5
        assert summary["gaps"] == entry["gaps"]
        assert summary["papers"] == entry["papers"]
        assert summary["stances"]["support"] >= 1
        assert summary["stances"]["contradict"] >= 1


def test_verification_covers_every_paper(corpus: em.CorpusManifest) -> None:
    verification = _read(VERIFICATION)
    assert verification["schema_version"] == em.SCHEMA_VERSION
    paper_ids = {paper.paper_id for paper in corpus.papers}
    entries = {
        entry["paper_id"]: entry
        for entry in verification["papers"]
        if entry["paper_id"] in paper_ids
    }
    assert set(entries) == paper_ids
    for paper in corpus.papers:
        entry = entries[paper.paper_id]
        assert entry["doi"] == paper.doi
        assert entry["crossref_status"] == 200
        assert entry["handle_response_code"] == 1
        assert entry["title_match"] in {"exact", "prefix"}
        assert entry["oa_license"] == paper.license
        assert entry["license_consistent"] is not False


def test_verification_summary_is_consistent() -> None:
    verification = _read(VERIFICATION)
    entries = verification["papers"]
    summary = verification["summary"]
    assert len(entries) == summary["papers"] == 30
    assert summary["crossref_ok"] == 30
    assert summary["handle_ok"] == 30
    assert summary["title_mismatch"] == 0
    assert summary["license_mismatch"] == 0
    assert summary["license_consistent"] + summary["license_unchecked"] == 30
    assert (
        sum(1 for entry in entries if entry["license_consistent"] is True)
        == summary["license_consistent"]
    )
    assert (
        sum(1 for entry in entries if entry["license_consistent"] is None)
        == summary["license_unchecked"]
    )


def test_topic_payload_is_json_ready(topic: str) -> None:
    payload = em.topic_payload(topic, DATA_DIR)
    assert payload["schema_version"] == em.SCHEMA_VERSION
    assert payload["topic"]["topic_id"] == topic
    assert len(payload["papers"]) == 15
    assert len(payload["evidence"]) == 5
    assert payload["counts"]["papers"] == 15
    assert payload["counts"]["evidence"] == 5
    assert sum(payload["counts"]["stances"].values()) == 5
    for claim in payload["claims"]:
        assert claim["evidence_ids"]
        assert sum(claim["stance_counts"].values()) == len(claim["evidence_ids"])
    for item in payload["evidence"]:
        assert item["paper_id"]
        assert item["claim_id"]
        assert item["stance"] in em.STANCES
    assert payload["verification"]["summary"]["papers"] == 30
    json.dumps(payload, ensure_ascii=False)


def test_unknown_topic_raises_with_known_topics() -> None:
    with pytest.raises(em.UnknownTopicError) as excinfo:
        em.topic_payload("does_not_exist", DATA_DIR)
    assert excinfo.value.topic_id == "does_not_exist"
    assert "ai_education" in str(excinfo.value)
    assert "medical_imaging" in str(excinfo.value)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_check_reports_totals(capsys) -> None:
    assert em.main(["--check", "--data-dir", str(DATA_DIR)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["schema_version"] == em.SCHEMA_VERSION
    assert result["totals"] == {"papers": 30, "claims": 7, "evidence": 10, "gaps": 6}
    assert len(result["topics"]) == 2


def test_cli_topic_payload(capsys) -> None:
    assert em.main(["--data-dir", str(DATA_DIR), "--topic", "ai_education"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["payload"]["topic"]["topic_id"] == "ai_education"
    assert result["payload"]["counts"]["evidence"] == 5


def test_cli_unknown_topic_exits_two(capsys) -> None:
    assert em.main(["--data-dir", str(DATA_DIR), "--topic", "nope"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_cli_missing_data_dir_exits_two(tmp_path, capsys) -> None:
    assert em.main(["--data-dir", str(tmp_path / "missing")]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


# ---------------------------------------------------------------------------
# Negative schema tests (in-memory mutations of valid documents)
# ---------------------------------------------------------------------------


def test_duplicate_paper_id_is_rejected(corpus_dict: dict) -> None:
    corpus_dict["papers"][1]["paper_id"] = corpus_dict["papers"][0]["paper_id"]
    with pytest.raises(em.EvidenceMapError, match="重复"):
        em.parse_corpus(corpus_dict)


def test_duplicate_doi_is_case_insensitive(corpus_dict: dict) -> None:
    corpus_dict["papers"][1]["doi"] = corpus_dict["papers"][0]["doi"].upper()
    with pytest.raises(em.EvidenceMapError, match="DOI"):
        em.parse_corpus(corpus_dict)


def test_empty_license_is_rejected(corpus_dict: dict) -> None:
    corpus_dict["papers"][0]["license"] = ""
    with pytest.raises(em.EvidenceMapError, match="license"):
        em.parse_corpus(corpus_dict)


def test_unknown_license_with_oa_is_rejected(corpus_dict: dict) -> None:
    corpus_dict["papers"][0]["license"] = "unknown"
    with pytest.raises(em.EvidenceMapError, match="license"):
        em.parse_corpus(corpus_dict)


def test_fulltext_without_oa_is_rejected(corpus_dict: dict) -> None:
    corpus_dict["papers"][0]["is_oa"] = False
    with pytest.raises(em.EvidenceMapError, match="fulltext_available"):
        em.parse_corpus(corpus_dict)


def test_paper_topic_must_match_manifest(topic: str, corpus_dict: dict) -> None:
    other = "medical_imaging" if topic == "ai_education" else "ai_education"
    corpus_dict["papers"][0]["topic_id"] = other
    with pytest.raises(em.EvidenceMapError, match="topic_id"):
        em.parse_corpus(corpus_dict)


def test_unknown_field_is_rejected(corpus_dict: dict) -> None:
    corpus_dict["papers"][0]["pdf_bytes"] = "not allowed"
    with pytest.raises(em.EvidenceMapError, match="未知字段"):
        em.parse_corpus(corpus_dict)


def test_missing_required_field_is_rejected(corpus_dict: dict) -> None:
    del corpus_dict["papers"][0]["doi"]
    with pytest.raises(em.EvidenceMapError, match="缺失"):
        em.parse_corpus(corpus_dict)


def test_schema_version_mismatch_is_rejected(corpus_dict: dict) -> None:
    corpus_dict["schema_version"] = "0.9"
    with pytest.raises(em.EvidenceMapError, match="schema_version"):
        em.parse_corpus(corpus_dict)


def test_invalid_stance_is_rejected(map_dict: dict, corpus: em.CorpusManifest) -> None:
    map_dict["evidence"][0]["stance"] = "supports"
    with pytest.raises(em.EvidenceMapError, match="stance"):
        em.parse_map(map_dict, corpus=corpus)


def test_unknown_claim_reference_is_rejected(map_dict: dict, corpus: em.CorpusManifest) -> None:
    map_dict["evidence"][0]["claim_id"] = "edu-c999"
    with pytest.raises(em.EvidenceMapError, match="未知 claim"):
        em.parse_map(map_dict, corpus=corpus)


def test_unknown_gap_claim_reference_is_rejected(map_dict: dict, corpus: em.CorpusManifest) -> None:
    map_dict["gaps"][0]["related_claim_ids"] = ["edu-c999"]
    with pytest.raises(em.EvidenceMapError, match="未知 claim"):
        em.parse_map(map_dict, corpus=corpus)


def test_quote_without_locator_is_rejected(map_dict: dict, corpus: em.CorpusManifest) -> None:
    map_dict["evidence"][0]["locator"] = ""
    with pytest.raises(em.EvidenceMapError, match="locator"):
        em.parse_map(map_dict, corpus=corpus)


def test_sample_size_mismatch_is_rejected(map_dict: dict, corpus: em.CorpusManifest) -> None:
    map_dict["evidence"][0]["method"]["sample_size"] += 1
    with pytest.raises(em.EvidenceMapError, match="不一致"):
        em.parse_map(map_dict, corpus=corpus)


def test_confidence_out_of_range_is_rejected(map_dict: dict, corpus: em.CorpusManifest) -> None:
    map_dict["evidence"][0]["confidence"] = 1.5
    with pytest.raises(em.EvidenceMapError, match="confidence"):
        em.parse_map(map_dict, corpus=corpus)


def test_duplicate_json_keys_are_rejected(tmp_path) -> None:
    path = tmp_path / "dupe.json"
    path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    with pytest.raises(em.EvidenceMapError, match="重复键"):
        em.read_json(path)


def test_invalid_json_reports_location(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"a": ', encoding="utf-8")
    with pytest.raises(em.EvidenceMapError, match="JSON 解析失败"):
        em.read_json(path)


# ---------------------------------------------------------------------------
# Index safety
# ---------------------------------------------------------------------------


def _index_with_entry(corpus: str, extractions: str = "extractions/x.json") -> dict:
    return {
        "schema_version": em.SCHEMA_VERSION,
        "topics": [
            {
                "topic_id": "ai_education",
                "name_zh": "人工智能教育",
                "name_en": "AI in Education",
                "question": "q",
                "corpus": corpus,
                "extractions": extractions,
            }
        ],
    }


def test_index_rejects_path_traversal(tmp_path) -> None:
    (tmp_path / "index.json").write_text(
        json.dumps(_index_with_entry("../outside.json")), encoding="utf-8"
    )
    with pytest.raises(em.EvidenceMapError, match="越界"):
        em.list_topics(tmp_path)


def test_index_rejects_absolute_paths(tmp_path) -> None:
    (tmp_path / "index.json").write_text(
        json.dumps(_index_with_entry(str(tmp_path / "corpus.json"))), encoding="utf-8"
    )
    with pytest.raises(em.EvidenceMapError, match="绝对路径"):
        em.list_topics(tmp_path)


def test_index_rejects_duplicate_topic_ids(tmp_path) -> None:
    index = _index_with_entry("corpus/a.json")
    index["topics"].append(dict(index["topics"][0]))
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(em.EvidenceMapError, match="重复"):
        em.list_topics(tmp_path)


def test_index_requires_topic_fields(tmp_path) -> None:
    index = _index_with_entry("corpus/a.json")
    del index["topics"][0]["question"]
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(em.EvidenceMapError, match="缺少字段"):
        em.list_topics(tmp_path)
