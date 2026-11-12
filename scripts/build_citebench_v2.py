"""Build CiteBench-CN v2: 500 Chinese references with controlled corruptions.

v2 = the original 250 items (Exact / Minor / Major) plus 250 new items:

    author_swap    35  authors replaced with another paper's authors
    year_shift     35  publication year shifted by 1-3 years
    venue_swap     30  journal name replaced with another paper's venue
    doi_swap       30  DOI replaced with another paper's DOI
    paraphrase     30  title reordered / subtitle trimmed
    fabricated     30  plausible but non-existent title (no DOI)
    retracted      30  real retracted works (OpenAlex is_retracted=true)
    predatory      30  real title placed in a predatory-looking venue

All labels are constructed by these rules, not by human annotation. The
retracted set is the only one whose ground truth comes from an external flag
(OpenAlex); predatory venues are a documented, deliberately small blocklist,
so this class measures "can any detector flag it", and the current product has
no predatory detector — v2 evaluation reports that as a known gap instead of
pretending a score.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_citebench as bc  # noqa: E402

DATA_DIR = ROOT / "data" / "citebench_cn"
V1_PATH = DATA_DIR / "citebench_cn.jsonl"
POOL_PATH = DATA_DIR / "openalex_zh_works.json"
RETRACTED_CACHE = DATA_DIR / "retracted_works.json"
OUT_PATH = DATA_DIR / "citebench_cn_v2.jsonl"
META_PATH = DATA_DIR / "citebench_cn_v2.meta.json"

SEED = 20261112
NEW_COUNTS = {
    "author_swap": 35,
    "year_shift": 35,
    "venue_swap": 30,
    "doi_swap": 30,
    "paraphrase": 30,
    "fabricated": 30,
    "retracted": 30,
    "predatory": 30,
}

# Deliberately small, documented list. These names are used only to construct a
# "predatory-looking venue" class; they are not an accusation against any real
# journal and must not be used as a production blocklist.
PREDATORY_VENUES = [
    "International Journal of Advanced Research and Science",
    "Global Journal of Engineering and Technology",
    "Academic Journal of Multidisciplinary Studies",
    "Open Journal of Computer Science and Engineering",
    "International Journal of Modern Research",
    "Journal of Emerging Trends and Innovation",
    "World Journal of Scientific Advances",
    "Universal Journal of Applied Sciences",
    "International Research Journal of Technology",
    "Journal of Global Academic Studies",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _work_id(work: dict) -> str:
    return (work.get("id") or "").rstrip("/").rsplit("/", 1)[-1]


def _source_id(item: dict) -> str:
    return (item.get("source") or "").replace("openalex:", "")


def _load_pool() -> list[dict]:
    data = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    works = data.get("works") or []
    return [
        w for w in works
        if w.get("title") and w.get("authors") and w.get("venue") and w.get("year") and w.get("doi")
    ]


def _fetch_retracted() -> list[dict]:
    if RETRACTED_CACHE.exists():
        return json.loads(RETRACTED_CACHE.read_text(encoding="utf-8"))
    raw = None
    last = None
    for attempt in range(4):
        try:
            resp = requests.get(
                "https://api.openalex.org/works",
                params={"filter": "is_retracted:true,language:zh", "per-page": 50, "mailto": "citeguard@example.com"},
                timeout=60,
            )
            resp.raise_for_status()
            raw = resp.json().get("results") or []
            break
        except Exception as exc:  # SSL/rate-limit flakiness
            last = exc
            time.sleep(2 + attempt * 2)
    if raw is None:
        raise SystemExit(f"cannot fetch retracted works: {last}")
    works = []
    for item in raw:
        norm = bc._normalize_work(item)
        if norm.get("title") and norm.get("doi") and norm.get("year"):
            works.append(norm)
    RETRACTED_CACHE.write_text(json.dumps(works, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(1)
    return works


def _shuffled(values: list[str], rng: random.Random) -> list[str]:
    copy = list(values)
    rng.shuffle(copy)
    return copy


def _paraphrase(title: str) -> str:
    t = re.sub(r"[（(][^）)]{0,30}[）)]", "", title).strip(" .")
    if ":" in t:
        head, tail = t.split(":", 1)
        t = f"{tail.strip()}：{head.strip()}"
    elif "——" in t:
        head, tail = t.split("——", 1)
        t = f"{tail.strip()}——{head.strip()}"
    elif len(t) > 12:
        t = t[4:] + "：" + t[:4]
    return t or title


def _render(work: dict, *, authors=None, title=None, venue=None, year=None, doi=None) -> str:
    return bc.render_reference(
        authors if authors is not None else work["authors"],
        title if title is not None else work["title"],
        venue if venue is not None else work["venue"],
        int(year if year is not None else work["year"]),
        work.get("volume") or "",
        work.get("issue") or "",
        bc.pages_of(work),
        doi if doi is not None else work.get("doi") or "",
    )


def _item(item_id: str, ref: str, label: str, corruption: str, gold_work: dict) -> dict:
    return {
        "id": item_id,
        "ref_string": ref,
        "label": label,
        "corruption": corruption,
        "gold": bc._gold(gold_work),
        "source": f"openalex:{_work_id(gold_work)}",
    }


def build() -> int:
    rng = random.Random(SEED)
    v1 = [json.loads(line) for line in V1_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    used = {_source_id(item) for item in v1}
    pool = [w for w in _load_pool() if _work_id(w) not in used]
    rng.shuffle(pool)
    if len(pool) < 260:
        raise SystemExit(f"pool too small: {len(pool)}")

    venues = [w["venue"] for w in pool]
    authors = [w["authors"] for w in pool]
    dois = [w["doi"] for w in pool]
    titles = [w["title"] for w in pool]

    new_items: list[dict] = []
    cursor = 0
    made = {key: 0 for key in NEW_COUNTS}

    def take() -> dict:
        nonlocal cursor
        work = pool[cursor]
        cursor += 1
        return work

    # field-level mutations
    for kind in ("author_swap", "year_shift", "venue_swap", "doi_swap", "paraphrase", "fabricated"):
        while made[kind] < NEW_COUNTS[kind]:
            work = take()
            if kind == "author_swap":
                other = authors[(cursor * 7) % len(authors)]
                ref = _render(work, authors=other)
                corruption = f"v2:author_swap ({len(other)} authors from another work)"
            elif kind == "year_shift":
                delta = rng.choice([-3, -2, -1, 1, 2, 3])
                ref = _render(work, year=int(work["year"]) + delta)
                corruption = f"v2:year_shift {work['year']}->{int(work['year']) + delta}"
            elif kind == "venue_swap":
                other = venues[(cursor * 11) % len(venues)]
                if other == work["venue"]:
                    continue
                ref = _render(work, venue=other)
                corruption = f"v2:venue_swap -> {other}"
            elif kind == "doi_swap":
                other = dois[(cursor * 13) % len(dois)]
                if other == work.get("doi"):
                    continue
                ref = _render(work, doi=other)
                corruption = f"v2:doi_swap -> {other}"
            elif kind == "paraphrase":
                new_title = _paraphrase(work["title"])
                if new_title == work["title"]:
                    continue
                ref = _render(work, title=new_title)
                corruption = "v2:title_paraphrase"
            else:  # fabricated
                fake = rng.choice(titles)
                fake = f"{fake.rstrip('。.')}的实证研究"
                ref = _render(work, title=fake, doi="")
                corruption = "v2:fabricated_title"
            made[kind] += 1
            new_items.append(_item(f"cbcn2-{len(new_items) + 1:04d}", ref, kind, corruption, work))

    # retracted: external ground truth
    for work in _fetch_retracted()[: NEW_COUNTS["retracted"]]:
        ref = _render(work)
        made["retracted"] += 1
        new_items.append(_item(
            f"cbcn2-{len(new_items) + 1:04d}", ref, "retracted",
            "v2:retracted (OpenAlex is_retracted=true)", work,
        ))

    # predatory-looking venue: constructed, detector absent
    for work in [take() for _ in range(NEW_COUNTS["predatory"])]:
        venue = PREDATORY_VENUES[made["predatory"] % len(PREDATORY_VENUES)]
        ref = _render(work, venue=venue, doi="")
        made["predatory"] += 1
        new_items.append(_item(
            f"cbcn2-{len(new_items) + 1:04d}", ref, "predatory",
            f"v2:predatory_venue ({venue})", work,
        ))

    # Retracted pool is whatever OpenAlex has for Chinese works (often < 30);
    # top up with additional constructed items so v2 always has 500.
    while len(v1) + len(new_items) < 500:
        work = take()
        fake = f"{rng.choice(titles).rstrip('。.')}的实证研究"
        ref = _render(work, title=fake, doi="")
        made["fabricated"] += 1
        new_items.append(_item(
            f"cbcn2-{len(new_items) + 1:04d}", ref, "fabricated",
            "v2:fabricated_title (top-up)", work,
        ))
    rows = v1 + new_items
    if len(rows) != 500:
        raise SystemExit(f"expected 500 rows, got {len(rows)}")
    if len({r["id"] for r in rows}) != len(rows):
        raise SystemExit("duplicate ids")
    if len({r["source"] for r in rows}) != len(rows):
        raise SystemExit("duplicate source works")

    OUT_PATH.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    meta = {
        "dataset": "CiteBench-CN",
        "version": 2,
        "built_at": _utc_now(),
        "seed": SEED,
        "n": len(rows),
        "counts": counts,
        "v1_items": len(v1),
        "new_items": len(new_items),
        "sha256": hashlib.sha256(OUT_PATH.read_bytes()).hexdigest(),
        "labels": "constructed by mutation rules; not human annotation",
        "retracted_source": "OpenAlex works?filter=is_retracted:true,language:zh",
        "predatory": "constructed from a documented, deliberately small venue list; no production blocklist",
        "notes": [
            "v1 250 items keep their Exact/Minor/Major labels.",
            "new classes are binary problem labels for per-class detection; see eval script.",
            "no item reuses a source work across the 500.",
        ],
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(build())
