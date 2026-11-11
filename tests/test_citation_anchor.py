"""正文引用句抽取测试（Phase 1）。"""

from citeguard.citation_anchor import Citation, extract_citations, summarize


def _nums(cites: list[Citation]) -> list[list[int]]:
    return [c.ref_numbers for c in cites]


def test_single_numeric():
    cites = extract_citations("已有研究表明这一点[12]。")
    assert len(cites) == 1
    assert cites[0].style == "numeric"
    assert cites[0].ref_numbers == [12]
    assert "已有研究表明这一点" in cites[0].sentence


def test_numeric_list_and_range():
    text = "方法见[3,5]与[8-10]，另有[2, 4]。"
    cites = extract_citations(text)
    assert [c.ref_numbers for c in cites] == [[3, 5], [8, 9, 10], [2, 4]]


def test_chinese_wenxian():
    cites = extract_citations("如文献[7]所述，文献 12 也持同样观点。")
    assert [c.style for c in cites] == ["chinese", "chinese"]
    assert [c.ref_numbers for c in cites] == [[7], [12]]


def test_author_year():
    cites = extract_citations(
        "The result (Smith et al., 2020) was later replicated.")
    assert len(cites) == 1
    assert cites[0].style == "author_year"
    assert cites[0].ref_numbers == []
    assert "Smith et al., 2020" in cites[0].key


def test_two_author_year():
    cites = extract_citations("见 (Smith & Jones, 2019)。")
    assert len(cites) == 1
    assert cites[0].style == "author_year"


def test_cn_author_year():
    cites = extract_citations("有研究指出这一点（张三，2020），也有不同结论。")
    assert len(cites) == 1
    assert cites[0].style == "cn_author_year"


def test_sentence_context_is_sentence_only():
    text = "第一句无关。第二句引用文献[4]，后面还有文字。第三句结束。"
    cites = extract_citations(text)
    assert len(cites) == 1
    assert cites[0].sentence.startswith("第二句引用文献")
    assert "第一句" not in cites[0].sentence
    assert "第三句" not in cites[0].sentence


def test_repeated_marker_kept_once_per_position():
    text = "文献[2]说 A；文献[2]又说 B。"
    cites = extract_citations(text)
    assert len(cites) == 2


def test_no_citation_plain_text():
    assert extract_citations("这段文字没有任何引用标记。") == []
    assert extract_citations("") == []


def test_out_of_range_numbers_dropped():
    cites = extract_citations("异常标记[0]、[999]与[500]。")
    assert all(1 <= n <= 300 for c in cites for n in c.ref_numbers)


def test_summary_counts():
    text = "文献[1]与[2,3]；另见 (Smith, 2021)。"
    s = summarize(extract_citations(text))
    assert s["total"] == 3
    assert s["by_style"]["numeric"] == 1
    assert s["by_style"]["chinese"] == 1
    assert s["ref_numbers"] == [1, 2, 3]
    assert s["sentences"] == 2  # 分号按句界处理


def test_cli_smoke(tmp_path, capsys):
    from citeguard import citation_anchor

    p = tmp_path / "body.txt"
    p.write_text("文献[5]表明该方法有效。", encoding="utf-8")
    assert citation_anchor.main([str(p)]) == 0
    out = capsys.readouterr().out
    assert '"total": 1' in out
    assert '"ref_numbers": [' in out


def test_pipeline_report_payload():
    from citeguard.pipeline import _citations_payload

    payload = _citations_payload("文献[3]支持该结论，另有[4-5]不同。")
    assert payload["summary"]["total"] == 2
    assert payload["items"][0]["ref_numbers"] == [3]
    assert payload["items"][1]["ref_numbers"] == [4, 5]
    assert payload["truncated"] is False
