"""Concurrent verification: order preservation and progress reporting."""
from __future__ import annotations

import time

import citeguard.metadata_verify as mv
from citeguard.reference_parser import Reference

REFS = [
    Reference(raw=f"[{i}] 作者{i}. 题名{i}[J]. 期刊, 2020, 1({i}): 1-9.", index=i, title=f"题名{i}")
    for i in range(1, 13)
]


def test_results_keep_input_order(monkeypatch):
    def fake_verify(ref, use_arxiv=True, library=None):
        # Later entries finish sooner; order must still follow the input list.
        time.sleep((12 - ref.index) * 0.01)
        return mv.VerifyResult(status="Exact", notes=[f"ref-{ref.index}"])

    monkeypatch.setattr(mv, "verify_reference", fake_verify)

    results = mv.verify_many(REFS, progress=False, workers=4)

    assert [r.notes[0] for r in results] == [f"ref-{i}" for i in range(1, 13)]


def test_progress_callback_is_called_for_every_reference(monkeypatch):
    monkeypatch.setattr(
        mv, "verify_reference", lambda ref, use_arxiv=True: mv.VerifyResult(status="Exact")
    )
    seen: list[tuple[int, int]] = []

    mv.verify_many(REFS, progress=False, workers=3, progress_cb=lambda i, n: seen.append((i, n)))

    assert sorted(i for i, _ in seen) == list(range(1, len(REFS) + 1))
    assert all(n == len(REFS) for _, n in seen)


def test_single_failure_degrades_to_unknown(monkeypatch):
    def boom(ref, use_arxiv=True, library=None):
        if ref.index == 3:
            raise RuntimeError("network exploded")
        return mv.VerifyResult(status="Exact")

    monkeypatch.setattr(mv, "verify_reference", boom)

    results = mv.verify_many(REFS, progress=False, workers=2)

    assert results[2].status == "Unknown"
    assert sum(1 for r in results if r.status == "Exact") == len(REFS) - 1


def test_empty_input_returns_empty():
    assert mv.verify_many([], progress=False) == []


def test_parallel_verification_is_faster_than_serial(monkeypatch):
    monkeypatch.setattr(
        mv,
        "verify_reference",
        lambda ref, use_arxiv=True: (time.sleep(0.05), mv.VerifyResult(status="Exact"))[1],
    )
    start = time.monotonic()
    mv.verify_many(REFS, progress=False, workers=6)
    elapsed = time.monotonic() - start

    # 12 refs x 50ms serial = 0.6s; with 6 workers this should be well below it.
    assert elapsed < 0.45
