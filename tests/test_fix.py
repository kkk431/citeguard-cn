from citeguard.fix import as_text, fix_entry, fix_report


def _ref(**parsed):
    base = {
        "title": "A study of citation practice",
        "authors": ["ZHANG San", "LI Si"],
        "doc_type": "J",
        "venue": "Journal of Tests",
        "year": 2020,
        "volume": "12",
        "issue": "3",
        "pages": "45-50",
    }
    base.update(parsed)
    return {
        "index": 1,
        "raw": "[1] ZHANG San; LI Si. A study of citation practice. Journal of Tests, 2020, 12 (3): 45-50",
        "parsed": base,
    }


def test_fix_entry_retypesets_and_reports_changes():
    item = fix_entry(1, _ref())
    assert "[J]" in item["after"]
    assert item["after"].endswith("45-50.")
    assert item["safe"] is True
    assert item["changed"] is True
    assert "补文献类型码" in item["fixes"]
    assert "作者分隔符统一为逗号" in item["fixes"]


def test_venue_tail_volume_and_pages_are_not_duplicated():
    ref = _ref(venue="Journal of Tests, 12, 45-50", volume="", issue="", pages="45-50")
    after = fix_entry(1, ref)["after"]
    assert after.count("45-50") == 1
    assert "2020, 12: 45-50." in after


def test_article_id_becomes_article_number():
    ref = _ref(
        venue="Expert Systems with Applications, 238, Article ID: 121801",
        volume="",
        issue="",
        pages="238",
    )
    after = fix_entry(1, ref)["after"]
    assert "2020, 238: 121801." in after
    assert "Article ID" not in after


def test_fix_entry_is_not_safe_without_title_or_authors():
    no_title = fix_entry(1, _ref(title=""))
    assert no_title["safe"] is False
    assert "题名" in no_title["missing"]
    no_authors = fix_entry(1, _ref(authors=[]))
    assert no_authors["safe"] is False
    assert "作者" in no_authors["missing"]


def test_fix_report_counts_changed_and_safe_entries():
    report = {
        "references": [
            _ref(),
            _ref(title="", raw="[2] broken"),
        ]
    }
    fixed = fix_report(report)
    assert fixed["summary"]["total"] == 2
    assert fixed["summary"]["changed"] == 2
    assert fixed["summary"]["safe"] == 1
    assert fixed["summary"]["with_missing"] == 1


def test_as_text_marks_incomplete_entries():
    fixed = fix_report({"references": [_ref(), _ref(title="")]})
    text = as_text(fixed)
    assert "[1]" in text and "[2] *" in text
    assert "未补全缺失字段" in text
