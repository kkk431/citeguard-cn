from __future__ import annotations

from citeguard.metadata_verify import Candidate, _version_dict
from citeguard.reference_parser import Reference


def test_verify_result_version_annotation_is_optional_and_serialisable():
    ref = Reference(raw="x", authors=["Vaswani, Ashish"], title="Attention Is All You Need", year=2017)
    cands = [
        Candidate(source="arxiv", title="Attention Is All You Need", year=2017,
                  authors=["Vaswani, Ashish"], url="https://arxiv.org/abs/1706.03762"),
        Candidate(source="openalex", title="Attention Is All You Need", doi="10.5555/3295222",
                  year=2019, authors=["Vaswani, Ashish"], venue="NeurIPS"),
    ]
    version = _version_dict(ref, cands)
    assert version["status"] in {"version_family", "same_version"}
    assert version["provenance"]
    assert "chosen" in version
