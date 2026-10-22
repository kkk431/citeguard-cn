"""Fetch GB/T-style Chinese reference lists from journal platforms that publish
free full text (软件学报 / 自动化学报 / 计算机研究与发展 等).

OpenAlex is queried for open-access Chinese works; only PDFs hosted on known
Chinese journal platforms are kept, because those are the ones that print
references in GB/T 7714 style (``[1] 作者. 题名[J]. 刊名, 年, 卷(期): 页码.``).

Everything lands in ``data/real_corpus/gbt/`` (git-ignored, local testing only).

Usage:
    python scripts/fetch_gbt_corpus.py --limit 12
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "real_corpus" / "gbt"
API = "https://api.openalex.org/works"

# Journal platforms that publish free full text and use GB/T 7714 references.
DOMAINS = (
    "jos.org.cn",
    "aas.net.cn",
    "crad.ict.ac.cn",
    "jcst.ict.ac.cn",
    "cjc.ict.ac.cn",
    "joca.cn",
    "ejournal.org.cn",
    "ict.ac.cn",
    "jfcs.org.cn",
    "jws.org.cn",
    "jss.org.cn",
)


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def candidates(pages: int = 6, per_page: int = 100) -> list[dict]:
    found: list[dict] = []
    for page in range(1, pages + 1):
        params = {
            "filter": "language:zh,is_oa:true,has_fulltext:true",
            "per-page": per_page,
            "page": page,
            "sort": "cited_by_count:desc",
            "select": "id,doi,title,publication_year,best_oa_location,primary_location,type",
            "mailto": "citeguard@example.org",
        }
        try:
            resp = requests.get(API, params=params, timeout=40)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"  openalex page {page} failed: {type(exc).__name__}")
            break
        results = resp.json().get("results", [])
        if not results:
            break
        for w in results:
            title = w.get("title") or ""
            if not _has_cjk(title):
                continue
            loc = w.get("best_oa_location") or {}
            pdf = loc.get("pdf_url") or ""
            if not pdf:
                continue
            if not any(d in pdf for d in DOMAINS):
                continue
            found.append(
                {
                    "id": w.get("id"),
                    "doi": w.get("doi"),
                    "title": title,
                    "year": w.get("publication_year"),
                    "pdf_url": pdf,
                    "landing": loc.get("landing_page_url") or "",
                }
            )
        time.sleep(0.3)
    return found


def download(item: dict) -> dict:
    safe = "".join(c for c in (item["id"] or "x").rsplit("/", 1)[-1] if c.isalnum())
    path = OUT / f"{safe}.pdf"
    if path.exists() and path.stat().st_size > 10000:
        return {**item, "file": str(path), "bytes": path.stat().st_size, "status": "cached"}
    last = ""
    for verify in (True, False):
        try:
            resp = requests.get(
                item["pdf_url"],
                timeout=90,
                headers={"User-Agent": "Mozilla/5.0 (CiteGuard-CN parser test)"},
                verify=verify,
            )
            if resp.status_code != 200:
                last = f"http_{resp.status_code}"
                continue
            if not resp.content.startswith(b"%PDF"):
                last = "not_pdf"
                continue
            path.write_bytes(resp.content)
            return {**item, "file": str(path), "bytes": len(resp.content), "status": "ok"}
        except Exception as exc:  # noqa: BLE001
            last = type(exc).__name__
    return {**item, "status": last or "failed", "bytes": 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--pages", type=int, default=6)
    args = ap.parse_args(argv)
    import urllib3

    urllib3.disable_warnings()

    OUT.mkdir(parents=True, exist_ok=True)
    cands = candidates(args.pages)
    print(f"candidates on Chinese journal platforms: {len(cands)}")
    kept: list[dict] = []
    for item in cands:
        res = download(item)
        print(f"  {res['status']:>10} {res['bytes']:>9}  {res['title'][:44]}")
        if res["status"] in {"ok", "cached"}:
            kept.append(res)
        if len(kept) >= args.limit:
            break
        time.sleep(0.3)
    (OUT / "manifest.json").write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nkept {len(kept)} pdfs -> {OUT}")
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
