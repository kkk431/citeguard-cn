import copy

import pytest

from citeguard.fix import (
    REPAIR_SCHEMA,
    apply_patch,
    as_text,
    build_patch,
    fix_entry,
    fix_report,
    repair_state,
    revert_patch,
    undo_patch,
)


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


def _report(*titles):
    """Build a report whose references carry stable 1..N numbers."""
    refs = []
    for index, title in enumerate(titles, 1):
        ref = _ref(title=title)
        ref["index"] = index
        ref["raw"] = (
            f"[{index}] ZHANG San; LI Si. {title}. "
            "Journal of Tests, 2020, 12 (3): 45-50"
        )
        refs.append(ref)
    return {"references": refs}


def test_build_patch_batch_returns_before_after_and_reversible_ops():
    report = _report("First study", "Second study", "Third study")

    patch = build_patch(report)

    assert patch["schema"] == REPAIR_SCHEMA
    assert patch["reversible"] is True
    assert patch["patch_id"].startswith("rp-")
    assert patch["indexes"] == [1, 2, 3]
    assert [item["index"] for item in patch["before"]] == [1, 2, 3]
    assert [item["index"] for item in patch["after"]] == [1, 2, 3]
    assert len(patch["entries"]) == 3
    assert patch["summary"]["total"] == 3
    assert patch["summary"]["selected"] == 3
    assert patch["summary"]["to_apply"] == 3
    assert all(op["op"] == "set_repair" for op in patch["ops"])
    assert [op["index"] for op in patch["ops"]] == [1, 2, 3]

    # The patch document is derived from the report but never mutates it.
    assert "repair" not in report["references"][0]

    # The character diff carries both sides and rebuilds each text exactly.
    diff = patch["entries"][0]["diff"]
    assert any(segment["op"] != "equal" for segment in diff)
    assert "".join(segment["before"] for segment in diff) == patch["entries"][0]["before"]
    assert "".join(segment["after"] for segment in diff) == patch["entries"][0]["after"]


def test_build_patch_single_index_touches_only_that_entry():
    report = _report("First study", "Second study", "Third study")

    patch = build_patch(report, [2])
    repaired = apply_patch(report, patch)

    assert patch["indexes"] == [2]
    assert [entry["index"] for entry in patch["entries"]] == [2]
    assert len(patch["ops"]) == 1 and patch["ops"][0]["index"] == 2
    assert "repair" not in repaired["references"][0]
    assert repaired["references"][1]["repair"]["state"] == "fixed"
    assert repaired["references"][1]["repair"]["after"] == patch["entries"][0]["after"]
    assert repaired["references"][1]["repair"]["patch_id"] == patch["patch_id"]
    assert "repair" not in repaired["references"][2]
    assert repair_state(repaired)["state"] == "partially_fixed"

    # A repeated number in the request is selected once, in report order.
    assert build_patch(report, [2, 2])["indexes"] == [2]


def test_apply_then_undo_restores_the_original_report():
    report = _report("First study", "Second study")
    snapshot = copy.deepcopy(report)
    patch = build_patch(report)

    repaired = apply_patch(report, patch)

    # apply_patch returns a new report and leaves the input untouched.
    assert report == snapshot
    assert repaired != report
    assert repaired["references"][0]["raw"] == snapshot["references"][0]["raw"]
    assert repaired["references"][0]["parsed"] == snapshot["references"][0]["parsed"]
    assert repaired["references"][0]["repair"]["state"] == "fixed"
    assert repair_state(repaired)["state"] == "fixed"
    assert repair_state(repaired)["fixed"] == 2

    restored = undo_patch(repaired, patch)
    assert restored == snapshot
    assert repair_state(restored)["state"] == "unfixed"
    assert undo_patch(restored, patch) == snapshot  # undo is idempotent
    assert revert_patch(repaired, patch) == snapshot
    assert undo_patch(repaired) == snapshot  # undo everything


def test_apply_patch_is_idempotent_and_rejects_stale_patches():
    report = _report("First study", "Second study")
    patch = build_patch(report)

    once = apply_patch(report, patch)
    twice = apply_patch(once, patch)
    assert twice == once
    assert apply_patch(report, patch) == once  # same patch, same result

    # Rebuilding on an already-fixed report reports nothing left to apply.
    follow_up = build_patch(once)
    assert follow_up["summary"]["to_apply"] == 0
    assert follow_up["summary"]["already_fixed"] == 2
    assert apply_patch(once, follow_up) == once

    # A patch built for different reference text is stale and must be rejected.
    edited = copy.deepcopy(report)
    edited["references"][0]["raw"] = "[1] a different reference text"
    with pytest.raises(ValueError, match="过期"):
        apply_patch(edited, patch)

    # Undo is also blocked once the report changed after the patch was applied.
    repaired = apply_patch(report, patch)
    repaired["references"][0]["parsed"]["year"] = 2021
    with pytest.raises(ValueError, match="撤销窗口"):
        undo_patch(repaired, patch)


def test_invalid_reference_index_is_rejected():
    report = _report("First study", "Second study")

    for bad in ([0], [-1], [3], ["1"], [True], ["x"]):
        with pytest.raises(ValueError):
            build_patch(report, bad)
    with pytest.raises(ValueError):
        build_patch(report, 2)  # not a list
    with pytest.raises(ValueError):
        build_patch({"references": ["not-a-reference"]})

    # A hand-edited patch pointing at a missing reference is rejected.
    bad_patch = copy.deepcopy(build_patch(report))
    bad_patch["ops"][0]["index"] = 99
    with pytest.raises(ValueError, match="99"):
        apply_patch(report, bad_patch)

    # undo validates explicit numbers against the current report.
    repaired = apply_patch(report, build_patch(report))
    with pytest.raises(ValueError, match="99"):
        undo_patch(repaired, indexes=[99])
