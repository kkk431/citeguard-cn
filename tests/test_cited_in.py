"""cited_in mapping: reference ↔ body citation traceability."""


def test_attach_cited_in_maps_numbers_and_pages():
    from citeguard.pipeline import _attach_cited_in
    report = {
        "references": [{"index": 1}, {"index": 2}, {"index": 3}],
        "citations": {"items": [
            {"key": "[2]", "ref_numbers": [2], "sentence": "见文献[2]。", "page": 4},
            {"key": "[9]", "ref_numbers": [9], "sentence": "越界编号", "page": 1},
        ]},
    }
    _attach_cited_in(report)
    assert report["references"][1]["cited_in"] == [
        {"key": "[2]", "page": 4, "sentence": "见文献[2]。"}
    ]
    assert report["references"][0]["cited_in"] == []
    assert report["references"][2]["cited_in"] == []


def test_attach_cited_in_dedupes_sentences_and_caps():
    from citeguard.pipeline import _attach_cited_in
    items = [
        {"key": "[1]", "ref_numbers": [1], "sentence": "同一句话。", "page": 2},
        {"key": "[1]", "ref_numbers": [1], "sentence": "同一句话。", "page": 2},
    ] + [
        {"key": "[1]", "ref_numbers": [1], "sentence": f"第{i}句。", "page": 3} for i in range(8)
    ]
    report = {"references": [{}], "citations": {"items": items}}
    _attach_cited_in(report)
    got = report["references"][0]["cited_in"]
    assert len(got) == 5
    assert got[0]["sentence"] == "同一句话。"
