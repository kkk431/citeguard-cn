"""The competition-required AI usage disclosure must stay present and honest."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ai_usage_disclosure_covers_development_and_runtime():
    text = (ROOT / "docs" / "ai_usage.md").read_text(encoding="utf-8")
    for phrase in (
        "开发过程中使用的 AI",
        "运行时使用的 AI 模型",
        "DeepSeek",
        "Qwen3-14B",
        "Qwen3-VL-8B",
        "不使用用户上传内容训练模型",
        "不是人工语义标注",
        "待真人完成",
    ):
        assert phrase in text, phrase


def test_ai_usage_is_linked_from_docs_nav_and_readme():
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "ai_usage.md" in nav
    assert "docs/ai_usage.md" in readme
