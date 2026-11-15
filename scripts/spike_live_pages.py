"""t25 Live spike：页面文献列表 → ``[n]`` → 被引来源定位。

运行（在仓库根目录）::

    python scripts/spike_live_pages.py

它会抓取 2 个 arXiv HTML 页面 + 1 个 Wikipedia 页面，用 readability-lxml
抽取正文，解析参考文献列表并建立 ``[n] → reference`` 映射；随后对每页至少
5 条带 ``[n]`` 的引用句做“来源定位”，并（默认）调用现有
``check_claim(..., phase="retrieve")`` 做对照。结果写入
``data/experiments/live_spike.json``。

这是研究 spike，不是产品路径：不写数据库、不调用判官、不下载模型。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from citeguard.live_page import (  # noqa: E402
    EXTRACTOR_LICENSE,
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    build_page_model,
    fetch_html,
    find_markers,
    locate_claim,
    normalise_doi,
    reference_matches,
)

HOLDOUT_CLAIMS = ROOT / "data" / "live_eval" / "claims_holdout.jsonl"
DEFAULT_OUT = ROOT / "data" / "experiments" / "live_spike.json"
TARGET_RATIO = 0.80

PAGES = [
    {
        "id": "arxiv-2611.07772",
        "url": "https://arxiv.org/html/2611.07772",
        "title": "Adapt the Object to the Subject: Representative Study Material for Empirical Software Engineering",
        "claims": "holdout",
    },
    {
        "id": "arxiv-2610.18926",
        "url": "https://arxiv.org/html/2610.18926",
        "title": "Personalising Deformable Image Registration with Clinical Context and Deformation Guidance",
        "claims": "holdout",
    },
    {
        "id": "wiki-rag",
        "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
        "title": "Retrieval-augmented generation",
        "claims": "wiki",
    },
]


def _load_holdout_claims(page_url: str) -> list[dict]:
    rows: list[dict] = []
    if not HOLDOUT_CLAIMS.exists():
        return rows
    with HOLDOUT_CLAIMS.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("page_url") == page_url:
                rows.append(row)
    return rows


def _wiki_claims(model: dict, limit: int = 5) -> list[dict]:
    """Pick real sentences that cite exactly one reference.

    Wikipedia's citation list is mixed: 11/22 entries carry a DOI, the rest only
    a URL/title.  We therefore match by DOI when present and fall back to title.
    Unique reference indexes are used first; if a page has fewer than ``limit``
    citable references, later sentences may reuse the same reference.
    """

    references = {entry["index"]: entry for entry in model["references"]}
    sentences = re.split(r"(?<=[.!?])\s+", model.get("body_text", ""))
    candidates: list[tuple[str, int, dict]] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not (80 <= len(sentence) <= 420):
            continue
        numbers = sorted({number for marker in find_markers(sentence) for number in marker["numbers"]})
        if len(numbers) != 1:
            continue
        reference = references.get(numbers[0])
        if not reference or not reference.get("title"):
            continue
        candidates.append((sentence, numbers[0], reference))

    chosen: list[tuple[str, int, dict]] = []
    for require_fresh in (True, False):
        seen = {index for _, index, _ in chosen}
        for sentence, index, reference in candidates:
            if len(chosen) >= limit:
                break
            if require_fresh and index in seen:
                continue
            if any(sentence == item[0] for item in chosen):
                continue
            chosen.append((sentence, index, reference))
            seen.add(index)
        if len(chosen) >= limit:
            break

    return [
        {
            "id": f"wiki-{position + 1:02d}",
            "sentence": sentence,
            "source_title": reference["title"],
            "source_doi": reference.get("doi") or "",
            "reference_index": index,
            "page_url": model["page_url"],
        }
        for position, (sentence, index, reference) in enumerate(chosen)
    ]


def _hit_method(reference: dict, gold_doi: str, gold_title: str) -> str:
    if gold_doi and normalise_doi(reference.get("doi")) == normalise_doi(gold_doi):
        return "doi"
    if reference_matches(reference, "", gold_title):
        return "title"
    return "none"


def _evaluate_mapping(claim: dict, model: dict) -> dict:
    located = locate_claim(claim["sentence"], model)
    references = [reference for item in located for reference in item["references"]]
    methods = [
        method
        for reference in references
        if (method := _hit_method(reference, claim.get("source_doi", ""), claim.get("source_title", ""))) != "none"
    ]
    return {
        "claim_id": claim.get("id", ""),
        "sentence": claim["sentence"][:400],
        "markers": [item["marker"] for item in located],
        "mapped": all(item["mapped"] for item in located) if located else False,
        "located": [reference.get("index") for reference in references],
        "hit": bool(methods),
        "hit_method": methods[0] if methods else "none",
        "gold_doi": claim.get("source_doi", ""),
        "gold_title": claim.get("source_title", ""),
    }


def _evaluate_check_claim(claim: dict, model: dict) -> dict:
    started = time.monotonic()
    try:
        from citeguard.live_check import check_claim

        result = check_claim(
            claim["sentence"],
            model["page_url"],
            model["page_title"],
            mode="fast",
            phase="retrieve",
        )
        candidates = result.get("candidates") or []
        methods = [
            method
            for candidate in candidates
            if (method := _hit_method(candidate, claim.get("source_doi", ""), claim.get("source_title", ""))) != "none"
        ]
        return {
            "claim_id": claim.get("id", ""),
            "ok": True,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "label": result.get("label"),
            "reason": str(result.get("reason") or "")[:200],
            "candidate_count": len(candidates),
            "hit": bool(methods),
            "hit_method": methods[0] if methods else "none",
            "top_candidates": [
                {
                    "title": (candidate.get("title") or "")[:160],
                    "doi": normalise_doi(candidate.get("doi")),
                }
                for candidate in candidates[:5]
            ],
        }
    except Exception as exc:  # network / service failure must be recorded, not fatal
        return {
            "claim_id": claim.get("id", ""),
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="JSON 输出路径")
    parser.add_argument("--check-claim", action="store_true", default=True, help="调用现有 check_claim 做对照（默认开）")
    parser.add_argument("--no-check-claim", dest="check_claim", action="store_false")
    parser.add_argument("--timeout", type=float, default=12.0, help="单页抓取超时（秒）")
    args = parser.parse_args(argv)

    generated_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    pages: list[dict] = []
    failures: list[dict] = []

    for definition in PAGES:
        record: dict = {"id": definition["id"], "url": definition["url"]}
        try:
            html = fetch_html(definition["url"], timeout=args.timeout)
        except Exception as exc:
            failures.append({"id": definition["id"], "url": definition["url"], "error": str(exc)[:300]})
            print(f"[FAIL] {definition['id']}: {exc}")
            continue
        model = build_page_model(html, definition["url"], definition["title"])
        record.update(
            {
                "page_title": model["page_title"],
                "extractor": model["extractor"],
                "text_chars": model["text_chars"],
                "reference_count": model["reference_count"],
                "markers_total": model["markers_total"],
                "markers_mapped": model["markers_mapped"],
                "mapped_ratio": model["mapped_ratio"],
                "samples": model["samples"],
                "reference_preview": model["references"][:5],
            }
        )
        if definition["claims"] == "holdout":
            claims = _load_holdout_claims(definition["url"])[:6]
        else:
            claims = _wiki_claims(model, limit=5)
        record["claims_total"] = len(claims)
        record["claims"] = [_evaluate_mapping(claim, model) for claim in claims]
        if args.check_claim:
            record["check_claim"] = [_evaluate_check_claim(claim, model) for claim in claims]
        pages.append(record)
        print(
            f"[OK] {definition['id']}: refs={model['reference_count']} "
            f"markers={model['markers_total']} mapped={model['markers_mapped']} "
            f"ratio={model['mapped_ratio']:.3f} mode={model['extractor']['mode']} "
            f"claims={len(claims)}"
        )

    markers_total = sum(page["markers_total"] for page in pages)
    markers_mapped = sum(page["markers_mapped"] for page in pages)
    claims_total = sum(page.get("claims_total", 0) for page in pages)
    claims_located = sum(1 for page in pages for claim in page["claims"] if claim["mapped"])
    claims_hit = sum(1 for page in pages for claim in page["claims"] if claim["hit"])
    check_claims = [entry for page in pages for entry in page.get("check_claim", [])]
    check_hit = sum(1 for entry in check_claims if entry.get("hit"))
    ratio = round(markers_mapped / markers_total, 4) if markers_total else 0.0

    summary = {
        "pages_requested": len(PAGES),
        "pages_ok": len(pages),
        "reference_count": sum(page["reference_count"] for page in pages),
        "markers_total": markers_total,
        "markers_mapped": markers_mapped,
        "mapped_ratio": ratio,
        "target_ratio": TARGET_RATIO,
        "target_met": bool(pages) and ratio >= TARGET_RATIO,
        "claims_total": claims_total,
        "claims_marker_mapped": claims_located,
        "claims_source_located": claims_hit,
        "check_claim_calls": len(check_claims),
        "check_claim_hits": check_hit,
        "check_claim_errors": sum(1 for entry in check_claims if not entry.get("ok")),
    }
    payload = {
        "generated_at": generated_at,
        "spike": "t25-live-page-mapping",
        "extractor": {
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "license": EXTRACTOR_LICENSE,
        },
        "summary": summary,
        "pages": pages,
        "failures": failures,
        "notes": [
            "映射率 = markers_mapped / markers_total（只统计正文中的锚点/标记，参考文献列表本身不计入分母）。",
            "claim 定位 = 该引用句的 [n] 所指页面文献是否与 gold DOI（或标题）一致；不做真伪判定。",
            "check_claim 对照走现有 Live 检索（phase=retrieve，不调用判官）；它目前只对 arXiv HTML 建映射。",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"summary: pages={summary['pages_ok']}/{summary['pages_requested']} "
        f"refs={summary['reference_count']} markers={markers_total} mapped={markers_mapped} "
        f"ratio={ratio:.3f} target_met={summary['target_met']} "
        f"claims={claims_total} located={claims_hit} "
        f"check_claim={check_hit}/{len(check_claims)}"
    )
    print(f"wrote {out_path}")
    return 0 if pages else 1


if __name__ == "__main__":
    raise SystemExit(main())
