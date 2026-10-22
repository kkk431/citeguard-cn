"""Fetch a small corpus of real open-access Chinese papers (PDF) for parser testing.

Only metadata + a handful of OA PDFs are downloaded to ``data/real_corpus/`` which
is git-ignored: third-party full texts are used locally for testing only and are
never redistributed.

Usage:
    python scripts/fetch_real_corpus.py --limit 12
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "real_corpus"
API = "https://api.openalex.org/works"
MAILTO = "citeguard@example.org"


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def fetch_candidates(limit: int = 40) -> list[dict]:
    params = {
        "filter": "language:zh,is_oa:true,has_fulltext:true",
        "per-page": min(limit, 50),
        "sort": "cited_by_count:desc",
        "select": "id,doi,title,publication_year,language,best_oa_location,primary_location,cited_by_count,type",
        "mailto": MAILTO,
    }
    resp = requests.get(API, params=params, timeout=40)
    resp.raise_for_status()
    works = resp.json().get("results", [])
    out = []
    for w in works:
        title = w.get("title") or ""
        if not _has_cjk(title):
            continue
        loc = w.get("best_oa_location") or {}
        pdf = loc.get("pdf_url") or ""
        landing = loc.get("landing_page_url") or ""
        if not pdf:
            continue
        out.append(
            {
                "id": w.get("id"),
                "doi": w.get("doi"),
                "title": title,
                "year": w.get("publication_year"),
                "type": w.get("type"),
                "pdf_url": pdf,
                "landing": landing,
                "cited_by": w.get("cited_by_count"),
            }
        )
    return out


def download(item: dict, out_dir: Path) -> dict:
    safe = "".join(c for c in (item["id"] or "x").rsplit("/", 1)[-1] if c.isalnum())
    path = out_dir / f"{safe}.pdf"
    if path.exists() and path.stat().st_size > 10000:
        return {**item, "file": str(path), "bytes": path.stat().st_size, "status": "cached"}
    last = ""
    # Many Chinese journal hosts have incomplete certificate chains; retry
    # without verification (content is only used locally for parser testing).
    for verify in (True, False):
        try:
            resp = requests.get(
                item["pdf_url"],
                timeout=60,
                headers={"User-Agent": "CiteGuard-CN-test/0.1"},
                verify=verify,
            )
            if resp.status_code != 200:
                last = f"http_{resp.status_code}"
                continue
            if not resp.content.startswith(b"%PDF"):
                last = f"not_pdf_{resp.headers.get('content-type', '?')[:30]}"
                continue
            path.write_bytes(resp.content)
            return {**item, "file": str(path), "bytes": len(resp.content), "status": "ok"}
        except Exception as exc:  # noqa: BLE001 - report and continue
            last = f"{type(exc).__name__}"
    return {**item, "status": last or "failed", "bytes": 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12, help="how many PDFs to keep")
    ap.add_argument("--candidates", type=int, default=40)
    args = ap.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    cands = fetch_candidates(args.candidates)
    print(f"candidates with pdf_url: {len(cands)}")
    picked: list[dict] = []
    for item in cands:
        res = download(item, OUT)
        print(f"  {res['status']:>12} {res['bytes']:>9}  {res['title'][:40]}")
        if res["status"] in {"ok", "cached"}:
            picked.append(res)
        if len(picked) >= args.limit:
            break
        time.sleep(0.3)

    manifest = OUT / "manifest.json"
    manifest.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nkept {len(picked)} pdfs -> {manifest}")
    return 0 if picked else 1


if __name__ == "__main__":
    sys.exit(main())
