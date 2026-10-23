"""Search-recall experiment for Chinese titles on OpenAlex/Crossref.

Question: for Chinese-titled papers that *are* in OpenAlex, does the current
title-search strategy find them? If yes, the remaining 'unverified' references
are a data-coverage problem, not a search problem. If no, there is headroom in
the query itself.

The known work IDs come from `data/citebench_cn/openalex_zh_works.json`.

Usage:
    python scripts/experiment_search_recall.py [--n 30]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard.metadata_verify import norm_title, title_sim  # noqa: E402

POOL = ROOT / "data" / "citebench_cn" / "openalex_zh_works.json"
OUT = ROOT / "data" / "experiments" / "search_recall.json"
MAILTO = "citeguard@example.org"


def _openalex(params: dict) -> list[dict]:
    p = {"per-page": 5, "mailto": MAILTO, **params}
    resp = requests.get("https://api.openalex.org/works", params=p, timeout=30)
    if resp.status_code != 200:
        return []
    return resp.json().get("results", []) or []


def _crossref(title: str) -> list[dict]:
    resp = requests.get(
        "https://api.crossref.org/works",
        params={"query.bibliographic": title, "rows": 5, "mailto": MAILTO},
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    return (resp.json().get("message") or {}).get("items", []) or []


def _hit(results: list[dict], work: dict, kind: str) -> bool:
    target_id = (work.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
    target_doi = (work.get("doi") or "").lower().replace("https://doi.org/", "")
    for item in results:
        if kind == "openalex":
            item_id = (item.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
            item_doi = (item.get("doi") or "").lower().replace("https://doi.org/", "")
            if item_id and item_id == target_id:
                return True
            if target_doi and item_doi and item_doi == target_doi:
                return True
        else:
            item_doi = (item.get("DOI") or "").lower()
            if target_doi and item_doi == target_doi:
                return True
    return False


def _best_sim(results: list[dict], title: str, kind: str) -> float:
    best = 0.0
    for item in results:
        if kind == "openalex":
            cand_title = item.get("title") or ""
        else:
            cand_title = (item.get("title") or [""])[0]
        best = max(best, title_sim(title, cand_title))
    return round(best, 3)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args(argv)

    works = json.loads(POOL.read_text(encoding="utf-8"))["works"]
    cjk = [w for w in works if any("\u4e00" <= ch <= "\u9fff" for ch in (w.get("title") or ""))]
    sample = cjk[: args.n]

    strategies = {
        "openalex_search": lambda t, y: _openalex({"search": t}),
        "openalex_title_search": lambda t, y: _openalex({"filter": f"title.search:{t}"}),
        "openalex_search_year": lambda t, y: _openalex(
            {"search": t, "filter": f"publication_year:{y}"}
        ),
        "crossref_bibliographic": lambda t, y: _crossref(t),
    }
    stats = {name: {"hit": 0, "sim_ge_078": 0, "n": 0} for name in strategies}
    rows: list[dict] = []
    for work in sample:
        title = work["title"]
        year = work.get("year") or 0
        row = {"id": work.get("id"), "title": title[:60], "year": year}
        for name, fn in strategies.items():
            try:
                results = fn(title, year)
            except Exception as exc:  # noqa: BLE001
                results = []
                row[f"{name}_error"] = type(exc).__name__
            hit = _hit(results, work, "openalex" if name.startswith("openalex") else "crossref")
            sim = _best_sim(results, title, "openalex" if name.startswith("openalex") else "crossref")
            row[name] = {"hit": hit, "best_sim": sim, "n": len(results)}
            stats[name]["hit"] += 1 if hit else 0
            stats[name]["sim_ge_078"] += 1 if sim >= 0.78 else 0
            stats[name]["n"] += 1
            time.sleep(0.2)
        rows.append(row)
        print(f"  {title[:40]:42} " + " ".join(
            f"{name}={'HIT' if row[name]['hit'] else '---'}" for name in strategies
        ))

    summary = {
        "sample": len(sample),
        "strategies": {
            name: {
                "recall_hit": round(s["hit"] / max(s["n"], 1), 3),
                "sim_ge_078": round(s["sim_ge_078"] / max(s["n"], 1), 3),
            }
            for name, s in stats.items()
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n== search recall on OpenAlex-indexed Chinese papers ==")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nreport -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
