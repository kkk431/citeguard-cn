import citeguard.retraction as retraction


def test_normalise_doi_accepts_url_and_prefix():
    assert retraction.normalise_doi("https://doi.org/10.1000/XYZ.1") == "10.1000/XYZ.1"
    assert retraction.normalise_doi("doi: 10.1000/xyz") == "10.1000/xyz"


def test_retracted_work_is_flagged(monkeypatch):
    monkeypatch.setattr(
        retraction,
        "_cached_json",
        lambda url: {"is_retracted": True, "title": "Old paper"} if "openalex" in url else None,
    )
    result = retraction.check_doi("10.1000/retracted")
    assert result["status"] == "retracted"
    assert result["title"] == "Old paper"


def test_crossref_update_relation_marks_corrected(monkeypatch):
    def fake(url):
        if "openalex" in url:
            return {"is_retracted": False, "title": "Paper"}
        return {"message": {"relation": {"updated-by": [{"id": "x"}]}, "title": ["Paper"]}}

    monkeypatch.setattr(retraction, "_cached_json", fake)
    result = retraction.check_doi("10.1000/corrected")
    assert result["status"] == "corrected"
    assert result["source"] == "crossref"


def test_clean_and_error_are_distinct(monkeypatch):
    monkeypatch.setattr(
        retraction, "_cached_json", lambda url: {"is_retracted": False, "title": "Fine"}
    )
    assert retraction.check_doi("10.1000/fine", check_corrections=False)["status"] == "clean"
    monkeypatch.setattr(retraction, "_cached_json", lambda url: None)
    assert retraction.check_doi("10.1000/down")["status"] == "error"


def test_chain_detects_an_indirectly_cited_retraction(monkeypatch):
    def fake(url):
        if "/works/doi:" in url:
            return {
                "title": "Citing paper",
                "referenced_works": [
                    "https://openalex.org/W111",
                    "https://openalex.org/W222",
                    "https://openalex.org/W333",
                ],
            }
        return {
            "results": [
                {
                    "id": "https://openalex.org/W111",
                    "doi": "https://doi.org/10.1/old",
                    "title": "Retracted paper",
                    "is_retracted": True,
                },
                {
                    "id": "https://openalex.org/W222",
                    "doi": "https://doi.org/10.1/fine",
                    "title": "Fine paper",
                    "is_retracted": False,
                },
            ]
        }

    monkeypatch.setattr(retraction, "_cached_json", fake)
    result = retraction.check_chain("10.1/citing", max_refs=5)
    assert result["status"] == "indirect"
    assert result["sampled"] == 3
    assert result["checked"] == 2
    assert result["coverage"] == 0.667  # 3 sampled, 2 returned by OpenAlex
    assert result["retracted"][0]["title"] == "Retracted paper"


def test_chain_is_honest_when_references_are_missing(monkeypatch):
    monkeypatch.setattr(
        retraction,
        "_cached_json",
        lambda url: {"title": "No refs", "referenced_works": []},
    )
    result = retraction.check_chain("10.1/norefs")
    assert result["status"] == "no_references"
    assert result["coverage"] == 0.0
    assert result["retracted"] == []


def test_chain_batch_failure_is_an_error_not_a_clean_bill(monkeypatch):
    def fake(url):
        if "/works/doi:" in url:
            return {"title": "Citing paper", "referenced_works": ["W1"]}
        return None

    monkeypatch.setattr(retraction, "_cached_json", fake)
    result = retraction.check_chain("10.1/down")
    assert result["status"] == "error"
    assert result["checked"] == 0


def test_summarize_chain_counts_and_coverage():
    summary = retraction.summarize_chain(
        [
            {"status": "indirect", "checked": 2, "coverage": 1.0, "retracted": [{"id": "W1"}]},
            {"status": "clean", "checked": 1, "coverage": 0.5, "retracted": []},
            {"status": "no_references", "checked": 0, "coverage": 0.0, "retracted": []},
            {"status": "error", "checked": 0, "coverage": 0.0, "retracted": []},
        ]
    )
    assert summary["checked"] == 4
    assert summary["references_checked"] == 3
    assert summary["retracted_found"] == 1
    assert summary["indirect"] == 1
    assert summary["average_coverage"] == 0.75


def test_summarize_counts_statuses():
    summary = retraction.summarize(
        [
            {"status": "retracted"},
            {"status": "corrected"},
            {"status": "clean"},
            {"status": "error"},
            {"status": "clean"},
        ]
    )
    assert summary == {"checked": 5, "retracted": 1, "corrected": 1, "clean": 2, "error": 1}


def test_pipeline_only_checks_matched_references_with_doi(monkeypatch):
    from citeguard import pipeline

    calls = []

    def fake(doi, check_corrections=True):
        calls.append(doi)
        return {"status": "clean", "source": "openalex", "title": "", "detail": ""}

    monkeypatch.setattr("citeguard.retraction.check_doi", fake)
    report = {
        "references": [
            {"parsed": {"doi": "10.1/a"}, "verify": {"status": "Exact"}},
            {"parsed": {"doi": "10.1/b"}, "verify": {"status": "Unverified"}},
            {"parsed": {}, "verify": {"status": "Exact"}},
        ]
    }
    pipeline._attach_retractions(report)
    assert calls == ["10.1/a"]
    assert report["retractions"]["checked"] == 1
    assert "retraction" not in report["references"][1]


def test_chain_two_hop_finds_retraction_one_layer_down(monkeypatch):
    def fake(url):
        if "/works/doi:" in url:
            return {"title": "Citing paper", "referenced_works": ["W1", "W2"]}
        if "W9%7CW10" in url or "W9|W10" in url:
            return {"results": [{"id": "W9", "title": "Retracted downstream", "is_retracted": True}]}
        return {"results": [
            {"id": "W1", "title": "Clean middle", "is_retracted": False, "referenced_works": ["W9"]},
            {"id": "W2", "title": "Clean middle 2", "is_retracted": False, "referenced_works": ["W10"]},
        ]}

    monkeypatch.setattr(retraction, "_cached_json", fake)
    result = retraction.check_chain("10.1/twohop", max_refs=5, max_hops=2, hop2_limit=2)
    assert result["status"] == "indirect"
    assert result["retracted"] == []
    assert result["second_sampled"] == 2
    assert result["second_degree"][0]["id"] == "W9"
    assert result["max_hops"] == 2
