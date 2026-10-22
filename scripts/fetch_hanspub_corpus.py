"""Collect a real-world Chinese reference corpus from Hans Publishers (OA).

Downloads, for a handful of open-access Chinese articles:
- the PDF (if reachable),
- the reference list exactly as published on the article page,
- article metadata (title, year, doi, journal).

Everything lands in ``data/real_corpus/`` (git-ignored) and is used only to
measure how well the parser handles real reference lists.

Usage:
    python scripts/fetch_hanspub_corpus.py --articles 12
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "real_corpus"
BASE = "https://www.hanspub.org/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; CiteGuard-CN parser test)"}


def _text(html: str) -> str:
    import html as _html

    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|tr|li|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = _html.unescape(text).replace("\u00a0", " ")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _references_block(html: str) -> str:
    """Return the reference list as plain text (the part after the heading)."""
    idx = -1
    for marker in ("参考文献", "參考文獻"):
        idx = html.find(marker)
        if idx > 0:
            break
    if idx < 0:
        return ""
    block = html[idx:]
    # Stop at the next typical post-reference section.
    for stop in ("相关文章", "参考文献", "文章引用", "版权"):
        pass
    plain = _text(block)
    return plain


def _pdf_url(html: str) -> str:
    m = re.search(r'(?:href|src)="(//[^"]*pdf\.hanspub\.org[^"]+\.pdf)"', html, re.I)
    if m:
        return "https:" + m.group(1)
    m = re.search(r'href="([^"]+\.pdf)"', html, re.I)
    return urljoin(BASE, m.group(1)) if m else ""


def _title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def article_links(n: int = 40) -> list[str]:
    html = requests.get(BASE, timeout=40, headers=UA).text
    links = re.findall(r"paperinformation\?paperid=(\d+)", html)
    seen: list[str] = []
    for pid in links:
        url = f"{BASE}journal/paperinformation?paperid={pid}"
        if url not in seen:
            seen.append(url)
    return seen[:n]


def collect(limit: int = 12, candidate_pages: int = 30) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    corpus: list[dict] = []
    refs_dir = OUT / "refs"
    refs_dir.mkdir(exist_ok=True)
    for url in article_links(candidate_pages):
        if len(corpus) >= limit:
            break
        try:
            resp = requests.get(url, timeout=40, headers=UA)
            if resp.status_code != 200:
                continue
            html = resp.text
            refs = _references_block(html)
            # Heuristic: a usable reference list has at least 3 numbered entries.
            marks = len(re.findall(r"\[\d+\]", refs))
            if marks < 3:
                continue
            pid = re.search(r"paperid=(\d+)", url).group(1)
            pdf = _pdf_url(html)
            pdf_path = ""
            if pdf:
                try:
                    pdf_resp = requests.get(pdf, timeout=60, headers=UA, verify=False)
                    if pdf_resp.status_code == 200 and pdf_resp.content.startswith(b"%PDF"):
                        target = OUT / f"hanspub_{pid}.pdf"
                        target.write_bytes(pdf_resp.content)
                        pdf_path = str(target)
                except Exception:  # noqa: BLE001 - pdf is optional
                    pdf_path = ""
            refs_path = refs_dir / f"hanspub_{pid}.txt"
            refs_path.write_text(refs, encoding="utf-8")
            corpus.append(
                {
                    "source": "hanspub",
                    "url": url,
                    "title": _title(html),
                    "refs_file": str(refs_path),
                    "ref_count_marks": marks,
                    "pdf_file": pdf_path,
                }
            )
            print(f"  ok refs={marks:3d} pdf={'y' if pdf_path else 'n'}  {_title(html)[:44]}")
        except Exception as exc:  # noqa: BLE001 - keep going
            print(f"  skip {type(exc).__name__}: {url}")
        time.sleep(0.5)
    (OUT / "hanspub_manifest.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\ncollected {len(corpus)} reference lists -> {OUT}")
    return 0 if corpus else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--articles", type=int, default=12)
    ap.add_argument("--candidate-pages", type=int, default=30)
    args = ap.parse_args(argv)
    import urllib3

    urllib3.disable_warnings()
    return collect(args.articles, args.candidate_pages)


if __name__ == "__main__":
    sys.exit(main())
