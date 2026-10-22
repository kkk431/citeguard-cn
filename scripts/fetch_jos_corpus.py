"""Download GB/T 7714-style Chinese journal papers (软件学报 全文 PDF) for parser
testing.

软件学报 (jos.org.cn) publishes free full-text PDFs of Chinese papers whose
reference lists follow GB/T 7714 with ``[J]/[C]/[M]/[D]`` type marks — exactly
the style GitHub-hosted sample papers do not cover.

Output: ``data/real_corpus/gbt/pdf/<id>.pdf`` (git-ignored, local testing only).

Usage:
    python scripts/fetch_jos_corpus.py --limit 12
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
OUT = ROOT / "data" / "real_corpus" / "gbt" / "pdf"
HOME = "https://www.jos.org.cn/jos/home"
PDF = "https://www.jos.org.cn/jos/article/pdf/{pid}"
UA = {"User-Agent": "Mozilla/5.0 (CiteGuard-CN parser test)"}


def paper_ids(limit: int = 40) -> list[str]:
    html = requests.get(HOME, timeout=40, headers=UA, verify=False).text
    ids = re.findall(r"jos/article/abstract/(\d+)", html)
    unique: list[str] = []
    for pid in ids:
        if pid not in unique:
            unique.append(pid)
    return unique[:limit]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--candidates", type=int, default=30)
    args = ap.parse_args(argv)
    import urllib3

    urllib3.disable_warnings()

    OUT.mkdir(parents=True, exist_ok=True)
    kept: list[dict] = []
    for pid in paper_ids(args.candidates):
        if len(kept) >= args.limit:
            break
        path = OUT / f"jos_{pid}.pdf"
        if path.exists() and path.stat().st_size > 50000:
            kept.append({"id": pid, "file": str(path), "bytes": path.stat().st_size, "status": "cached"})
            print(f"  cached {path.stat().st_size:>9}  {pid}")
            continue
        try:
            resp = requests.get(PDF.format(pid=pid), timeout=90, headers=UA, verify=False)
            if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
                print(f"  skip  {pid}: http {resp.status_code}")
                continue
            if len(resp.content) < 50000:  # truncated / error page
                print(f"  skip  {pid}: too small")
                continue
            path.write_bytes(resp.content)
            kept.append({"id": pid, "file": str(path), "bytes": len(resp.content), "status": "ok"})
            print(f"  ok    {len(resp.content):>9}  {pid}")
        except Exception as exc:  # noqa: BLE001
            print(f"  skip  {pid}: {type(exc).__name__}")
        time.sleep(0.4)

    (OUT.parent / "manifest.json").write_text(
        json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nkept {len(kept)} pdfs -> {OUT}")
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
