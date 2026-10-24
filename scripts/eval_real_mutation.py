"""Measure whether real references with injected errors are actually caught.

Why this exists: the product's error-catching claims used to rest on a
template-built benchmark (CiteBench-CN). That is useful but easy to dismiss.
This script starts from the 409 references parsed out of real published papers
and injects controlled errors into references that carry a DOI, so every case
has a clear ground truth:

- ``doi_bad``       fake DOI (10.99999/...), the cited fields stay real -> Major
- ``year_shift``    real DOI, publication year shifted by 7 -> Minor (year)
- ``authors_swap``  real DOI, author list taken from another real paper -> Minor
- ``venue_swap``    real DOI, venue taken from another real paper -> Minor
- ``title_swap``    real DOI, title taken from another real paper -> Major/Minor
- ``baseline``      the untouched reference, for the false-positive baseline

A reference is "caught" when the verifier returns Major or Minor. Exact means
the injected error slipped through; Unverified means the product could not
decide (honest, but not a catch).

The ``fabricated_noanchor`` family (fake title/authors/venue, no DOI/URL) is
reported separately: by design the product does not call an unindexed record
fabricated, so most of these should be Unverified, not Major.

Usage:
    python scripts/eval_real_mutation.py [--sample 40] [--seed 20261024]
        [--workers 4] [--out data/experiments/real_mutation_eval.json]
        [--smoke]   # 3 base refs, no fabricated family, for a quick run
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.metadata_verify import verify_many  # noqa: E402
from citeguard.reference_parser import parse_reference_list  # noqa: E402

CORPUS = ROOT / "data" / "real_corpus"
OUT = ROOT / "data" / "experiments" / "real_mutation_eval.json"

STATUSES = ("Exact", "Minor", "Major", "Unverified", "Unknown")
CATCH = {"Major", "Minor"}


def _load_published_refs() -> tuple[list, dict]:
    items: list[dict] = []
    for name in ("hanspub_manifest.json", "manifest.json"):
        path = CORPUS / name
        if path.exists():
            items += json.loads(path.read_text(encoding="utf-8"))
    refs: list = []
    papers = 0
    for item in items:
        refs_file = item.get("refs_file")
        if not refs_file or not Path(refs_file).exists():
            continue
        papers += 1
        refs += parse_reference_list(Path(refs_file).read_text(encoding="utf-8"))
    return refs, {"papers_with_published_list": papers, "refs": len(refs)}


def _usable(ref) -> bool:
    return bool(
        (ref.doi or "").strip()
        and (ref.title or "").strip()
        and len(ref.title.strip()) >= 8
        and ref.authors
        and ref.year
        and (ref.doc_type or "").upper() != "EB"
    )


def _fake_doi(rng: random.Random) -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyz23456789"
    return "10.99999/mut-" + "".join(rng.choice(alphabet) for _ in range(10))


def _shift_year(year: int) -> int:
    return year - 7 if year >= 2015 else year + 7


def _fabricated_title(ref_a, ref_b) -> str:
    a = (ref_a.title or "").strip()
    b = (ref_b.title or "").strip()
    return f"基于{a[:14]}的{b[:14]}研究"


def _case(family: str, ref, expected: str, note: str) -> dict:
    return {"family": family, "ref": ref, "expected": expected, "note": note}


def build_cases(base: list, n: int, rng: random.Random) -> tuple[list[dict], list[dict]]:
    sample = base[:n]
    cases: list[dict] = []
    for i, ref in enumerate(sample):
        other = sample[(i + 1) % len(sample)]
        cases.append(_case("baseline", ref, "Exact/Minor", "未改动的真实条目"))
        cases.append(
            _case("doi_bad", replace(ref, doi=_fake_doi(rng)), "Major",
                  "真实字段 + 伪造 DOI")
        )
        cases.append(
            _case("year_shift", replace(ref, year=_shift_year(ref.year)), "Minor",
                  "真实 DOI + 年份偏移 7 年")
        )
        cases.append(
            _case("authors_swap", replace(ref, authors=list(other.authors)), "Minor",
                  "真实 DOI + 换成另一篇真实文献的作者")
        )
        cases.append(
            _case("venue_swap", replace(ref, venue=other.venue or "虚构学报"), "Minor",
                  "真实 DOI + 换成另一篇真实文献的刊名")
        )
        cases.append(
            _case("title_swap", replace(ref, title=other.title), "Major/Minor",
                  "真实 DOI + 换成另一篇真实文献的题名")
        )

    fabricated: list[dict] = []
    for i in range(max(1, n // 3)):
        ref = sample[i]
        other = sample[(i + 2) % len(sample)]
        fake = replace(
            ref,
            title=_fabricated_title(ref, other),
            authors=list(other.authors),
            venue=other.venue or ref.venue,
            year=2019 + (i % 5),
            doi="",
            url="",
            raw="",
        )
        fabricated.append(_case("fabricated_noanchor", fake, "Unverified（设计上不指控）",
                                "拼接的假题名，无 DOI/URL"))
    return cases, fabricated


def run(cases: list[dict], workers: int) -> tuple[list[dict], float]:
    # ``verify_many`` deduplicates by (title, year, DOI).  Two of our families
    # deliberately keep those three fields (authors_swap / venue_swap), so using
    # it would silently reuse the baseline result and report a false "exact".
    # Call the single-reference path directly instead.
    from concurrent.futures import ThreadPoolExecutor

    from citeguard.metadata_verify import verify_reference

    started = time.time()
    results: list = [None] * len(cases)

    def one(index: int, ref) -> None:
        try:
            results[index] = verify_reference(ref, use_arxiv=False)
        except Exception as exc:  # noqa: BLE001 - one bad case must not kill the run
            from citeguard.metadata_verify import VerifyResult

            results[index] = VerifyResult(status="Unknown", notes=[f"crash: {exc}"])

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(lambda pair: one(*pair), enumerate(c["ref"] for c in cases)))
    elapsed = time.time() - started
    out: list[dict] = []
    for case, result in zip(cases, results):
        out.append(
            {
                "family": case["family"],
                "expected": case["expected"],
                "note": case["note"],
                "status": result.status,
                "title_sim": result.title_sim,
                "year_match": result.year_match,
                "doi_status": result.doi_status,
                "mismatches": list(result.mismatches or []),
                "title": (case["ref"].title or "")[:80],
                "doi": (case["ref"].doi or "")[:60],
                "notes": (result.notes or [])[:3],
            }
        )
    return out, elapsed


def summarize(rows: list[dict], fabricated: list[dict], meta: dict) -> dict:
    def counts(items: list[dict]) -> dict:
        return {s: sum(1 for r in items if r["status"] == s) for s in STATUSES}

    baseline = [r for r in rows if r["family"] == "baseline"]
    mut = [r for r in rows if r["family"] != "baseline"]
    by_family: dict[str, dict] = {}
    for family in ("doi_bad", "year_shift", "authors_swap", "venue_swap", "title_swap"):
        items = [r for r in mut if r["family"] == family]
        c = counts(items)
        by_family[family] = {
            "n": len(items),
            **c,
            "detection_rate": round(sum(1 for r in items if r["status"] in CATCH) / (len(items) or 1), 4),
            "exact_rate": round(c["Exact"] / (len(items) or 1), 4),
        }
    base_c = counts(baseline)
    detectable = len(mut)
    detected = sum(1 for r in mut if r["status"] in CATCH)
    exact = sum(1 for r in mut if r["status"] == "Exact")
    unknown = sum(1 for r in mut if r["status"] == "Unknown")
    fab_c = counts(fabricated)
    return {
        **meta,
        "baseline": {**base_c, "n": len(baseline),
                     "exact_rate": round(base_c["Exact"] / (len(baseline) or 1), 4)},
        "mutations": {
            "n": detectable,
            "detected": detected,
            "detection_rate": round(detected / (detectable or 1), 4),
            "exact": exact,
            "exact_rate": round(exact / (detectable or 1), 4),
            "unverified": sum(1 for r in mut if r["status"] == "Unverified"),
            "unknown": unknown,
            "by_family": by_family,
        },
        "fabricated_noanchor": {
            "n": len(fabricated),
            **fab_c,
            "note": "无索引锚点的伪造条：产品按设计给 Unverified 而非指控；不计入检出率",
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    refs, corpus_meta = _load_published_refs()
    usable = [r for r in refs if _usable(r)]
    if not usable:
        print("no DOI-bearing references found", file=sys.stderr)
        return 1
    rng.shuffle(usable)
    n = min(args.sample, len(usable))
    if args.smoke:
        n = min(3, len(usable))
    base = usable[:n]
    cases, fabricated = build_cases(base, n, rng)
    if args.smoke:
        fabricated = []

    print(f"corpus: {corpus_meta['refs']} refs / {corpus_meta['papers_with_published_list']} papers, "
          f"{len(usable)} with DOI -> sample {n}", flush=True)
    rows, elapsed = run(cases + fabricated, args.workers)
    fab_rows = rows[len(cases):]
    rows = rows[:len(cases)]

    summary = summarize(
        rows,
        fab_rows,
        {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "seed": args.seed,
            "sample_size": n,
            "workers": args.workers,
            "corpus": corpus_meta,
            "usable_doi_refs": len(usable),
            "elapsed_seconds": round(elapsed, 1),
            "design": {
                "catch_rule": "status in {Major, Minor}",
                "doi_bad": "伪造 DOI -> 期望 Major",
                "year_shift": "真实 DOI + 年份 -7/+7 -> 期望 Minor(year)",
                "authors_swap": "真实 DOI + 他人作者 -> 期望 Minor(authors)",
                "venue_swap": "真实 DOI + 他人刊名 -> 期望 Minor(venue)",
                "title_swap": "真实 DOI + 他人题名 -> 期望 Major 或 Minor",
                "baseline": "未改动，用于误报基线（Exact 越高越好）",
            },
        },
    )

    payload = {
        "schema": "citeguard.real_mutation.v1",
        "summary": summary,
        "cases": rows,
        "fabricated": fab_rows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    fmt = lambda c: "/".join(f"{k}:{v}" for k, v in c.items() if v)
    print("\n== baseline ==")
    print(fmt(summary["baseline"]), "exact_rate=", summary["baseline"]["exact_rate"])
    print("\n== injected errors ==")
    for family, item in summary["mutations"]["by_family"].items():
        print(f"  {family:12s} n={item['n']:3d} detect={item['detection_rate']:.2f} "
              f"exact={item['exact_rate']:.2f}  {fmt(item)}")
    print(f"  overall      n={summary['mutations']['n']:3d} "
          f"detect={summary['mutations']['detection_rate']:.2f} "
          f"exact={summary['mutations']['exact_rate']:.2f}")
    if fab_rows:
        print("\n== fabricated without anchor ==")
        print(fmt(summary["fabricated_noanchor"]))
    print(f"\nreport -> {out_path}  ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
