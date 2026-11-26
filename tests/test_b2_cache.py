"""B2: content-addressed result cache and batch rerun that only fills failures."""
from __future__ import annotations

from pathlib import Path

import pytest

from citeguard import jobs, pipeline, support


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_result_cache_key_covers_content_options_and_versions():
    base = jobs.result_cache_key("a" * 64, {"support_max": 5}, {"prompt": "v10", "audit": "on:auto"})
    assert base == jobs.result_cache_key("a" * 64, {"support_max": 5}, {"prompt": "v10", "audit": "on:auto"})
    assert base != jobs.result_cache_key("b" * 64, {"support_max": 5}, {"prompt": "v10", "audit": "on:auto"})
    assert base != jobs.result_cache_key("a" * 64, {"support_max": 6}, {"prompt": "v10", "audit": "on:auto"})
    assert base != jobs.result_cache_key("a" * 64, {"support_max": 5}, {"prompt": "v11", "audit": "on:auto"})
    assert base != jobs.result_cache_key("a" * 64, {"support_max": 5}, {"prompt": "v10", "audit": "off"})
    # A different schema (report shape) is a different namespace too.
    assert base != jobs.result_cache_key(
        "a" * 64, {"support_max": 5}, {"prompt": "v10", "audit": "on:auto"}, schema=2
    )


def test_result_cache_roundtrip_invalidate_and_corruption(tmp_path):
    cache = jobs.ResultCache(tmp_path / "cache")
    key = jobs.result_cache_key("c" * 64, {"support_max": 0}, {"prompt": "v10"})
    assert cache.load(key) is None

    cache.store(key, {"references": 3, "support": {"support": 1}}, {"file": "a.pdf"})
    hit = cache.load(key)
    assert hit is not None
    assert hit["report"]["references"] == 3
    assert hit["meta"]["file"] == "a.pdf"

    # A corrupted entry is a miss, never an exception.
    cache.slot(key).write_text("{not json", encoding="utf-8")
    assert cache.load(key) is None

    cache.store(key, {"references": 4}, {})
    assert cache.load(key)["report"]["references"] == 4
    assert cache.invalidate(key) is True
    assert cache.load(key) is None
    assert cache.stats()["entries"] == 0


def test_result_cache_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("CITEGUARD_RESULT_CACHE", "0")
    cache = jobs.ResultCache(tmp_path / "cache")
    key = jobs.result_cache_key("d" * 64, {}, {})
    assert jobs.result_cache_enabled() is False
    assert cache.store(key, {"ok": True}) is None
    assert cache.load(key) is None


def test_batch_hot_run_reuses_cache_without_reprocessing(tmp_path):
    first = _write(tmp_path / "p1.txt", "第一篇文章正文。\n参考文献：[1] 张三. 测试. 2024.")
    second = _write(tmp_path / "p2.txt", "第二篇文章正文。\n参考文献：[1] 李四. 测试. 2023.")
    runner = jobs.BatchRunner(
        cache=jobs.ResultCache(tmp_path / "cache"),
        root=tmp_path / "batches",
        options={"support_max": 0, "online": False},
        versions={"prompt": "v10", "audit": "on:auto"},
    )
    calls: list[str] = []

    def process(path: str, options: dict) -> dict:
        calls.append(path)
        return {"source": Path(path).name, "options": options}

    cold = runner.create([first, second])
    cold = runner.run(cold["id"], process)
    assert calls == [str(first.resolve()), str(second.resolve())]
    assert [it["status"] for it in cold["items"]] == ["done", "done"]
    assert [it["source"] for it in cold["items"]] == ["processed", "processed"]
    assert cold["stats"]["cache_hits"] == 0
    after_cold = runner.cache.stats()

    hot = runner.create([first, second])
    hot = runner.run(hot["id"], process)
    # The analyser is never called again for already-cached content.
    assert len(calls) == 2
    assert [it["source"] for it in hot["items"]] == ["cache", "cache"]
    assert hot["stats"]["cache_hits"] == 2
    after_hot = runner.cache.stats()
    # The hot batch adds two hits and no new misses.
    assert after_hot["hits"] - after_cold["hits"] == 2
    assert after_hot["misses"] == after_cold["misses"]
    report = runner.report(hot["id"], "item-01")
    assert report == {"source": "p1.txt", "options": {"support_max": 0, "online": False}}


def test_batch_retry_failed_only_reruns_the_failed_item(tmp_path):
    files = [
        _write(tmp_path / "ok1.txt", "ok1"),
        _write(tmp_path / "flaky.txt", "flaky"),
        _write(tmp_path / "ok2.txt", "ok2"),
    ]
    runner = jobs.BatchRunner(
        cache=jobs.ResultCache(tmp_path / "cache"),
        root=tmp_path / "batches",
        options={"support_max": 0, "online": False},
        versions={"prompt": "v10"},
    )
    calls: list[str] = []
    attempts: dict[str, int] = {}

    def process(path: str, options: dict) -> dict:
        calls.append(path)
        name = Path(path).name
        attempts[name] = attempts.get(name, 0) + 1
        if name == "flaky.txt" and attempts[name] == 1:
            raise RuntimeError("transient network error")
        return {"file": name}

    batch = runner.create(files)
    batch = runner.run(batch["id"], process)
    assert [it["status"] for it in batch["items"]] == ["done", "error", "done"]
    assert "transient network error" in batch["items"][1]["error"]
    assert len(calls) == 3
    # A failure must not be cached, otherwise a retry would replay it forever.
    assert runner.cache.load(batch["items"][1]["cache_key"]) is None

    first_report = runner.report(batch["id"], "item-01")
    retried = runner.retry_failed(batch["id"], process)
    assert [it["status"] for it in retried["items"]] == ["done", "done", "done"]
    assert retried["stats"]["error"] == 0
    # Only the failed item ran again; successful items kept their report.
    assert calls[3] == str(files[1].resolve())
    assert attempts == {"ok1.txt": 1, "flaky.txt": 2, "ok2.txt": 1}
    assert runner.report(batch["id"], "item-01") == first_report
    # Skipped items keep their previous provenance; only the failed one reran.
    assert retried["items"][0]["source"] == "processed"
    assert retried["items"][2]["source"] == "processed"
    assert retried["items"][1]["source"] == "processed"


def test_batch_can_retry_a_single_failed_item(tmp_path):
    files = [_write(tmp_path / f"p{i}.txt", f"text {i}") for i in range(1, 4)]
    runner = jobs.BatchRunner(
        cache=jobs.ResultCache(tmp_path / "cache"),
        root=tmp_path / "batches",
        options={},
        versions={"prompt": "v10"},
    )
    calls: list[str] = []

    def process(path: str, options: dict) -> dict:
        calls.append(Path(path).name)
        if Path(path).name == "p2.txt" and calls.count("p2.txt") == 1:
            raise RuntimeError("boom")
        return {"file": Path(path).name}

    batch = runner.create(files)
    batch = runner.run(batch["id"], process)
    assert [it["status"] for it in batch["items"]] == ["done", "error", "done"]
    assert calls == ["p1.txt", "p2.txt", "p3.txt"]

    batch = runner.retry_item(batch["id"], "item-02", process)
    assert [it["status"] for it in batch["items"]] == ["done", "done", "done"]
    assert calls == ["p1.txt", "p2.txt", "p3.txt", "p2.txt"]
    assert runner.cache.load(batch["items"][1]["cache_key"]) is not None
    with pytest.raises(KeyError):
        runner.retry_item(batch["id"], "item-99", process)


def test_batch_reports_are_persisted_on_disk(tmp_path):
    source = _write(tmp_path / "p.txt", "text")
    runner = jobs.BatchRunner(
        cache=jobs.ResultCache(tmp_path / "cache"),
        root=tmp_path / "batches",
        options={},
        versions={"prompt": "v10"},
    )
    batch = runner.create([source])
    runner.run(batch["id"], lambda path, options: {"file": Path(path).name})
    record = tmp_path / "batches" / batch["id"] / "batch.json"
    assert record.exists()
    assert runner.get(batch["id"])["items"][0]["status"] == "done"
    report_path = Path(runner.get(batch["id"])["items"][0]["report_path"])
    assert report_path.exists() and report_path.parent.parent == tmp_path / "batches" / batch["id"]


def test_analysis_cache_versions_include_model_prompt_and_audit():
    versions = pipeline.analysis_cache_versions()
    assert versions["prompt"] == str(support.PROMPT_VERSION)
    assert versions["analysis"] == pipeline.ANALYSIS_CACHE_VERSION
    assert versions["audit"].startswith(("on:", "off"))
    assert "judge_model" in versions and "judge_base" in versions
    assert isinstance(versions["judge_available"], bool)


def test_analyze_file_cached_second_call_is_a_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setenv("CITEGUARD_RESULT_CACHE_DIR", str(tmp_path / "result-cache"))
    monkeypatch.setenv("CITEGUARD_TEXT_CACHE_DIR", str(tmp_path / "text-cache"))
    text = (
        "本文讨论引用核验。近年来相关研究很多[1]。\n\n参考文献\n"
        "[1] 张三, 李四. 一种引用核验方法. 计算机学报, 2024, 47(1): 1-10.\n"
    )
    source = _write(tmp_path / "paper.txt", text)
    options = {"support_max": 0, "online": False, "figures": False}

    first = pipeline.analyze_file_cached(source, options=options)
    assert first["cache"]["status"] == "miss"
    assert first["references"]

    second = pipeline.analyze_file_cached(source, options=options)
    assert second["cache"]["status"] == "hit"
    assert second["cache"]["key"] == first["cache"]["key"]
    assert [r["raw"] for r in second["references"]] == [r["raw"] for r in first["references"]]
