import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "citebench_cn"
DATASET = DATA / "citebench_cn_v2.jsonl"
META = DATA / "citebench_cn_v2.meta.json"


def _load():
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_v2_has_500_unique_items_and_sources():
    rows = _load()
    assert len(rows) == 500
    assert len({row["id"] for row in rows}) == 500
    assert len({row["source"] for row in rows}) == 500


def test_v2_counts_match_meta_and_hash():
    rows = _load()
    meta = json.loads(META.read_text(encoding="utf-8"))
    counts = Counter(row["label"] for row in rows)
    assert dict(counts) == meta["counts"]
    assert meta["n"] == 500
    assert meta["sha256"] == hashlib.sha256(DATASET.read_bytes()).hexdigest()


def test_v2_labels_are_documented_constructs():
    rows = _load()
    labels = {row["label"] for row in rows}
    assert labels <= {
        "Exact", "Minor", "Major", "author_swap", "year_shift", "venue_swap",
        "doi_swap", "paraphrase", "fabricated", "retracted", "predatory",
    }
    assert all(row.get("gold", {}).get("title") for row in rows)
