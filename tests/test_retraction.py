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
