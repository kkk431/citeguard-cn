"""Build the 30-item Live stance annotation kit.

Each row pairs a held-out claim with the abstract of the paper it cites.
The annotator decides whether the cited source supports / partially supports /
contradicts the sentence, or provides no evidence. Product output is NOT shown.
"""
from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

FIELDS = [
    "seq",
    "claim_id",
    "sentence",
    "page_title",
    "page_url",
    "source_title",
    "source_doi",
    "reference_index",
    "source_abstract",
    "stance_decision",
    "confidence_1_5",
    "note",
]

OPENALEX = "https://api.openalex.org/works"


def _abstract(work: dict) -> str:
    inv = work.get("abstract_inverted_index") or {}
    if not inv:
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in inv.items():
        for pos in positions:
            pairs.append((int(pos), word))
    return " ".join(word for _, word in sorted(pairs))


def _norm_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)


def fetch_abstracts(dois: list[str], timeout: int = 60) -> dict[str, str]:
    wanted = [d for d in dict.fromkeys(_norm_doi(d) for d in dois) if d]
    out: dict[str, str] = {}
    for start in range(0, len(wanted), 25):
        chunk = wanted[start : start + 25]
        # OpenAlex OR syntax: only the first value carries the field prefix.
        flt = "doi:" + "|".join(chunk)
        params = {
            "filter": flt,
            "per-page": "50",
            "select": "doi,title,abstract_inverted_index",
        }
        url = OPENALEX + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "citeguard-live-annotation/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - offline is acceptable, leave blanks
            print(f"warning: abstract fetch failed: {exc}")
            continue
        for work in payload.get("results", []):
            key = _norm_doi(work.get("doi", ""))
            if key:
                out[key] = _abstract(work)
    return out


def build(claims_path: Path, out_dir: Path, fetch: bool = True) -> dict:
    rows_in = [json.loads(line) for line in claims_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows_in) != 30:
        raise ValueError(f"expected 30 held-out claims, got {len(rows_in)}")
    abstracts = fetch_abstracts([r.get("source_doi", "") for r in rows_in]) if fetch else {}
    rows = []
    for i, claim in enumerate(rows_in, 1):
        doi = _norm_doi(claim.get("source_doi", ""))
        rows.append(
            {
                "seq": i,
                "claim_id": claim.get("id", ""),
                "sentence": claim.get("sentence", ""),
                "page_title": claim.get("page_title", ""),
                "page_url": claim.get("page_url", ""),
                "source_title": claim.get("source_title", ""),
                "source_doi": doi,
                "reference_index": claim.get("reference_index", ""),
                "source_abstract": abstracts.get(doi, ""),
                "stance_decision": "",
                "confidence_1_5": "",
                "note": "",
            }
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "live_stance_30.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    have = sum(1 for r in rows if r["source_abstract"])
    readme = f"""# Live 立场标注（30 条）

请独立判断：**被引论文的摘要是否支持这句话**。

- `support`：摘要直接支持句子的核心断言；
- `partial`：只支持一部分，或有条件/范围差异；
- `contradict`：摘要给出相反结论或方向；
- `no_evidence`：摘要没有涉及该断言，或只有背景性提及。

不要看产品输出，不要按“机器判定”填；每行填 `stance_decision` 和 1–5 置信度。
`source_abstract` 为空的行说明 OpenAlex 没有摘要，可点 `source_doi` 查原文；查不到就标 `no_evidence` 并在 `note` 写“摘要不可得”。

预计 40–50 分钟。填完后运行：
`python scripts/score_live_stance_kit.py --csv live_stance_30.csv --out agreement.json`

摘要可得：{have}/{len(rows)}。
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    return {"rows": len(rows), "abstracts": have, "out": str(out_dir)}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default="data/live_eval/claims_holdout.jsonl")
    ap.add_argument("--out", default="dist/live_annotation")
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()
    print(json.dumps(build(Path(args.claims), Path(args.out), not args.no_fetch), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
