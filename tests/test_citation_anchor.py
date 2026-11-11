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



def test_footnote_markers():
    items = extract_citations("见[^12]和^[7]，另见[3-5]。")
    notes = [c for c in items if c.style == "footnote"]
    assert [c.ref_numbers for c in notes] == [[12], [7]]
    numeric = [c for c in items if c.style == "numeric"]
    assert [c.ref_numbers for c in numeric] == [[3, 4, 5]]


def test_footnote_definition_not_treated_as_citation():
    items = extract_citations("[^12]: 这是一条脚注定义。")
    assert items == []


def test_summary_includes_footnote_style():
    items = extract_citations("见[^3]。")
    summary = summarize(items)
    assert summary["by_style"]["footnote"] == 1
    assert summary["ref_numbers"] == [3]


def test_coverage_counts_only_cited_numbers():
    from citeguard.citation_anchor import Citation, coverage

    items = [
        Citation("[1]", "numeric", [1], "s1", 0, 3),
        Citation("[2,4]", "numeric", [2, 4], "s2", 5, 11),
        Citation("[99]", "numeric", [99], "s3", 12, 16),
    ]
    cov = coverage(items, 5)
    assert cov["refs"] == 5
    assert cov["cited"] == 3
    assert cov["uncited"] == [3, 5]
    assert cov["ratio"] == 0.6

def test_coverage_resolves_author_year():
    from types import SimpleNamespace

    from citeguard.citation_anchor import Citation, coverage

    cites = [Citation(key="Smith et al., 2020", style="author_year", ref_numbers=[], sentence="Smith et al., 2020 show it.", start=0, end=18)]
    refs = [
        SimpleNamespace(authors=["Smith, J."], year="2020"),
        SimpleNamespace(authors=["Lee, A."], year="2019"),
    ]
    cov = coverage(cites, refs)
    assert cov["cited"] == 1
    assert cov["uncited"] == [2]

def test_find_page_normalizes_whitespace():
    from citeguard.citation_anchor import find_page

    assert find_page("Alpha  Beta\nGamma", ["x", "alpha beta gamma"]) == 2
    assert find_page("nothing here", ["x"]) == 0


def test_caption_mentions_cjk():
    from citeguard.citation_anchor import extract_caption_mentions
    items = extract_caption_mentions("如图 3 所示，模型在表 2 中给出结果；图 3 再次出现。")
    assert [i["label"] for i in items] == ["图 3", "表 2"]
    assert items[0]["count"] == 2
    assert "图 3" in items[0]["sentence"]


def test_caption_mentions_english():
    from citeguard.citation_anchor import extract_caption_mentions
    items = extract_caption_mentions("As shown in Fig. 2 and Table 3.")
    assert {i["label"] for i in items} == {"Figure 2", "Table 3"}


def test_citations_payload_includes_captions():
    from citeguard.pipeline import _citations_payload
    payload = _citations_payload("如图 1 所示，见文献[2]。", [object()], limit=5)
    assert payload["captions"]["unique"] == 1
    assert payload["captions"]["items"][0]["label"] == "图 1"


def test_caption_mentions_ignores_word_table():
    from citeguard.citation_anchor import extract_caption_mentions
    items = extract_caption_mentions("作者共发表 1~2 篇相关论文，代表 3 种观点。")
    assert items == []


def test_caption_mentions_numbered_subsection_not_caption():
    from citeguard.citation_anchor import extract_caption_mentions
    items = extract_caption_mentions("图 3.3 作者与合作分布")
    assert items == []
