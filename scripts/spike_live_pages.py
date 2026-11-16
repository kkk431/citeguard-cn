"""t27 Live 页面引用预检 spike：arXiv / PMC / Wikipedia 的 ``[n]`` 与作者年定位。

运行（在仓库根目录）::

    python scripts/spike_live_pages.py

抓取 3 个 arXiv HTML、2 个 PMC 页面、1 个 Wikipedia 页面，用 readability-lxml
抽取正文（抽取塌缩时回退原始 body），解析参考文献列表并建立引用标记 →
reference 的映射；随后对每页至少 5 条引用句做“来源定位”（只定位，不判断
支持/矛盾）。结果写入 ``data/experiments/live_spike.json``。

这是研究 spike，不是产品路径：不写数据库、不调用判官、不下载模型。PMC 页面
的标记既可能是 ``[n]`` 锚点，也可能是 ``(Author, year)`` 作者年形式；两者都
会被映射，无法无歧义映射时保持 ``mapped=false``，不猜测。
"""
from __future__ import annotations

import argparse
import json
import os
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
    locate_claim,
    normalise_doi,
    reference_matches,
    sentence_split,
)

HOLDOUT_CLAIMS = ROOT / "data" / "live_eval" / "claims_holdout.jsonl"
DEFAULT_OUT = ROOT / "data" / "experiments" / "live_spike.json"
TARGET_RATIO = 0.80
CLAIMS_PER_PAGE = 5

PAGES = [
    {
        "id": "arxiv-2611.07772",
        "url": "https://arxiv.org/html/2611.07772",
        "title": "Adapt the Object to the Subject: Representative Study Material for Empirical Software Engineering",
        "claims": "holdout",
        "cache": "arxiv_2611_07772.html",
    },
    {
        "id": "arxiv-2610.18926",
        "url": "https://arxiv.org/html/2610.18926",
        "title": "Personalising Deformable Image Registration with Clinical Context and Deformation Guidance",
        "claims": "holdout",
        "cache": "arxiv_2610_18926.html",
    },
    {
        "id": "arxiv-2610.24037",
        "url": "https://arxiv.org/html/2610.24037",
        "title": "",
        "claims": "holdout",
        "cache": "arxiv_2610_24037.html",
    },
    {
        "id": "pmc-13541550",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC13541550/",
        "title": "",
        "claims": "derive",
        "cache": "pmc_13541550.html",
    },
    {
        "id": "pmc-13198158",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC13198158/",
        "title": "",
        "claims": "derive",
        "cache": "pmc_13198158.html",
    },
    {
        "id": "wiki-rag",
        "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
        "title": "Retrieval-augmented generation",
        "claims": "derive",
        "cache": "wiki_rag.html",
    },
]


def _load_holdout_claims(page_url: str, limit: int = CLAIMS_PER_PAGE) -> list[dict]:
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
                if len(rows) >= limit:
                    break
    return rows


def _derive_claims(model: dict, limit: int = CLAIMS_PER_PAGE) -> list[dict]:
    """Pick real body sentences that cite exactly one locatable reference.

    PMC numbers citations as anchor text ``"1"`` (no brackets) and often uses
    ``(Author, year)``; ``locate_claim`` handles both.  Sentences whose citation
    cannot be mapped unambiguously are skipped rather than guessed.
    """

    chosen: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for sentence in sentence_split(model.get("body_text", "")):
        sentence = sentence.strip()
        if not (60 <= len(sentence) <= 500):
            continue
        located = locate_claim(sentence, model)
        if len(located) != 1 or not located[0]["mapped"]:
            continue
        references = located[0]["references"]
        if len(references) != 1:
            continue
        reference = references[0]
        key = (sentence, reference["index"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append(
            {
                "id": f"{model['page_url'].rstrip('/').rsplit('/', 1)[-1][:24]}-{len(chosen) + 1:02d}",
                "sentence": sentence[:500],
                "source_title": reference.get("title") or "",
                "source_doi": reference.get("doi") or "",
                "reference_index": reference["index"],
                "page_url": model["page_url"],
                "derived": True,
            }
        )
        if len(chosen) >= limit:
            break
    return chosen


def _looks_blocked(model: dict) -> bool:
    """True for bot-check / JS-stub pages that carry no article text."""

    text = model.get("body_text", "")
    title = (model.get("page_title") or "").lower()
    if model.get("reference_count"):
        return False
    if len(text) >= 1500:
        return False
    haystack = f"{title} {text[:800]}".lower()
    return any(
        marker in haystack
        for marker in ("checking your browser", "client challenge", "captcha", "enable javascript")
    ) or len(text) < 400


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
        "kinds": [item.get("kind", "numeric") for item in located],
        "mapped": all(item["mapped"] for item in located) if located else False,
        "located": [reference.get("index") for reference in references],
        "hit": bool(methods),
        "hit_method": methods[0] if methods else "none",
        "derived": bool(claim.get("derived")),
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
    parser.add_argument(
        "--check-claim",
        action="store_true",
        default=False,
        help="额外调用现有 check_claim（只对 arXiv 页面，phase=retrieve，默认关）",
    )
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("CITEGUARD_LIVE_CACHE", ""),
        help="抓取失败时读取本地缓存 HTML 的目录（默认取环境变量 CITEGUARD_LIVE_CACHE）",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="单页抓取超时（秒）")
    args = parser.parse_args(argv)

    generated_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    pages: list[dict] = []
    failures: list[dict] = []

    for definition in PAGES:
        record: dict = {"id": definition["id"], "url": definition["url"]}
        source = "network"
        fetch_error = ""
        try:
            html = fetch_html(definition["url"], timeout=args.timeout)
        except Exception as exc:
            fetch_error = str(exc)[:300]
            cache_path = (
                Path(args.cache_dir) / definition["cache"]
                if args.cache_dir and definition.get("cache")
                else None
            )
            if cache_path is not None and cache_path.exists():
                html = cache_path.read_text(encoding="utf-8", errors="replace")
                source = "cache"
                print(f"[CACHE] {definition['id']}: {fetch_error}")
            else:
                failures.append(
                    {"id": definition["id"], "url": definition["url"], "error": fetch_error}
                )
                print(f"[FAIL] {definition['id']}: {fetch_error}")
                continue
        model = build_page_model(html, definition["url"], definition["title"])
        cache_path = (
            Path(args.cache_dir) / definition["cache"]
            if args.cache_dir and definition.get("cache")
            else None
        )
        if source == "network" and cache_path is not None and cache_path.exists() and _looks_blocked(model):
            fetch_error = "页面返回验证/挑战页，已改用本地缓存"
            html = cache_path.read_text(encoding="utf-8", errors="replace")
            model = build_page_model(html, definition["url"], definition["title"])
            source = "cache"
            print(f"[CACHE] {definition['id']}: {fetch_error}")
        record.update(
            {
                "source": source,
                "fetch_error": fetch_error,
                "page_title": model["page_title"],
                "extractor": model["extractor"],
                "text_chars": model["text_chars"],
                "reference_count": model["reference_count"],
                "markers_total": model["markers_total"],
                "markers_mapped": model["markers_mapped"],
                "mapped_ratio": model["mapped_ratio"],
                "unique_markers": model["unique_markers"],
                "unique_mapped": model["unique_mapped"],
                "mapped_sources": model["mapped_sources"],
                "reference_sentences": model["reference_sentences"],
                "unmapped_markers": model["unmapped_markers"],
                "samples": model["samples"],
                "reference_preview": model["references"][:5],
            }
        )
        if definition["claims"] == "holdout":
            claims = _load_holdout_claims(definition["url"], limit=CLAIMS_PER_PAGE)
        else:
            claims = _derive_claims(model, limit=CLAIMS_PER_PAGE)
        record["claims_total"] = len(claims)
        record["claims_derived"] = sum(1 for claim in claims if claim.get("derived"))
        record["claims"] = [_evaluate_mapping(claim, model) for claim in claims]
        if args.check_claim and "arxiv.org" in definition["url"]:
            record["check_claim"] = [_evaluate_check_claim(claim, model) for claim in claims]
        pages.append(record)
        print(
            f"[OK] {definition['id']}: refs={model['reference_count']} "
            f"markers={model['markers_total']} mapped={model['markers_mapped']} "
            f"ratio={model['mapped_ratio']:.3f} mode={model['extractor']['mode']} "
            f"ref_sentences={model['reference_sentences']} claims={len(claims)}"
        )

    markers_total = sum(page["markers_total"] for page in pages)
    markers_mapped = sum(page["markers_mapped"] for page in pages)
    claims_total = sum(page.get("claims_total", 0) for page in pages)
    claims_located = sum(1 for page in pages for claim in page["claims"] if claim["mapped"])
    claims_hit = sum(1 for page in pages for claim in page["claims"] if claim["hit"])
    claims_derived = sum(1 for page in pages for claim in page["claims"] if claim.get("derived"))
    check_claims = [entry for page in pages for entry in page.get("check_claim", [])]
    check_hit = sum(1 for entry in check_claims if entry.get("hit"))
    ratio = round(markers_mapped / markers_total, 4) if markers_total else 0.0

    summary = {
        "pages_requested": len(PAGES),
        "pages_ok": len(pages),
        "pages_from_cache": sum(1 for page in pages if page.get("source") == "cache"),
        "reference_count": sum(page["reference_count"] for page in pages),
        "markers_total": markers_total,
        "markers_mapped": markers_mapped,
        "mapped_ratio": ratio,
        "target_ratio": TARGET_RATIO,
        "target_met": bool(pages) and ratio >= TARGET_RATIO,
        "reference_sentences": sum(page["reference_sentences"] for page in pages),
        "mapped_sources": sum(page["mapped_sources"] for page in pages),
        "claims_total": claims_total,
        "claims_marker_mapped": claims_located,
        "claims_source_located": claims_hit,
        "claims_derived": claims_derived,
        "check_claim_calls": len(check_claims),
        "check_claim_hits": check_hit,
        "check_claim_errors": sum(1 for entry in check_claims if not entry.get("ok")),
    }
    payload = {
        "generated_at": generated_at,
        "spike": "t27-live-page-citation-locating",
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
            "claim 定位 = 该引用句的 [n] 或 (Author, year) 所指页面文献是否与 gold DOI（或标题）一致；不做真伪判定。",
            "derived=true 的句子来自页面正文，gold 就是页面文献条目本身；它验证“能不能定位”，不是独立评测。",
            "PMC 的作者年引用在没有唯一 (first author, year, suffix) 条目时保持 unmapped，不猜测。",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"summary: pages={summary['pages_ok']}/{summary['pages_requested']} "
        f"refs={summary['reference_count']} markers={markers_total} mapped={markers_mapped} "
        f"ratio={ratio:.3f} target_met={summary['target_met']} "
        f"ref_sentences={summary['reference_sentences']} claims={claims_total} "
        f"located={claims_hit}"
    )
    print(f"wrote {out_path}")
    return 0 if pages else 1


if __name__ == "__main__":
    raise SystemExit(main())
