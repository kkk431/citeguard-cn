"""Expand ClaimSupport-CN with fresh OpenAlex source works (A3a SFT pool).

The 100-case benchmark plus its two disjoint extensions (``ext`` 60, ``v2`` 140)
already consume 349 source works.  This script keeps the *construction rules*
from ``scripts/build_claimsupport.py`` unchanged, but mines brand-new Chinese
OpenAlex works (pages the existing cache never fetched) so that every item here
is source-disjoint from those 300 items.  The result is a 380-item pool with
``a3-`` ids that feeds the enlarged SFT train split.

Provenance:
  * prior cache ``data/claimsupport_cn/claimsupport_cn.sources.json`` is only
    *read*; works already used by the 300 items are filtered out;
  * new works are fetched from OpenAlex and stored in our own fragment-only
    cache ``data/sft/openalex_sources_a3.json`` (at most two abstract sentences
    per work, OpenAlex metadata CC0 1.0).

Usage:
    PYTHONPATH=src python3 scripts/build_sft_expand.py            # fetch if needed
    PYTHONPATH=src python3 scripts/build_sft_expand.py --offline  # cache only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_claimsupport as B  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sft"
CACHE = DATA / "openalex_sources_a3.json"
OUT = DATA / "claimsupport_a3.jsonl"
META = DATA / "claimsupport_a3.meta.json"

BASE_ITEM_FILES = [
    ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl",
    ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_ext.jsonl",
    ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_v2.jsonl",
]

SEED = 20261114
LABELS = ["support", "partial", "contradict", "no_evidence"]
# Label mix for the new pool.  Contradict is the scarcest construction rule
# (only 29 antonym pairs fire on a first sentence), so it gets a smaller share.
N_SUPPORT = 150
N_PARTIAL = 105
N_CONTRADICT = 50
N_NO_EVIDENCE = 75
N_TOTAL = N_SUPPORT + N_PARTIAL + N_CONTRADICT + N_NO_EVIDENCE  # 380

# Fetch until each pool has this much slack over what build_items consumes.
# build_items fills support/partial *before* contradict from the same shuffled
# pool, so a contradict unit can be spent by an earlier role; `enough()` models
# that attrition instead of comparing raw pool sizes.
MAX_FETCH_PAGES = 26  # OpenAlex caps page*per-page at 10k -> pages 1..50
WORKS_NEEDED = N_SUPPORT + N_PARTIAL + N_CONTRADICT + 2 * N_NO_EVIDENCE
SLACK_WORKS = 180
SLACK_PARTIAL = 40
SLACK_CONTRADICT = 12


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


LOG: list[str] = []


def log(message: str) -> None:
    """Print and keep the line, so the data card can quote the real build log."""
    print(message)
    LOG.append(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _renormalise(unit: dict) -> dict:
    unit["sentences"] = [
        s for s in (B.normalize_sentence(x) for x in (unit.get("sentences") or [])) if B.sentence_ok(s)
    ]
    return unit


def load_prior_units() -> tuple[list[dict], int]:
    """Read the read-only ClaimSupport-CN fragment cache (never written here)."""
    payload = json.loads(B.SOURCE_CACHE.read_text(encoding="utf-8"))
    units = [
        u
        for u in (_renormalise(u) for u in payload.get("units") or [])
        if u["sentences"] and u.get("id")
    ]
    pages = int((payload.get("meta") or {}).get("pages_fetched") or 0)
    return units, pages


def load_extra_cache() -> tuple[list[dict], int]:
    if not CACHE.exists():
        return [], 0
    payload = json.loads(CACHE.read_text(encoding="utf-8"))
    units = [
        u
        for u in (_renormalise(u) for u in payload.get("units") or [])
        if u["sentences"] and u.get("id")
    ]
    pages = int((payload.get("meta") or {}).get("pages_fetched") or 0)
    return units, pages


def save_extra_cache(units: list[dict], pages_fetched: int) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(
            {
                "meta": {
                    "provider": "OpenAlex",
                    "license": "CC0 1.0 (metadata)",
                    "api": B.OPENALEX_URL,
                    "filter": B.OPENALEX_FILTER,
                    "select": B.OPENALEX_SELECT,
                    "mailto": B.MAILTO,
                    "pages_fetched": pages_fetched,
                    "fetched_at": utc_now(),
                    "note": "Fragment-only cache for the A3 SFT expansion: at most two "
                            "abstract sentences per work, no full abstract is stored.",
                    "purpose": "ClaimSupport-CN SFT expansion, disjoint from the 300-item pool",
                },
                "units": units,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def used_source_ids() -> set[str]:
    """Source works already consumed by the 300 existing items (v1 + ext + v2)."""
    used: set[str] = set()
    for path in BASE_ITEM_FILES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for key in ("claim_source", "evidence_source"):
                ref = row.get(key) or {}
                if ref.get("openalex_id"):
                    used.add(ref["openalex_id"])
    return used


def pool_stats(units: list[dict]) -> dict:
    plain = sum(1 for u in units if u["sentences"])
    partial = sum(1 for u in units if B.partial_clause(u["sentences"][0]))
    contradict = sum(1 for u in units if B.find_antonym(u["sentences"][0]))
    return {"works": plain, "partial_capable": partial, "contradict_capable": contradict}


def enough(stats: dict) -> bool:
    """True when each role still has enough units *after* earlier roles consume.

    support (and partial) draw from the same pooled units as contradict, so the
    contradict pool effectively shrinks by the share support/partial take.
    """
    works = max(1, stats["works"])
    support_share = min(0.9, N_SUPPORT / works)
    partial_share = min(0.9, (N_SUPPORT + N_PARTIAL) / works)
    partial_left = stats["partial_capable"] * (1 - support_share)
    contradict_left = stats["contradict_capable"] * (1 - partial_share)
    return (
        stats["works"] >= WORKS_NEEDED + SLACK_WORKS
        and partial_left >= N_PARTIAL + SLACK_PARTIAL
        and contradict_left >= N_CONTRADICT + SLACK_CONTRADICT
    )


def fetch_missing(
    prior_units: list[dict],
    prior_pages: int,
    extra_units: list[dict],
    extra_pages: int,
    used_ids: set[str],
    offline: bool,
) -> tuple[list[dict], int]:
    """Fetch further OpenAlex pages until the unused pool is comfortably large."""
    primary_seen = {u["sentences"][0] for u in prior_units + extra_units}
    ids_seen = {u["id"] for u in prior_units + extra_units}
    unused = [u for u in prior_units + extra_units if u["id"] not in used_ids]
    stats = pool_stats(unused)
    log(f"[sources] cached unused pool: {stats}")
    if enough(stats):
        log("[sources] cached pool is sufficient; no network fetch needed")
        return extra_units, extra_pages
    if offline:
        raise SystemExit(
            f"[sources] --offline but cached pool is too small: {stats} "
            f"(need works>={WORKS_NEEDED + SLACK_WORKS}, "
            f"partial>={N_PARTIAL + SLACK_PARTIAL}, "
            f"contradict>={N_CONTRADICT + SLACK_CONTRADICT})"
        )
    # Never re-fetch a page the prior cache (or our own cache) already covered.
    page = max(extra_pages, prior_pages) + 1
    while page <= MAX_FETCH_PAGES:
        payload = B._fetch_page(page)
        if not payload:
            log(f"[sources] page {page} unavailable, stopping fetch")
            break
        added = 0
        for raw in payload.get("results") or []:
            unit = B.normalize_unit(raw)
            if not unit or unit["id"] in ids_seen:
                continue
            if unit["sentences"][0] in primary_seen:
                continue  # translated abstracts repeat across works
            unit["fetched_page"] = page
            ids_seen.add(unit["id"])
            primary_seen.add(unit["sentences"][0])
            extra_units.append(unit)
            added += 1
        extra_pages = page
        save_extra_cache(extra_units, extra_pages)
        unused = [u for u in prior_units + extra_units if u["id"] not in used_ids]
        stats = pool_stats(unused)
        log(f"[sources] page {page}: +{added} works, unused pool {stats}")
        if enough(stats):
            break
        page += 1
    stats = pool_stats([u for u in prior_units + extra_units if u["id"] not in used_ids])
    if not enough(stats):
        raise SystemExit(
            f"[sources] pool still too small after page {extra_pages}: {stats}; "
            "lower the N_* counts or raise MAX_FETCH_PAGES"
        )
    return extra_units, extra_pages


def main(argv: list[str] | None = None) -> int:
    argp = argparse.ArgumentParser(description="Build the A3 ClaimSupport-CN expansion.")
    argp.add_argument("--seed", type=int, default=SEED)
    argp.add_argument("--offline", action="store_true", help="refuse to hit the OpenAlex API")
    argp.add_argument("--out", type=Path, default=OUT)
    args = argp.parse_args(argv)

    prior_units, prior_pages = load_prior_units()
    extra_units, extra_pages = load_extra_cache()
    used_ids = used_source_ids()
    print(
        f"[sources] prior cache: {len(prior_units)} works / pages 1..{prior_pages}; "
        f"a3 cache: {len(extra_units)} works / pages up to {extra_pages}; "
        f"used by 300 items: {len(used_ids)} works"
    )
    extra_units, extra_pages = fetch_missing(
        prior_units, prior_pages, extra_units, extra_pages, used_ids, offline=args.offline
    )

    all_units = prior_units + extra_units
    unused = [u for u in all_units if u["id"] not in used_ids]
    from_prior = sum(1 for u in unused if "fetched_page" not in u)
    from_new = len(unused) - from_prior
    log(f"[build] unused pool={len(unused)} (prior cache={from_prior}, new pages={from_new})")

    # Reuse the upstream constructor verbatim; only the counts change.
    B.N_SUPPORT = N_SUPPORT
    B.N_PARTIAL = N_PARTIAL
    B.N_CONTRADICT = N_CONTRADICT
    B.N_NO_EVIDENCE = N_NO_EVIDENCE
    B.N_TOTAL = N_TOTAL
    rng = random.Random(args.seed)
    items = B.build_items(unused, rng)

    # Fresh id namespace, and drop the transient page marker from the sources.
    for index, item in enumerate(items, 1):
        item["id"] = f"a3-{index:04d}"
        item["batch"] = "a3"
        for key in ("claim_source", "evidence_source"):
            item[key] = {
                "openalex_id": item[key]["openalex_id"],
                "title": item[key]["title"],
                "doi": item[key]["doi"],
                "year": item[key]["year"],
            }

    problems = [(item["id"], B.check_item(item)) for item in items]
    problems = [(i, p) for i, p in problems if p]
    if problems:
        for item_id, issue in problems[:10]:
            print(f"[check] {item_id}: {issue}")
        raise SystemExit(f"[check] {len(problems)} items failed the construction self-check")

    item_works = {
        item[key]["openalex_id"] for item in items for key in ("claim_source", "evidence_source")
    }
    overlap = item_works & used_ids
    if overlap:
        raise SystemExit(f"[check] {len(overlap)} works overlap the existing 300 items")
    roles_overlap = [
        item["id"]
        for item in items
        if item["label"] == "no_evidence"
        and item["claim_source"]["openalex_id"] == item["evidence_source"]["openalex_id"]
    ]
    if roles_overlap:
        raise SystemExit(f"[check] no_evidence items share one work: {roles_overlap[:5]}")

    labels = {label: sum(1 for item in items if item["label"] == label) for label in LABELS}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    spot = [
        {
            "id": item["id"],
            "label": item["label"],
            "claim": item["claim"],
            "evidence": item["evidence"],
            "claim_openalex_id": item["claim_source"]["openalex_id"],
            "evidence_openalex_id": item["evidence_source"]["openalex_id"],
        }
        for item in items[:5]
    ]
    previous_log: list[str] = []
    if META.exists():
        try:
            previous_log = json.loads(META.read_text(encoding="utf-8")).get("fetch_log") or []
        except Exception:  # pragma: no cover - corrupted meta is not fatal
            previous_log = []
    fetch_log = previous_log + [line for line in LOG if line not in previous_log]

    meta = {
        "dataset": "ClaimSupport-CN / A3 SFT expansion",
        "version": "a3",
        "built_at": utc_now(),
        "script": "scripts/build_sft_expand.py",
        "seed": args.seed,
        "n": len(items),
        "counts": labels,
        "counts_requested": {
            "support": N_SUPPORT,
            "partial": N_PARTIAL,
            "contradict": N_CONTRADICT,
            "no_evidence": N_NO_EVIDENCE,
        },
        "construction_rules": "inherited from scripts/build_claimsupport.py (unchanged)",
        "antonym_pairs": len(B.ANTONYM_PAIRS),
        "self_check": {"items": len(items), "failed": 0},
        "disjoint_from": [str(p.relative_to(ROOT)).replace("\\", "/") for p in BASE_ITEM_FILES],
        "source_works": {
            "unique": len(item_works),
            "from_prior_cache": from_prior,
            "from_new_pages": from_new,
            "overlap_with_existing_300": 0,
            "existing_300_works": len(used_ids),
        },
        "source_pages": {"prior_pages_fetched": prior_pages, "a3_pages_fetched": extra_pages},
        "cache": {
            "path": str(CACHE.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(CACHE),
            "works": len(extra_units),
        },
        "sha256": sha256_file(args.out),
        "labels": LABELS,
        "spot_check": spot,
        "fetch_log": fetch_log,
        "note": "Labels are construction-based, not human-annotated.",
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[done] wrote {args.out.relative_to(ROOT)} n={len(items)} {labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
