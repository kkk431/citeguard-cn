"""Generate a realistic demo paper from OpenAlex Chinese metadata.

The generated file is a *demo*: 8 real references (with abstracts, so the
claim-support judge can run), 2 minor metadata corruptions and 2 fabricated
references. It powers the "用示例论文试试" button on the home page.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parents[1] / "web" / "static" / "samples" / "sample_paper.txt"
API = "https://api.openalex.org/works"
CJK = re.compile(r"[\u4e00-\u9fff]")


def _reconstruct(inv: dict | None) -> str:
    if not inv:
        return ""
    pairs = []
    for word, positions in inv.items():
        if isinstance(positions, list):
            for p in positions:
                pairs.append((int(p), word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pairs)


def _first_sentence(abstract: str) -> str:
    abstract = re.sub(r"\s+", " ", abstract or "").strip()
    m = re.search(r"[。！？!?]|\.(?=\s)", abstract)
    sentence = abstract[: m.end()] if m else abstract
    sentence = sentence.strip("。.！？!?;；\n ")
    if len(sentence) < 20:
        sentence = abstract[:140].strip()
    return sentence[:160].strip()


def fetch_works(need: int = 8) -> list[dict]:
    works: list[dict] = []
    for page in range(1, 10):
        r = requests.get(
            API,
            params={
                "filter": "language:zh,has_doi:true",
                "per-page": 100,
                "page": page,
                "select": (
                    "id,doi,title,publication_year,authorships,primary_location,"
                    "biblio,type,abstract_inverted_index"
                ),
                "mailto": "citeguard@example.org",
            },
            timeout=30,
        )
        if r.status_code != 200:
            break
        for w in r.json().get("results", []):
            title = (w.get("title") or "").strip()
            doi = (w.get("doi") or "").replace("https://doi.org/", "")
            src = ((w.get("primary_location") or {}).get("source") or {}) or {}
            authors = [(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])]
            biblio = w.get("biblio") or {}
            abstract = _reconstruct(w.get("abstract_inverted_index"))
            if not (title and CJK.search(title) and doi and authors and src.get("display_name")):
                continue
            if len(abstract) < 80:
                continue
            claim = _first_sentence(abstract)
            if len(claim) < 20:
                continue
            works.append(
                {
                    "title": title,
                    "doi": doi,
                    "year": w.get("publication_year"),
                    "authors": [a for a in authors if a],
                    "venue": src.get("display_name", ""),
                    "volume": biblio.get("volume") or "",
                    "issue": biblio.get("issue") or "",
                    "first_page": biblio.get("first_page") or "",
                    "last_page": biblio.get("last_page") or "",
                    "abstract": abstract,
                    "claim": claim,
                }
            )
            if len(works) >= need:
                return works
    return works


def render(w: dict, idx: int) -> str:
    authors = w["authors"][:3]
    author_str = ", ".join(authors) + ("等" if len(w["authors"]) > 3 else "")
    pages = ""
    if w["first_page"] and w["last_page"]:
        pages = f": {w['first_page']}-{w['last_page']}"
    elif w["first_page"]:
        pages = f": {w['first_page']}"
    vol = w["volume"]
    issue = f"({w['issue']})" if w["issue"] else ""
    return (
        f"[{idx}] {author_str}. {w['title']}[J]. {w['venue']}, {w['year']}, "
        f"{vol}{issue}{pages}. DOI: {w['doi']}."
    )


def corrupt_minor(w: dict) -> dict:
    c = dict(w)
    if c.get("year"):
        c["year"] = int(c["year"]) + 1
    return c


def corrupt_major(w: dict, idx: int) -> dict:
    c = dict(w)
    c["title"] = f"面向复杂场景的{['智能引文核验','多模态文献理解','学术可信计算'][idx % 3]}方法研究"
    c["doi"] = f"10.9999/fake.{idx:04d}.2024"
    return c


def main() -> None:
    works = fetch_works(8)
    if len(works) < 8:
        print(f"only fetched {len(works)} works with abstracts; abort")
        sys.exit(1)
    refs = [render(w, i + 1) for i, w in enumerate(works[:8])]
    refs.append(render(corrupt_minor(works[0]), 9))
    refs.append(render(corrupt_minor(works[1]), 10))
    refs.append(render(corrupt_major(works[2], 1), 11))
    refs.append(render(corrupt_major(works[3], 2), 12))

    # Build the body from the cited abstracts: 8 supported claims, then two
    # deliberately mismatched claims (9/10) and two fabricated references (11/12).
    claims = [w["claim"] for w in works[:8]]
    body_sentences = [f"{claims[i]}[{i + 1}]。" for i in range(8)]
    # mismatched claims: reuse another paper's abstract sentence
    body_sentences.append(f"{claims[2]}[9]。")
    body_sentences.append(f"{claims[3]}[10]。")
    body_sentences.append(f"{claims[4]}[11]。")
    body_sentences.append(f"{claims[5]}[12]。")

    body = (
        "# 示例论文：中文论文引文的可信核验方法研究\n\n"
        "## 摘要\n"
        "本文讨论中文论文中参考文献的真实性、引用支持度与著录规范问题，并给出一个可复现的核验流程。\n\n"
        "## 1 引言\n"
        + "".join(body_sentences[:4])
        + "\n\n## 2 方法\n"
        + "".join(body_sentences[4:8])
        + "\n\n## 3 讨论\n"
        + "".join(body_sentences[8:])
        + "\n\n## 参考文献\n"
        + "\n".join(refs)
        + "\n"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT} ({len(refs)} references, {len(body_sentences)} claims)")


if __name__ == "__main__":
    main()
