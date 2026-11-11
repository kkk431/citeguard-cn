"""Analysis pipeline shared by the CLI and the web app.

``analyze_text`` is the pure part: text in, report dict out. ``run_job`` adds
job progress reporting and persistence for the web app. Keeping the logic in one
place means the CLI and the web UI cannot drift apart.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from . import config
from .gbt7714 import check_reference_list, citation_consistency
from .jobs import manager
from .metadata_verify import source_error_count, source_health, VerifyResult, local_library_verdict, verify_many
from .pdf_extract import extract_text_with_meta, split_references
from .reference_parser import parse_intext_citations, parse_reference_list
from .report import build_report, save_report
from .support import (
    PROMPT_VERSION,
    apply_grounding,
    build_claims,
    is_low_confidence,
    judge_available,
    judge_support,
)

Progress = Optional[Callable[[int, str], None]]


def _normalized_cap(support_max: int | None) -> int:
    cap = config.SUPPORT_MAX_REFS if support_max is None else support_max
    return max(0, min(int(cap), config.SUPPORT_MAX_REFS_LIMIT))


def _health_since(errors_at_start: int) -> dict:
    """Source health for THIS run: the global counter also carries failures from
    earlier jobs in the same server process, so report the delta."""
    health = source_health()
    health["errors"] = max(0, int(health.get("errors", 0)) - errors_at_start)
    return health


def _citations_payload(body: str, references=(), limit: int = 200) -> dict:
    """Report-level citation context: where each citation appears and what it cites."""
    from .citation_anchor import coverage, extract_citations, summarize

    is_list = isinstance(references, (list, tuple))
    ref_count = len(references) if is_list else int(references or 0)

    items = extract_citations(body)
    return {
        "summary": summarize(items),
        "coverage": coverage(items, references if is_list else ref_count),
        "items": [c.to_dict() for c in items[:limit]],
        "truncated": len(items) > limit,
    }


def _judge_run_config() -> dict:
    """Record which judge endpoint actually generated this report."""
    try:
        from .support import judge_endpoint

        base, model, _key = judge_endpoint()
        return {"base_url": base, "model": model}
    except Exception:
        return {"base_url": "", "model": ""}


def analyze_text(
    text: str,
    source_name: str = "粘贴文本",
    *,
    support_max: int | None = None,
    progress: Progress = None,
    online: bool = True,
    use_arxiv: bool = True,
    library=None,
    max_refs: int = 0,
    input_meta: dict | None = None,
    figure_checks: bool = False,
    pdf_path: str | None = None,
) -> dict:
    """Run the whole analysis on already-extracted text and return the report."""
    errors_at_start = source_error_count()

    def step(pct: int, stage: str) -> None:
        if progress:
            progress(pct, stage)

    if not text or not text.strip():
        raise ValueError("没有读到文本内容（PDF 可能是扫描件，或 Word 正文是图片）")

    step(8, "切分正文与参考文献")
    body, refs_text = split_references(text)
    if not refs_text:
        # The paste box may contain only a reference list.
        refs_text = text
        body = ""

    refs = parse_reference_list(refs_text)
    if pdf_path and len(refs) < 200:
        # Hanging-indent / two-column lists often collapse after text extraction.
        # Build a layout candidate and keep it only when its titles are healthier.
        try:
            from .refs_layout import extract_reference_entries, title_health

            layout_entries = extract_reference_entries(pdf_path)
        except Exception:
            layout_entries = []
        if len(layout_entries) >= 5:
            from .refs_layout import _URL_TITLE_RE, recover_title

            layout_refs = []
            for entry in layout_entries:
                parsed = parse_reference_list(entry)
                if len(parsed) == 1 and _URL_TITLE_RE.match(parsed[0].title or ""):
                    better = recover_title(entry)
                    if better:
                        parsed[0].title = better
                layout_refs.extend(parsed)
            if (len(layout_refs) >= len(refs) and
                    title_health(layout_refs) >= title_health(refs) + 0.02):
                refs = layout_refs
    # Entries parsed one-by-one (layout path) all carry index 1; renumber so
    # the report and exports show stable per-reference numbers.
    for i, ref in enumerate(refs, 1):
        ref.index = i
    if not refs:
        raise ValueError("没有解析到参考文献，请检查格式或改用 --refs 方式")
    if max_refs and max_refs > 0:
        refs = refs[:max_refs]
    step(12, f"解析到 {len(refs)} 条引文")

    intext = parse_intext_citations(body)

    if online:
        verify_started = time.monotonic()

        def verify_progress(i: int, n: int) -> None:
            step(15 + int(70 * i / max(n, 1)), _stage_with_eta("多源核验", i, n, verify_started))

        verify_results = verify_many(
            refs, progress_cb=verify_progress, use_arxiv=use_arxiv, library=library
        )
    else:
        # Offline mode still uses the user's library; everything else is Unknown.
        verify_results = [
            local_library_verdict(ref, library) or VerifyResult(status="Unknown") for ref in refs
        ]
        step(85, "已跳过在线核验（--no-verify）" if library is None else "已跳过在线核验，仅比对本地题录库")

    step(88, "检查 GB/T 7714-2025 字段")
    compliance = check_reference_list(refs)
    consistency = citation_consistency(refs, intext)

    support_results, support_meta = _judge_support(
        body,
        intext,
        refs,
        verify_results,
        _normalized_cap(support_max),
        step,
    )

    report = build_report(
        source_name,
        body,
        refs,
        verify_results,
        compliance,
        intext,
        support_results,
        support_meta,
        consistency,
    )
    # How much of this report came from the user's own library, and how big it is.
    local_hits = sum(
        1
        for v in verify_results
        if v is not None and "local" in getattr(v, "sources", [])
    )
    report["stats"]["library_entries"] = len(library) if library is not None else 0
    report["stats"]["library_hits"] = local_hits
    report["citations"] = _citations_payload(body, refs)
    from .report_charts import build_charts

    report["charts"] = build_charts(report)
    report["input_meta"] = input_meta or {
        "method": "text",
        "file_type": "txt",
        "pages": 0,
        "ocr": False,
        "chars": len(text or ""),
        "warnings": [],
    }
    # Record what produced this report. Without it, two runs that differ only
    # because a judge prompt or a source changed look identical on paper.
    report["run_config"] = {
        "engine": "citeguard",
        "offline": bool(config.OFFLINE),
        "online_verify": bool(online),
        "support_prompt": PROMPT_VERSION,
        "support_audit": bool(config.SUPPORT_AUDIT),
        "support_judge_available": bool(judge_available()),
        "judge": _judge_run_config(),
        "wanfang": bool(getattr(config, "WANFANG_APP_KEY", "")),
        "sources": ["local-library", "openalex", "crossref", "arxiv"]
        + (["semantic-scholar"] if getattr(config, "SEMANTIC_SCHOLAR", False) else []),
        "source_health": _health_since(errors_at_start),
    }
    if figure_checks and pdf_path and not config.OFFLINE:
        step(93, "抽检正文图表结论")
        try:
            report["figure_checks"] = _check_body_figures(body, pdf_path, step)
        except Exception as exc:  # never fail a good report because of the optional check
            report["figure_checks"] = [{"number": "", "error": str(exc)[:200]}]
    return report


_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])\s*|\n+")
# Caption lines such as "Figure 1. ..." / "图 1：..." are part of the extracted
# body but are not author claims. A sentence merely *starting* with "图 1 显示…"
# is a real claim, so only caption-shaped prefixes are skipped.
_CAPTION_LINE_RE = re.compile(
    r"^(?:(?:figure|fig\.|table)\s*\d+\s*[.:：]|(?:图|表)\s*\d+\s*[：:.])", re.IGNORECASE
)


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def _stage_with_eta(label: str, done: int, total: int, started: float) -> str:
    elapsed = time.monotonic() - started
    eta = elapsed / done * (total - done) if done else 0
    return f"{label} {done}/{total} · 已用 {_fmt_duration(elapsed)} · 剩约 {_fmt_duration(eta)}"


def _body_figure_claims(body: str, *, max_figures: int = 3, per_figure: int = 2):
    """Group body sentences that reference ``图 N`` / ``表 N`` by figure number.

    Only the first few distinct figures are kept: the visual judge costs seconds
    per call, and a paper that mentions forty figures should not silently turn a
    routine check into a ten-minute job.
    """
    from .pdf_extract import caption_kind_from_claim, figure_number_from_claim

    groups: dict[tuple[str, str], list[str]] = {}
    for sentence in _SENTENCE_SPLIT.split(body or ""):
        claim = sentence.strip()
        if not 5 <= len(claim) <= 500:
            continue
        # The extracted "body" still contains figure captions themselves
        # ("Figure 1. ..." / "图 1 ..."). Those are not author claims: asking
        # the model whether a caption matches its own figure just burns time.
        if _CAPTION_LINE_RE.match(claim):
            continue
        number = figure_number_from_claim(claim)
        if not number:
            continue
        key = (caption_kind_from_claim(claim) or "figure", number)
        if key not in groups:
            if len(groups) >= max_figures:
                continue
            groups[key] = []
        claims = groups[key]
        if len(claims) < per_figure and claim not in claims:
            claims.append(claim)
    return [(key, claims) for key, claims in groups.items() if claims]


def _check_body_figures(body: str, pdf_path: str, step: Callable[[int, str], None]) -> list[dict]:
    from .figure_advice import annotate_items
    from .figure_check import check_claims
    from .pdf_extract import extract_page_text, find_figure_page, render_page_png

    results: list[dict] = []
    for (kind, number), claims in _body_figure_claims(body):
        step(94, f"图表结论抽检：{'表' if kind == 'table' else '图'} {number}")
        found = find_figure_page(pdf_path, number, kind=kind, claim=claims[0])
        if not found:
            results.append(
                {"number": number, "page": None, "claims": claims, "error": "未在 PDF 前 40 页找到对应图注"}
            )
            continue
        page, caption = found
        try:
            png = render_page_png(pdf_path, page)
        except Exception as exc:
            results.append(
                {"number": number, "page": page, "claims": claims, "error": f"渲染页面失败：{exc}"}
            )
            continue
        try:
            context = extract_page_text(pdf_path, page)
        except Exception:
            context = ""
        batch = check_claims(png, "image/png", claims, context=(caption + "\n" + context).strip())
        results.append(
            {
                "kind": kind,
                "number": number,
                "page": page, 
                "caption": caption,
                "claims": claims,
                "items": annotate_items(batch.get("items") or []),
                "ok": bool(batch.get("ok")),
                "error": batch.get("error", ""),
            }
        )
    return results


def _judge_support(
    body: str,
    intext: list,
    refs: list,
    verify_results: list,
    cap: int,
    step: Callable[[int, str], None],
) -> tuple[list[dict | None], dict]:
    """Attach a support verdict (or a reason why there is none) to each ref.

    Eligible claims are judged by a small thread pool (config.SUPPORT_WORKERS):
    the judge is I/O bound, so this cuts wall-clock time on long lists without
    changing which references are judged (the first ``cap`` eligible ones, in
    list order) or the shape of the returned verdicts.
    """
    has_judge = judge_available()
    if config.OFFLINE:
        return [None] * len(refs), {
            "judge_available": False,
            "cap": 0,
            "candidates": 0,
            "judged": 0,
            "skipped_by_cap": 0,
            "skipped_no_abstract": 0,
            "skipped_unreliable_match": 0,
            "offline": True,
        }
    claims = build_claims(body, intext, refs)
    results: list[dict | None] = [None] * len(refs)
    pending: list[tuple[int, str, str, str, str]] = []
    candidates = 0
    skipped_by_cap = 0
    skipped_no_abstract = 0
    skipped_no_claim = 0
    skipped_unreliable_match = 0

    for i, (ref, ver) in enumerate(zip(refs, verify_results)):
        claim_text = claims.get(ref.index)
        abstract = (ver.best.abstract if ver and ver.best else "") or ""
        best_title = ver.best.title if ver and ver.best else ""
        sim = float(ver.title_sim or 0.0) if ver else 0.0
        trusted = bool(
            ver
            and (
                ver.status in {"Exact", "Minor"}
                or sim >= config.SUPPORT_MIN_TITLE_SIM
            )
        )
        if not claim_text:
            skipped_no_claim += 1
            results[i] = {
                "label": "not_checked",
                "confidence": 0.0,
                "reason": "正文未引用该文献，未做支持度判定",
                "evidence": "",
            }
        elif not trusted:
            skipped_unreliable_match += 1
            results[i] = {
                "label": "not_checked",
                "confidence": 0.0,
                "reason": (
                    f"题录匹配度不足（标题相似度 {sim:.2f}），"
                    "无法确认摘要属于同一篇论文，未做支持度判定"
                ),
                "evidence": "",
                "claim": claim_text,
            }
        elif not abstract:
            skipped_no_abstract += 1
            results[i] = {
                "label": "not_checked",
                "confidence": 0.0,
                "reason": "未获取到被引论文摘要，无法判断",
                "evidence": "",
                "claim": claim_text,
            }
        else:
            candidates += 1
            if candidates > cap:
                skipped_by_cap += 1
                results[i] = {
                    "label": "not_checked",
                    "confidence": 0.0,
                    "reason": "未启用支持度判定（本次上限为 0）"
                    if cap == 0
                    else f"超出本次判定上限（{cap} 条），可提高上限后重跑",
                    "evidence": "",
                    "claim": claim_text,
                }
            elif not has_judge:
                results[i] = {
                    "label": "not_checked",
                    "confidence": 0.0,
                    "reason": "未配置 LLM judge（DEEPSEEK_API_KEY 未设置）",
                    "evidence": "",
                    "claim": claim_text,
                }
            else:
                pending.append((i, claim_text, abstract, best_title, ref.doi))

    def _normalise(res: dict | None, claim_text: str) -> dict:
        if res is None:
            return {
                "label": "not_checked",
                "confidence": 0.0,
                "reason": "LLM judge 调用失败，本条未判定",
                "evidence": "",
                "claim": claim_text,
            }
        res["claim"] = claim_text
        try:
            from .claim_decompose import analyze_claim

            res["sub_claims"] = analyze_claim(claim_text)
        except Exception:
            pass
        return res

    judged = 0
    total = len(pending)
    workers = max(1, min(int(getattr(config, "SUPPORT_WORKERS", 1) or 1), total or 1))
    if total:
        support_started = time.monotonic()
        step(90, f"支持度判定 0/{total}")
        if workers == 1:
            for i, claim_text, abstract, best_title, doi in pending:
                res = judge_support(claim_text, abstract, best_title, doi)
                results[i] = apply_grounding(_normalise(res, claim_text), abstract)
                judged += 1
                step(90 + int(6 * judged / total), _stage_with_eta("支持度判定", judged, total, support_started))
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(judge_support, claim_text, abstract, best_title, doi): (
                        i,
                        claim_text,
                        abstract,
                    )
                    for i, claim_text, abstract, best_title, doi in pending
                }
                for fut in as_completed(futures):
                    i, claim_text, abstract = futures[fut]
                    try:
                        res = fut.result()
                    except Exception:
                        res = None
                    results[i] = apply_grounding(_normalise(res, claim_text), abstract)
                    judged += 1
                    step(90 + int(6 * judged / total), _stage_with_eta("支持度判定", judged, total, support_started))

    if any(r is None for r in results):
        for i, r in enumerate(results):
            if r is None:
                results[i] = {
                    "label": "not_checked",
                    "confidence": 0.0,
                    "reason": "支持度判定未完成",
                    "evidence": "",
                }

    low_confidence = 0
    for r in results:
        if is_low_confidence(r):
            conf = r.get("confidence")
            r["low_confidence"] = True
            r["review_hint"] = (
                f"置信度 {float(conf):.2f} 低于阈值 {config.SUPPORT_ABSTAIN:.2f}，建议人工复核"
            )
            low_confidence += 1
    meta = {
        "judge_available": has_judge,
        "low_confidence": low_confidence,
        "abstain_threshold": config.SUPPORT_ABSTAIN,
        "cap": cap,
        "candidates": candidates,
        "judged": judged,
        "workers": workers,
        "skipped_by_cap": skipped_by_cap,
        "skipped_no_abstract": skipped_no_abstract,
        "skipped_no_claim": skipped_no_claim,
        "skipped_unreliable_match": skipped_unreliable_match,
    }
    return results, meta


def _extract_cached(file_path: str, on_page=None) -> tuple[str, dict]:
    """Extract text, reusing a content-hash cache for repeat runs."""
    from . import text_cache

    if text_cache.cache_enabled():
        hit = text_cache.load_text(file_path)
        if hit:
            text, meta = hit
            return text, {**meta, "cache": "hit"}
    text, meta = extract_text_with_meta(file_path, on_page=on_page)
    meta = {**meta, "cache": "miss"}
    if text_cache.cache_enabled():
        try:
            text_cache.save_text(file_path, text, {k: v for k, v in meta.items() if k != "cache"})
        except Exception:
            pass
    return text, meta


def run_job(
    job_id: str,
    *,
    file_path: str | None = None,
    text: str | None = None,
    support_max: int | None = None,
    library=None,
    figures: bool = False,
) -> dict:
    """Run the analysis for a web job and write report.json/html/md to disk."""
    if file_path:
        manager.update(job_id, progress=4, stage="读取文件")

        def _page(done: int, total: int) -> None:
            pct = 4 + int(6 * done / max(total, 1))
            manager.update(job_id, progress=pct, stage=f"抽取文字 {done}/{total} 页")

        text, input_meta = _extract_cached(file_path, on_page=_page)
        manager.update(
            job_id,
            progress=10,
            stage=f"抽取完成：{input_meta.get('pages', 0)} 页 / {input_meta.get('chars', 0)} 字",
        )
    else:
        input_meta = {
            "method": "text",
            "file_type": "txt",
            "pages": 0,
            "ocr": False,
            "chars": len(text or ""),
            "warnings": [],
        }

    if library is None:
        from .local_library import Library

        library = Library.load(config.LIBRARY_FILE)

    source_name = Path(file_path).name if file_path else "粘贴文本"
    out_dir = config.DATA_DIR / "jobs" / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # Keep the extracted text only until the job succeeds: it makes a crashed or
    # interrupted run retryable without asking the user to upload again, and is
    # deleted together with options.json as soon as a report exists.
    try:
        (out_dir / "input.txt").write_text(text or "", encoding="utf-8")
        (out_dir / "options.json").write_text(
            json.dumps(
                {"support_max": support_max, "source_name": source_name, "figures": bool(figures)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    def progress(pct: int, stage: str) -> None:
        manager.update(job_id, progress=pct, stage=stage)

    report = analyze_text(
        text or "",
        source_name,
        support_max=support_max,
        progress=progress,
        library=library,
        input_meta=input_meta,
        figure_checks=figures,
        pdf_path=file_path,
    )
    report["job_id"] = job_id

    # Build the annotated PDF while the uploaded file is still on disk: the
    # copy is deleted right after this function returns (privacy).
    if file_path and Path(file_path).suffix.lower() == ".pdf":
        try:
            from .annotate import annotate_pdf

            stats = annotate_pdf(file_path, report, out_dir / "report.annotated.pdf")
            report["annotated"] = {k: stats[k] for k in ("annotated", "unmapped", "pages")}
        except Exception:
            pass

    save_report(report, out_dir, stem="report")
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manager.update(job_id, progress=98, stage="生成报告")

    # Privacy: do not keep the uploaded paper after extraction, and drop the
    # retry copy as soon as a complete report exists.
    if file_path:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
    for name in ("input.txt", "options.json"):
        try:
            (out_dir / name).unlink(missing_ok=True)
        except Exception:
            pass
    return report
