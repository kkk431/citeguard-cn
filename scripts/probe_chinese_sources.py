"""Probe free Chinese metadata sources for possible integration.

Goal: find out whether any *public* source can verify Chinese-language references
that OpenAlex/Crossref miss, without scraping licensed databases (CNKI/万方 are
not options: their content is not openly licensed and their pages forbid
automated access).

Findings (2026-10, run from a mainland network):
- ``https://doi.org/<CNKI DOI>`` (China DOI registry) returns a small
  "多重解析地址选择页面" page that *does* contain 题名/作者/来源/DOI码. This is
  integrated as ``doi:landing`` in ``metadata_verify`` because it is registered
  DOI metadata, not full text.
- Semantic Scholar returned 429 without a key.
- paper.edu.cn was under maintenance; ChinaXiv had TLS problems.
- NSSD (ncpssd.org) requires session cookies and is not a stable API.

Usage:
    python scripts/probe_chinese_sources.py
"""
from __future__ import annotations

import requests

UA = {"User-Agent": "CiteGuard-CN-source-probe/0.1"}
TITLE = "累积生态风险与青少年的学业和社交能力"
CNKI_DOI = "10.15886/j.cnki.hnus.202410.0119"


def show(name: str, resp) -> None:
    print(f"\n== {name} -> HTTP {resp.status_code} ({len(resp.content)}B)")
    text = resp.text[:400].replace("\n", " ")
    print(text)


def main() -> int:
    # 1) DOI content negotiation for a China-registered DOI
    try:
        r = requests.get(
            f"https://doi.org/{CNKI_DOI}",
            headers={**UA, "Accept": "application/vnd.citationstyles.csl+json"},
            timeout=25,
            allow_redirects=True,
        )
        show("doi.org content negotiation (CNKI DOI)", r)
    except Exception as exc:  # noqa: BLE001
        print("doi.org error", type(exc).__name__, exc)

    # 2) Semantic Scholar search
    try:
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": TITLE, "limit": 5, "fields": "title,year,venue,authors,externalIds"},
            headers=UA,
            timeout=25,
        )
        show("Semantic Scholar search", r)
    except Exception as exc:  # noqa: BLE001
        print("semantic scholar error", type(exc).__name__, exc)

    # 3) ChinaXiv search page (HTML)
    for url, params in (
        ("https://www.chinaxiv.org/search", {"keyword": TITLE}),
        ("http://www.chinaxiv.org/abs/202301.00001", None),
    ):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=25)
            show("ChinaXiv " + url, r)
        except Exception as exc:  # noqa: BLE001
            print("chinaxiv error", url, type(exc).__name__)

    # 4) 中国科技论文在线 search page
    try:
        r = requests.get(
            "https://www.paper.edu.cn/search/search_list",
            params={"search_type": "paper", "search_key": TITLE},
            headers=UA,
            timeout=25,
        )
        show("paper.edu.cn search", r)
    except Exception as exc:  # noqa: BLE001
        print("paper.edu.cn error", type(exc).__name__)

    # 5) NSSD (国家哲学社会科学文献中心) search page
    try:
        r = requests.get(
            "https://www.ncpssd.org/Literature/search",
            params={"q": TITLE},
            headers=UA,
            timeout=25,
        )
        show("ncpssd search", r)
    except Exception as exc:  # noqa: BLE001
        print("ncpssd error", type(exc).__name__)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
