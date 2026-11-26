"""Tests for the semi-automatic CiteMap expansion spike (E3).

The tests use the real, machine-safe ``ai_education`` corpus for generation and
a temporary copy of its extraction file for the one write test.  The canonical
human layer must remain untouched by generation.
"""
from __future__ import annotations

import copy
import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import citemap_expand as ce  # noqa: E402
from citeguard import evidence_map  # noqa: E402

DATA = ROOT / "data" / "evidence_map"
TOPIC = "ai_education"


@pytest.fixture(scope="module")
def bundle() -> dict:
    return ce.generate_candidates(TOPIC, data_dir=DATA, limit=15, min_candidates=5)


@pytest.fixture()
def tmp_topic(tmp_path: Path) -> Path:
    """Copy just the files needed to validate/write one topic into tmp."""
    root = tmp_path / "evidence_map"
    (root / "corpus").mkdir(parents=True)
    (root / "extractions").mkdir(parents=True)
    shutil.copy2(DATA / "corpus" / f"{TOPIC}.json", root / "corpus" / f"{TOPIC}.json")
    shutil.copy2(DATA / "extractions" / f"{TOPIC}.json", root / "extractions" / f"{TOPIC}.json")
    return root


def _candidate(bundle: dict) -> dict:
    return copy.deepcopy(bundle["candidates"][0])


def test_generate_candidates_from_existing_topic(bundle: dict) -> None:
    candidates = bundle["candidates"]
    assert bundle["mode"] == "existing-topic"
    assert len(candidates) >= 5
    assert bundle["counts"]["candidates"] == len(candidates)
    seen_ids: set[str] = set()
    seen_claims: set[str] = set()
    for candidate in candidates:
        assert candidate["machine"] is True
        assert candidate["needs_human"] is True
        assert candidate["candidate_type"] == "new_claim"
        assert candidate["status"] == "pending"
        assert candidate["candidate_id"] not in seen_ids
        assert candidate["claim_id"] not in seen_claims
        seen_ids.add(candidate["candidate_id"])
        seen_claims.add(candidate["claim_id"])
        assert candidate["quote"] == candidate["claim"]
        assert candidate["quote"] in candidate["source_text"]
        assert candidate["paper"]["doi"]
        assert candidate["locator"] == "Abstract"
        assert candidate["stance"] in evidence_map.STANCES


def test_generation_does_not_touch_human_layer(bundle: dict, tmp_path: Path) -> None:
    extraction = DATA / "extractions" / f"{TOPIC}.json"
    before = extraction.read_bytes()
    out = tmp_path / "expansion"
    written = ce.write_outputs(bundle, output_dir=out)
    after = extraction.read_bytes()
    assert before == after
    assert Path(written["candidates"]).exists()
    assert Path(written["review_csv"]).exists()
    payload = json.loads(Path(written["candidates"]).read_text(encoding="utf-8"))
    assert all(item["machine"] and item["needs_human"] for item in payload["candidates"])
    with Path(written["review_csv"]).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(bundle["candidates"])
    assert {row["decision"] for row in rows} == {""}
    assert {row["note"] for row in rows} == {""}


def test_promote_requires_a_real_confirmation(bundle: dict) -> None:
    candidate = _candidate(bundle)
    with pytest.raises(ce.ExpandError):
        ce.promote_candidate(candidate, decision="", data_dir=DATA)
    with pytest.raises(ce.ExpandError):
        ce.promote_candidate(candidate, decision="pending", data_dir=DATA)
    rejected = ce.promote_candidate(candidate, decision="reject", data_dir=DATA)
    assert rejected.accepted is False
    assert rejected.written is False


def test_promote_builds_valid_patch_without_writing_human_layer(
    bundle: dict, tmp_path: Path
) -> None:
    candidate = _candidate(bundle)
    extraction = DATA / "extractions" / f"{TOPIC}.json"
    before = extraction.read_bytes()
    promotion = ce.promote_candidate(
        candidate,
        decision="accept",
        note="测试确认",
        reviewer="tester",
        data_dir=DATA,
        output_dir=tmp_path / "promotions",
        write_human_layer=False,
    )
    assert promotion.accepted is True
    assert promotion.written is False
    assert promotion.path is not None and promotion.path.exists()
    assert promotion.patch["human_layer_written"] is False
    assert promotion.patch["evidence"]["verified"] is True
    assert promotion.patch["evidence"]["extracted_by"] == "human:promoted-candidate"
    assert promotion.patch["evidence"]["quote"] == candidate["quote"]
    assert extraction.read_bytes() == before
    # The produced objects must already satisfy the canonical schema.
    evidence_map.Claim.from_dict(promotion.patch["claim"])
    evidence_map.Evidence.from_dict(promotion.patch["evidence"])


def test_promote_writes_only_after_explicit_flag(bundle: dict, tmp_topic: Path) -> None:
    candidate = _candidate(bundle)
    original = evidence_map.load_map(tmp_topic / "extractions" / f"{TOPIC}.json")
    before_count = len(original.evidence)
    promotion = ce.promote_candidate(
        candidate,
        decision="accept",
        reviewer="tester",
        data_dir=tmp_topic,
        write_human_layer=True,
    )
    assert promotion.written is True
    corpus = evidence_map.load_corpus(tmp_topic / "corpus" / f"{TOPIC}.json")
    updated = evidence_map.load_map(
        tmp_topic / "extractions" / f"{TOPIC}.json", corpus=corpus
    )
    assert len(updated.evidence) == before_count + 1
    assert any(item.evidence_id == promotion.patch["evidence"]["evidence_id"] for item in updated.evidence)
    assert any(item.claim_id == candidate["claim_id"] for item in updated.claims)
    # A second promotion of the same candidate must not silently duplicate it.
    with pytest.raises(ce.ExpandError):
        ce.promote_candidate(
            candidate,
            decision="accept",
            reviewer="tester",
            data_dir=tmp_topic,
            write_human_layer=True,
        )


def test_tampered_quote_is_rejected_and_generation_dedupes(bundle: dict) -> None:
    candidate = _candidate(bundle)
    candidate["quote"] = "This exact quote does not occur in the abstract."
    candidate["claim"] = candidate["quote"]
    with pytest.raises(ce.ExpandError, match="逐字"):
        ce.promote_candidate(candidate, decision="accept", data_dir=DATA)

    second = ce.generate_candidates(TOPIC, data_dir=DATA, limit=15, min_candidates=1)
    quotes = [item["quote"] for item in second["candidates"]]
    assert len(quotes) == len(set(quotes))


def test_promote_rejects_duplicate_claim_id(bundle: dict, tmp_topic: Path) -> None:
    candidate = _candidate(bundle)
    candidate["claim_id"] = "edu-c1"
    candidate["claim"] = "与既有断言相同的文本"
    with pytest.raises(ce.ExpandError, match="已存在"):
        ce.promote_candidate(
            candidate, decision="accept", data_dir=tmp_topic, output_dir=tmp_topic / "promotions"
        )
    original = evidence_map.load_map(tmp_topic / "extractions" / f"{TOPIC}.json")
    assert not any(item.claim_id == "edu-c1" and item.text == candidate["claim"] for item in original.claims)


def test_empty_invalid_inputs_raise() -> None:
    with pytest.raises(ce.ExpandError):
        ce.generate_candidates("topic_does_not_exist", data_dir=DATA, min_candidates=1)
    with pytest.raises(ce.ExpandError):
        ce.generate_candidates(TOPIC, data_dir=DATA, limit=1, min_candidates=2)
    with pytest.raises(ce.ExpandError):
        ce.generate_candidates(TOPIC, data_dir=DATA, works=[], min_candidates=1)
