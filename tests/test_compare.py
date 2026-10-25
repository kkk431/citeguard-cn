"""Unit tests for the multi-paper comparison module (no network)."""
from __future__ import annotations

import json

import pytest

from citeguard import compare


def _long_body(chars: int = 6000) -> str:
    return "标题：一篇论文\n摘要：本文研究了一个问题。" + "正文内容。" * (chars // 5)


def test_excerpt_cuts_reference_list_and_caps():
    text = _long_body(9000) + " 参考文献\n[1] 张三. 测试[J]. 2020."
    excerpt = compare._excerpt(text)
    assert len(excerpt) <= compare.EXCERPT_CHARS
    assert "参考文献" not in excerpt


def test_excerpt_keeps_short_text():
    text = "标题\n摘要：很短。"
    assert compare._excerpt(text) == "标题 摘要：很短。"


def test_extract_profile_requires_judge(monkeypatch):
    monkeypatch.setattr(compare, "judge_available", lambda: False)
    with pytest.raises(compare.CompareError, match="判官"):
        compare.extract_profile(_long_body())


def test_extract_profile_rejects_short_text(monkeypatch):
    monkeypatch.setattr(compare, "judge_available", lambda: True)
    monkeypatch.setattr(compare, "judge_endpoint", lambda: ("http://x", "fake", ""))
    with pytest.raises(compare.CompareError, match="文字太少"):
        compare.extract_profile("太短")


def test_extract_profile_cleans_fields_and_caches(monkeypatch, isolated_cache):
    monkeypatch.setattr(compare, "judge_available", lambda: True)
    monkeypatch.setattr(compare, "judge_endpoint", lambda: ("http://x", "fake", ""))
    calls = {"n": 0}

    def fake_judge(user, max_tokens=800):
        calls["n"] += 1
        return {
            "research_question": " 研究问题。 ",
            "method": "方法" * 200,
            "研究问题": "被中文键覆盖",
            "findings": "结论",
            "limitations": "",
        }

    monkeypatch.setattr(compare, "_judge_json", fake_judge)
    result = compare.extract_profile(_long_body())
    assert result["fields"]["research_question"] == "研究问题"
    assert result["fields"]["findings"] == "结论"
    assert len(result["fields"]["method"]) <= compare.FIELD_MAX_CHARS
    assert result["fields"]["limitations"] == ""
    assert result["cached"] is False

    def boom(*_args, **_kwargs):
        raise AssertionError("second call should hit the cache")

    monkeypatch.setattr(compare, "_judge_json", boom)
    again = compare.extract_profile(_long_body())
    assert again["cached"] is True
    assert again["fields"] == result["fields"]
    assert calls["n"] == 1


def test_extract_profile_rejects_empty_model_output(monkeypatch, isolated_cache):
    monkeypatch.setattr(compare, "judge_available", lambda: True)
    monkeypatch.setattr(compare, "judge_endpoint", lambda: ("http://x", "fake", ""))
    monkeypatch.setattr(compare, "_judge_json", lambda *a, **k: {})
    with pytest.raises(compare.CompareError, match="JSON"):
        compare.extract_profile(_long_body())


def test_compare_texts_keeps_partial_failures(monkeypatch, isolated_cache):
    monkeypatch.setattr(compare, "judge_available", lambda: True)
    monkeypatch.setattr(compare, "judge_endpoint", lambda: ("http://x", "fake", ""))

    def fake_extract(text, *, use_cache=True):
        if "坏文件" in text:
            raise compare.CompareError("解析失败")
        return {
            "fields": {key: f"{key}-值" for key in compare.FIELD_KEYS},
            "model": "fake",
            "excerpt_chars": len(text),
            "latency_ms": 3,
        }

    monkeypatch.setattr(compare, "extract_profile", fake_extract)
    progress = []
    result = compare.compare_texts(
        [("好文件", _long_body()), ("坏文件", "坏文件" + _long_body())],
        on_progress=lambda i, total, name: progress.append((i, total, name)),
    )
    assert progress == [(1, 2, "好文件"), (2, 2, "坏文件")]
    assert result["papers"][0]["fields"]["method"] == "method-值"
    assert result["papers"][1]["error"] == "解析失败"
    assert result["papers"][1]["fields"]["method"] == ""


def test_compare_texts_all_failed_raises(monkeypatch, isolated_cache):
    monkeypatch.setattr(compare, "judge_available", lambda: True)
    monkeypatch.setattr(compare, "judge_endpoint", lambda: ("http://x", "fake", ""))
    monkeypatch.setattr(
        compare, "extract_profile", lambda text, use_cache=True: (_ for _ in ()).throw(compare.CompareError("坏"))
    )
    with pytest.raises(compare.CompareError, match="所有文献"):
        compare.compare_texts([("a", _long_body()), ("b", _long_body())])


def test_compare_texts_enforces_count():
    with pytest.raises(compare.CompareError, match="2–6"):
        compare.compare_texts([("only", _long_body())])


def test_render_markdown_and_csv():
    result = {
        "generated_at": "2026-01-02T03:04:05",
        "model": "fake-model",
        "fields": [{"key": "method", "label": "方法 / 设计"}],
        "papers": [
            {"name": "甲", "fields": {"method": "问卷 | 实验"}, "error": "", "cached": False},
            {"name": "乙", "fields": {"method": ""}, "error": "", "cached": False},
        ],
    }
    md = compare.render_markdown(result)
    assert "多篇文献对比" in md
    assert "问卷 \\| 实验" in md
    assert "fake-model" in md
    csv_text = compare.render_csv(result)
    assert "字段,甲,乙" in csv_text
    lines = csv_text.splitlines()
    assert lines[0] == "字段,甲,乙"
    assert lines[1] == "方法 / 设计,问卷 | 实验,"


def test_cache_path_namespaced_by_model(monkeypatch, isolated_cache):
    monkeypatch.setattr(compare, "judge_endpoint", lambda: ("http://x", "model-a", ""))
    a = compare._cache_path("同一个摘录")
    monkeypatch.setattr(compare, "judge_endpoint", lambda: ("http://x", "model-b", ""))
    b = compare._cache_path("同一个摘录")
    assert a != b
    assert a.parent == b.parent


def _sectioned_paper() -> str:
    body = "这是一段用于测试的正文内容，重复若干次以超过最小长度要求。" * 4
    return (
        "摘要：本文研究了一个问题，" + body + "\n"
        "1 引言\n" + body + "\n"
        "2 方法\n本文采用问卷调查方法，" + body + "\n"
        "3 结果\n结果显示显著差异，" + body + "\n"
        "4 讨论\n讨论部分解释了原因，" + body + "\n"
        "5 结论\n结论指出实践意义，" + body
    )


def test_section_snippets_split_headings():
    snippets = compare._section_snippets(_sectioned_paper())
    labels = [label for label, _body in snippets]
    assert "方法" in labels and "结果" in labels and "结论" in labels
    body = next(body for label, body in snippets if label == "方法")
    assert "问卷调查" in body


def test_context_uses_section_labels_when_available():
    body, sections = compare._context(_sectioned_paper())
    assert "【方法】" in body and "【结果】" in body
    assert "方法" in sections and "结论" in sections


def test_extract_profile_passes_sections_to_judge(monkeypatch):
    monkeypatch.setattr(compare, "judge_available", lambda: True)
    monkeypatch.setattr(compare, "judge_endpoint", lambda: ("http://judge", "offline-test", ""))
    captured = {}

    def fake_judge(user, max_tokens=800):
        captured["user"] = user
        return {key: "内容" for key in compare.FIELD_KEYS}

    monkeypatch.setattr(compare, "_judge_json", fake_judge)
    profile = compare.extract_profile(_sectioned_paper(), use_cache=False)
    assert "【方法】" in captured["user"]
    assert "方法" in profile["sections"]
    assert profile["fields"]["method"] == "内容"
