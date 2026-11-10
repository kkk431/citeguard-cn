from pathlib import Path

from citeguard import pipeline, text_cache


def test_text_cache_roundtrip(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 demo")
    cache = tmp_path / "cache"
    assert text_cache.load_text(src, cache_dir=cache) is None
    text_cache.save_text(src, "hello 世界", {"pages": 1}, cache_dir=cache)
    text, meta = text_cache.load_text(src, cache_dir=cache)
    assert text == "hello 世界"
    assert meta["pages"] == 1


def test_extract_uses_cache_for_same_file(tmp_path, monkeypatch):
    src = tmp_path / "b.pdf"
    src.write_bytes(b"%PDF-1.4 demo")
    monkeypatch.setenv("CITEGUARD_TEXT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("CITEGUARD_TEXT_CACHE", "1")
    calls = {"n": 0}

    def fake_extract(path, on_page=None):
        calls["n"] += 1
        return "fake text", {"pages": 2, "warnings": []}

    monkeypatch.setattr(pipeline, "extract_text_with_meta", fake_extract)
    text1, meta1 = pipeline._extract_cached(str(src))
    text2, meta2 = pipeline._extract_cached(str(src))
    assert calls["n"] == 1
    assert text1 == text2 == "fake text"
    assert meta1["cache"] == "miss"
    assert meta2["cache"] == "hit"
