from __future__ import annotations

from pathlib import Path

import pytest

from citeguard.tech_eval import HarnessError, check, collect, to_markdown


def test_collects_the_frozen_batch0_samples():
    card = collect()
    sections = card["sections"]
    assert sections["support_human_100"]["n"] == 100
    assert sections["real_references_409"]["n"] == 409
    assert sections["real_references_409"]["status"]["Major"] == 0
    assert sections["parse_529"]["pdf_refs"] == 529
    assert sections["citemap_105"]["cells"] == 105
    assert sections["fulltext_25_of_30"]["papers"] == 25
    assert sections["fulltext_25_of_30"]["papers_total"] == 30
    assert not check(card)


def test_the_constant_majority_baseline_is_lower_than_the_product():
    card = collect()
    human = card["sections"]["support_human_100"]
    baseline = human["constant_majority_baseline"]
    assert baseline["label"] in {"support", "partial", "contradict", "no_evidence"}
    assert baseline["macro_f1"] < human["macro_f1"]


def test_markdown_has_the_expected_required_rows():
    md = to_markdown(collect())
    for name in ("support_human_100", "real_references_409", "parse_529", "citemap_105", "fulltext_25_of_30"):
        assert name in md
    assert "门禁" in md


def test_missing_source_raises_a_readable_error(tmp_path: Path):
    with pytest.raises(HarnessError, match="missing evaluation source"):
        collect(tmp_path)
