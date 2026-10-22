"""E5: retrieval / verification statistics over CiteBench-CN (250 items).

What it measures
----------------
For every reference in CiteBench-CN (250 items, labels fixed by construction):

- **DOI anchor hit rate** — items whose parsed DOI resolves to a real record.
  Reported for all DOI-bearing items and separately for *genuine* DOIs (the 37
  fabricated ``10.9999/...`` DOIs in the Major split are expected to 404, so they
  would otherwise depress the hit rate for reasons unrelated to retrieval).
- **title-search fallback hit rate** — for the 75 items without a DOI: did the
  title search return any candidate, and did it return a title match
  (``title_sim >= 0.90``)?
- **field-level comparison trigger rate** — share of items where the verifier
  actually ran ``_field_mismatches`` (it only runs when a candidate record was
  obtained).
- **per-item latency** — mean / median / p90 of one ``verify_reference`` call.
  Measured twice: (a) warm, served from ``data/citebench_cn/cache/`` (what a
  re-run or a demo costs); (b) a small cold sample fetched with the cache
  bypassed (what a first run over the network costs).
- **external request failure rate** — non-200 responses and exceptions over the
  HTTP requests actually issued.

Network discipline
------------------
The warm pass only *reads* ``data/citebench_cn/cache/``; cache misses (if any)
are written to ``data/experiments/cache_e5/`` instead, so the benchmark directory
is never modified. The cold sample is capped by ``--cold-sample`` and its raw
result is saved to ``data/experiments/e5_cold_sample.json``; reruns reuse that
file and issue 0 requests unless ``--refresh-cold`` is passed. Total requests for
one run stay well below the 150-request budget (numbers are recorded in the JSON).

Output
------
``data/experiments/e5_retrieval.json``

Usage
-----
    PYTHONPATH=src python3 scripts/e5_retrieval_stats.py            # cache-only + cold sample
    PYTHONPATH=src python3 scripts/e5_retrieval_stats.py --cold-sample 0
    PYTHONPATH=src python3 scripts/e5_retrieval_stats.py --refresh-cold
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402

import citeguard.config as config  # noqa: E402
import citeguard.metadata_verify as mv  # noqa: E402
from citeguard.reference_parser import parse_reference  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CB_DIR = ROOT / "data" / "citebench_cn"
DATASET = CB_DIR / "citebench_cn.jsonl"
CB_CACHE = CB_DIR / "cache"
OUT_DIR = ROOT / "data" / "experiments"
WARM_MISS_CACHE = OUT_DIR / "cache_e5"
COLD_CACHE = OUT_DIR / "cache_e5_cold"
COLD_RESULTS = OUT_DIR / "e5_cold_sample.json"
OUT_FILE = OUT_DIR / "e5_retrieval.json"
SEED = 20261022
REQUEST_BUDGET = 150

CODE_FILES = (
    "src/citeguard/metadata_verify.py",
    "src/citeguard/reference_parser.py",
    "src/citeguard/gbt7714.py",
)


def code_snapshot() -> dict:
    """Hashes of the modules whose behaviour this experiment measures.

    The team edits the project concurrently; E5 numbers are only comparable
    within the same source snapshot, so it is stored next to the metrics.
    """
    out = {}
    for rel in CODE_FILES:
        path = ROOT / rel
        if path.exists():
            out[rel] = {
                "sha256_16": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
    return out


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Instrumentation
# ---------------------------------------------------------------------------

class Counters:
    def __init__(self) -> None:
        self.requests = 0
        self.failed = 0  # any non-200 response (includes legitimate DOI 404s)
        self.http_404 = 0
        self.infra_failures = 0  # 429/5xx/timeouts: real infrastructure failures
        self.by_host: dict[str, dict[str, int]] = {}
        self.statuses: dict[str, int] = {}
        self.request_ms: list[float] = []
        self.api_calls = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.field_compares = 0
        self.sample_urls: list[str] = []

    def to_dict(self) -> dict:
        return {
            "http_requests": self.requests,
            "http_non_200": self.failed,
            "http_404": self.http_404,
            "infra_failures": self.infra_failures,
            "failure_rate_all_non_200": round(self.failed / self.requests, 4) if self.requests else 0.0,
            "infra_failure_rate": round(self.infra_failures / self.requests, 4) if self.requests else 0.0,
            "by_host": self.by_host,
            "http_statuses": self.statuses,
            "api_lookups": self.api_calls,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "field_compares": self.field_compares,
            "sample_request_urls": self.sample_urls[:12],
        }


class _RequestsProxy:
    """Only metadata_verify's ``requests`` global is proxied, not the process one."""

    def __init__(self, real, counters: Counters) -> None:
        self._real = real
        self._c = counters

    def get(self, url: str, *args: Any, **kwargs: Any):
        host = urlparse(url).netloc or url
        self._c.requests += 1
        slot = self._c.by_host.setdefault(
            host, {"requests": 0, "non_200": 0, "http_404": 0, "infra_failures": 0}
        )
        slot["requests"] += 1
        if len(self._c.sample_urls) < 12:
            self._c.sample_urls.append(url[:160])
        started = time.perf_counter()
        try:
            resp = self._real.get(url, *args, **kwargs)
        except Exception:
            self._c.failed += 1
            self._c.infra_failures += 1
            slot["non_200"] += 1
            slot["infra_failures"] += 1
            self._c.statuses["exception"] = self._c.statuses.get("exception", 0) + 1
            self._c.request_ms.append((time.perf_counter() - started) * 1000.0)
            raise
        elapsed = (time.perf_counter() - started) * 1000.0
        self._c.request_ms.append(elapsed)
        self._c.statuses[str(resp.status_code)] = self._c.statuses.get(str(resp.status_code), 0) + 1
        if resp.status_code == 404:
            self._c.failed += 1
            self._c.http_404 += 1
            slot["non_200"] += 1
            slot["http_404"] += 1
        elif resp.status_code != 200:
            self._c.failed += 1
            self._c.infra_failures += 1
            slot["non_200"] += 1
            slot["infra_failures"] += 1
        return resp


def _md5_key(key: str) -> str:
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def install_instrumentation(counters: Counters, cold: bool = False) -> dict:
    """Patch metadata_verify: cache lookup, HTTP, field-compare counter."""
    original = {
        "_cache_path": mv._cache_path,
        "requests": mv.requests,
        "_cached_json": mv._cached_json,
        "_cached_text": mv._cached_text,
        "_field_mismatches": mv._field_mismatches,
    }

    if cold:
        def cache_path(key: str) -> Path:
            return COLD_CACHE / f"{_md5_key(key)}.json"
    else:
        def cache_path(key: str) -> Path:
            hit = CB_CACHE / f"{_md5_key(key)}.json"
            if hit.exists():
                return hit
            return WARM_MISS_CACHE / f"{_md5_key(key)}.json"
    mv._cache_path = cache_path  # type: ignore[assignment]

    def _track(call):
        def wrapper(url: str, params: Optional[dict] = None):
            counters.api_calls += 1
            key = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
            if cache_path(key).exists():
                counters.cache_hits += 1
            else:
                counters.cache_misses += 1
            return call(url, params)
        return wrapper

    mv._cached_json = _track(original["_cached_json"])  # type: ignore[assignment]
    mv._cached_text = _track(original["_cached_text"])  # type: ignore[assignment]

    def field_mismatches(ref, cand):
        counters.field_compares += 1
        return original["_field_mismatches"](ref, cand)

    mv._field_mismatches = field_mismatches  # type: ignore[assignment]
    mv.requests = _RequestsProxy(requests, counters)  # type: ignore[assignment]
    return original


def restore_instrumentation(original: dict) -> None:
    mv._cache_path = original["_cache_path"]  # type: ignore[assignment]
    mv._cached_json = original["_cached_json"]  # type: ignore[assignment]
    mv._cached_text = original["_cached_text"]  # type: ignore[assignment]
    mv._field_mismatches = original["_field_mismatches"]  # type: ignore[assignment]
    mv.requests = original["requests"]  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _latency_stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def pct(p: float) -> float:
        idx = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
        return round(ordered[idx], 1)

    return {
        "n": len(ordered),
        "mean_ms": round(statistics.fmean(ordered), 1),
        "median_ms": round(statistics.median(ordered), 1),
        "p90_ms": pct(0.90),
        "p95_ms": pct(0.95),
        "max_ms": round(ordered[-1], 1),
        "min_ms": round(ordered[0], 1),
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


# ---------------------------------------------------------------------------
# Passes
# ---------------------------------------------------------------------------

def warm_pass(rows: list[dict]) -> tuple[list[dict], dict]:
    counters = Counters()
    original = install_instrumentation(counters, cold=False)
    records: list[dict] = []
    started_all = time.perf_counter()
    try:
        for i, row in enumerate(rows, 1):
            requested_before = counters.requests
            t0 = time.perf_counter()
            parsed = parse_reference(row["ref_string"], index=i)
            result = mv.verify_reference(parsed)
            elapsed = (time.perf_counter() - t0) * 1000.0
            network = counters.requests - requested_before
            records.append(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "corruption": row.get("corruption", ""),
                    "parsed_doi": parsed.doi,
                    "parsed_title": parsed.title,
                    "doi_present": bool(parsed.doi),
                    "doi_fabricated": str(row.get("corruption", "")).startswith("major:fake_doi"),
                    "status": result.status,
                    "doi_status": result.doi_status,
                    "title_sim": round(result.title_sim, 4),
                    "has_candidate": result.best is not None,
                    "sources": result.sources,
                    "mismatches": result.mismatches,
                    "elapsed_ms": round(elapsed, 1),
                    "network_requests": network,
                }
            )
            if i % 50 == 0 or i == len(rows):
                print(f"  warm {i}/{len(rows)} in {time.perf_counter() - started_all:.1f}s", flush=True)
    finally:
        restore_instrumentation(original)
    wall = time.perf_counter() - started_all
    return records, {"wall_s": round(wall, 2), "counters": counters.to_dict(), "request_ms": counters.request_ms}


def cold_pass(rows: list[dict], sample_size: int, refresh: bool) -> Optional[dict]:
    if sample_size <= 0:
        return None
    if COLD_RESULTS.exists() and not refresh:
        try:
            saved = json.loads(COLD_RESULTS.read_text(encoding="utf-8"))
            saved["reused"] = True
            print(f"  cold sample reused from {COLD_RESULTS.name} ({saved.get('n')} items)")
            return saved
        except Exception:
            pass

    rng = random.Random(SEED)
    doi_rows = [r for r in rows if parse_reference(r["ref_string"]).doi]
    no_doi_rows = [r for r in rows if not parse_reference(r["ref_string"]).doi]
    n_each = max(1, sample_size // 2)
    sample = rng.sample(doi_rows, min(n_each, len(doi_rows))) + rng.sample(
        no_doi_rows, min(n_each, len(no_doi_rows))
    )
    rng.shuffle(sample)

    COLD_CACHE.mkdir(parents=True, exist_ok=True)
    counters = Counters()
    original = install_instrumentation(counters, cold=True)
    records: list[dict] = []
    try:
        for i, row in enumerate(sample, 1):
            before = counters.requests
            failures_before = counters.failed
            infra_before = counters.infra_failures
            t0 = time.perf_counter()
            parsed = parse_reference(row["ref_string"])
            result = mv.verify_reference(parsed)
            elapsed = (time.perf_counter() - t0) * 1000.0
            records.append(
                {
                    "id": row["id"],
                    "label": row["label"],
                    "doi_present": bool(parsed.doi),
                    "status": result.status,
                    "doi_status": result.doi_status,
                    "title_sim": round(result.title_sim, 4),
                    "has_candidate": result.best is not None,
                    "elapsed_ms": round(elapsed, 1),
                    "network_requests": counters.requests - before,
                    "network_failures": counters.failed - failures_before,
                    "network_infra_failures": counters.infra_failures - infra_before,
                }
            )
            print(f"  cold {i}/{len(sample)} ({elapsed:.0f} ms)", flush=True)
    finally:
        restore_instrumentation(original)

    payload = {
        "generated_at": _utc_now(),
        "seed": SEED,
        "n": len(records),
        "sampling": "random stratified: half DOI-bearing, half no-DOI, seed fixed",
        "refs": records,
        "latency": {
            "all": _latency_stats([r["elapsed_ms"] for r in records]),
            "doi_present": _latency_stats([r["elapsed_ms"] for r in records if r["doi_present"]]),
            "no_doi": _latency_stats([r["elapsed_ms"] for r in records if not r["doi_present"]]),
        },
        "counters": counters.to_dict(),
        "request_ms": _latency_stats(counters.request_ms),
        "reused": False,
    }
    COLD_RESULTS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def summarize(records: list[dict], warm: dict, cold: Optional[dict]) -> dict:
    n = len(records)
    doi_items = [r for r in records if r["doi_present"]]
    genuine = [r for r in doi_items if not r["doi_fabricated"]]
    fabricated = [r for r in doi_items if r["doi_fabricated"]]
    no_doi = [r for r in records if not r["doi_present"]]

    def count(items: list[dict], key: str, value: str) -> int:
        return sum(1 for r in items if r[key] == value)

    doi_resolved = count(doi_items, "doi_status", "resolved")
    doi_not_found = count(doi_items, "doi_status", "not_found")
    doi_error = count(doi_items, "doi_status", "error")

    genuine_resolved = count(genuine, "doi_status", "resolved")
    fake_not_found = count(fabricated, "doi_status", "not_found")

    fallback_any = sum(1 for r in no_doi if r["has_candidate"])
    fallback_match = sum(1 for r in no_doi if r["title_sim"] >= 0.90)

    by_label_fallback = {}
    for label in ("Exact", "Minor", "Major"):
        items = [r for r in no_doi if r["label"] == label]
        by_label_fallback[label] = {
            "n": len(items),
            "candidate_found": sum(1 for r in items if r["has_candidate"]),
            "title_match_ge_0.90": sum(1 for r in items if r["title_sim"] >= 0.90),
        }

    field_compare_items = sum(1 for r in records if r["has_candidate"])
    # _field_mismatches runs only when a candidate record exists; the counter below
    # is the authoritative number (it also catches candidates from DOI resolution).
    field_compares = warm["counters"]["field_compares"]

    warm_lat = _latency_stats([r["elapsed_ms"] for r in records])
    lat_doi = _latency_stats([r["elapsed_ms"] for r in records if r["doi_present"]])
    lat_no_doi = _latency_stats([r["elapsed_ms"] for r in records if not r["doi_present"]])

    cold_reused = bool(cold and cold.get("reused"))
    cold_requests = (cold["counters"]["http_requests"] if cold else 0) if not cold_reused else 0
    cold_non_200 = (cold["counters"]["http_non_200"] if cold else 0) if not cold_reused else 0
    cold_404 = (cold["counters"]["http_404"] if cold else 0) if not cold_reused else 0
    cold_infra = (cold["counters"]["infra_failures"] if cold else 0) if not cold_reused else 0
    total_requests = warm["counters"]["http_requests"] + cold_requests
    total_non_200 = warm["counters"]["http_non_200"] + cold_non_200
    total_404 = warm["counters"]["http_404"] + cold_404
    total_infra = warm["counters"]["infra_failures"] + cold_infra
    total_api = warm["counters"]["api_lookups"] + (
        cold["counters"]["api_lookups"] if cold and not cold_reused else 0
    )

    return {
        "n": n,
        "doi_anchor": {
            "doi_present": len(doi_items),
            "resolved": doi_resolved,
            "not_found": doi_not_found,
            "error": doi_error,
            "anchor_hit_rate_all": _rate(doi_resolved, len(doi_items)),
            "genuine_doi": len(genuine),
            "genuine_resolved": genuine_resolved,
            "genuine_hit_rate": _rate(genuine_resolved, len(genuine)),
            "fabricated_doi": len(fabricated),
            "fabricated_404": fake_not_found,
            "fabricated_404_rate": _rate(fake_not_found, len(fabricated)),
            "note": "fabricated DOIs (10.9999/...) are expected to 404; they are excluded from genuine_hit_rate",
        },
        "title_fallback": {
            "no_doi_items": len(no_doi),
            "candidate_found": fallback_any,
            "candidate_found_rate": _rate(fallback_any, len(no_doi)),
            "title_match_ge_0_90": fallback_match,
            "title_match_rate": _rate(fallback_match, len(no_doi)),
            "by_label": by_label_fallback,
        },
        "field_comparison": {
            "triggered": field_compares,
            "rate": _rate(field_compares, n),
            "items_with_candidate": field_compare_items,
        },
        "latency_warm": {
            "all": warm_lat,
            "doi_present": lat_doi,
            "no_doi": lat_no_doi,
            "wall_s": warm["wall_s"],
        },
        "latency_cold": (
            {
                "n": cold["n"],
                "all": cold["latency"]["all"],
                "doi_present": cold["latency"]["doi_present"],
                "no_doi": cold["latency"]["no_doi"],
                "http_request_ms": cold["request_ms"],
                "reused": cold.get("reused", False),
            }
            if cold
            else None
        ),
        "external_requests": {
            "warm_http_requests": warm["counters"]["http_requests"],
            "cold_http_requests": cold["counters"]["http_requests"] if cold else 0,
            "total_http_requests": total_requests,
            "http_404_total": total_404,
            "infra_failures_total": total_infra,
            "infra_failure_rate": _rate(total_infra, total_requests),
            "non_200_total": total_non_200,
            "failure_rate_all_non_200": _rate(total_non_200, total_requests),
            "warm": warm["counters"],
            "cold": cold["counters"] if cold else None,
            "api_lookups": total_api,
            "budget": REQUEST_BUDGET,
            "within_budget": total_requests <= REQUEST_BUDGET,
            "cold_sample_reused": cold_reused,
            "note": "404 responses are DOI-resolution negatives (expected for 37 fabricated DOIs), not infrastructure failures; "
                    + ("cold-sample counters come from the saved first run and are not re-issued this run"
                       if cold_reused else "cold-sample counters were issued by this run"),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    argp = argparse.ArgumentParser(description="E5: retrieval statistics on CiteBench-CN.")
    argp.add_argument("--dataset", type=Path, default=DATASET)
    argp.add_argument("--limit", type=int, default=0)
    argp.add_argument("--cold-sample", type=int, default=12, help="items measured with the cache bypassed")
    argp.add_argument("--refresh-cold", action="store_true")
    argp.add_argument("--out", type=Path, default=OUT_FILE)
    args = argp.parse_args(argv)

    if not args.dataset.exists():
        print(f"[fatal] dataset not found: {args.dataset}", file=sys.stderr)
        return 2
    rows = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        rows = rows[: args.limit]
    print(f"[info] dataset={args.dataset.name} n={len(rows)} cache={CB_CACHE}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    WARM_MISS_CACHE.mkdir(parents=True, exist_ok=True)

    print("[1/2] warm pass (reads data/citebench_cn/cache, writes misses to data/experiments/cache_e5) ...")
    records, warm = warm_pass(rows)
    print(
        f"  http={warm['counters']['http_requests']} api_lookups={warm['counters']['api_lookups']} "
        f"cache_hits={warm['counters']['cache_hits']} misses={warm['counters']['cache_misses']} "
        f"wall={warm['wall_s']}s"
    )

    print("[2/2] cold sample (cache bypassed) ...")
    cold = cold_pass(rows, args.cold_sample, args.refresh_cold)
    if cold:
        print(
            f"  cold n={cold['n']} http={cold['counters']['http_requests']} "
            f"404={cold['counters']['http_404']} infra_failures={cold['counters']['infra_failures']}"
        )

    metrics = summarize(records, warm, cold)
    payload = {
        "experiment": "E5",
        "title": "CiteBench-CN 检索与延迟统计",
        "generated_at": _utc_now(),
        "seed": SEED,
        "code_snapshot": code_snapshot(),
        "dataset": {
            "path": str(args.dataset.relative_to(ROOT)),
            "n": len(rows),
            "sha256": _sha256(args.dataset),
        },
        "cache": {
            "citebench_cache_dir": str(CB_CACHE.relative_to(ROOT)),
            "citebench_cache_files": len(list(CB_CACHE.glob("*.json"))),
            "warm_miss_dir": str(WARM_MISS_CACHE.relative_to(ROOT)),
            "cold_dir": str(COLD_CACHE.relative_to(ROOT)),
        },
        "metrics": metrics,
        "per_ref": records,
        "limitations": [
            "warm 延迟是缓存命中场景（复跑/演示），不代表首次联网核验的等待时间；首次联网见 latency_cold。",
            "cold 样本 n≈20，仅用于量级估计，不是全量 250 条的冷启动测量。",
            "DOI 404 率按构造包含 37 条虚构 DOI，故 all 口径的 anchor 命中率天然偏低，另给 genuine 口径。",
            "字段比对触发率统计的是 _field_mismatches 的实际调用次数，不区分字段是否真的不一致。",
            "延迟在单线程顺序执行下测量，未计入 Web 端上传/排队/渲染时间。",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[done] doi_hit={metrics['doi_anchor']['anchor_hit_rate_all']:.3f} "
        f"genuine={metrics['doi_anchor']['genuine_hit_rate']:.3f} "
        f"fallback={metrics['title_fallback']['title_match_rate']:.3f} "
        f"field_cmp={metrics['field_comparison']['rate']:.3f} "
        f"lat_med={metrics['latency_warm']['all']['median_ms']}ms "
        f"requests={metrics['external_requests']['total_http_requests']}"
    )
    print(f"[done] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
