"""Analysis pipeline shared by the CLI and the web app.

``analyze_text`` is the pure part: text in, report dict out. ``run_job`` adds
job progress reporting and persistence for the web app. Keeping the logic in one
place means the CLI and the web UI cannot drift apart.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from . import config
from .gbt7714 import check_reference_list, citation_consistency
from .jobs import manager
from .metadata_verify import VerifyResult, local_library_verdict, verify_many
from .pdf_extract import extract_text_with_meta, split_references
from .reference_parser import parse_intext_citations, parse_reference_list
from .report import build_report, save_report
from .support import build_claims, judge_available, judge_support

Progress = Optional[Callable[[int, str], None]]


def _normalized_cap(support_max: int | None) -> int:
    cap = config.SUPPORT_MAX_REFS if support_max is None else support_max
    return max(0, min(int(cap), config.SUPPORT_MAX_REFS_LIMIT))


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
) -> dict:
    """Run the whole analysis on already-extracted text and return the report."""
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
    if not refs:
        raise ValueError("没有解析到参考文献，请检查格式或改用 --refs 方式")
    if max_refs and max_refs > 0:
        refs = refs[:max_refs]
    step(12, f"解析到 {len(refs)} 条引文")

    intext = parse_intext_citations(body)

    if online:
        def verify_progress(i: int, n: int) -> None:
            step(15 + int(70 * i / max(n, 1)), f"多源核验 {i}/{n}")

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
    report["input_meta"] = input_meta or {
        "method": "text",
        "file_type": "txt",
        "pages": 0,
        "ocr": False,
        "chars": len(text or ""),
        "warnings": [],
    }
    return report


def _judge_support(
    body: str,
    intext: list,
    refs: list,
    verify_results: list,
    cap: int,
    step: Callable[[int, str], None],
) -> tuple[list[dict | None], dict]:
    """Attach a support verdict (or a reason why there is none) to each ref."""
    has_judge = judge_available()
    claims = build_claims(body, intext, refs)
    results: list[dict | None] = []
    judged = 0
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
            res: dict | None = {
                "label": "not_checked",
                "confidence": 0.0,
                "reason": "正文未引用该文献，未做支持度判定",
                "evidence": "",
            }
        elif not trusted:
            # The abstract may belong to a different paper: at similarity 0.4
            # a Crossref record is often unrelated. Judging on it would make
            # "no evidence" look like a property of the cited paper.
            skipped_unreliable_match += 1
            res = {
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
            res = {
                "label": "not_checked",
                "confidence": 0.0,
                "reason": "未获取到被引论文摘要，无法判断",
                "evidence": "",
                "claim": claim_text,
            }
        else:
            candidates += 1
            if judged >= cap:
                skipped_by_cap += 1
                res = {
                    "label": "not_checked",
                    "confidence": 0.0,
                    "reason": "未启用支持度判定（本次上限为 0）"
                    if cap == 0
                    else f"超出本次判定上限（{cap} 条），可提高上限后重跑",
                    "evidence": "",
                    "claim": claim_text,
                }
            elif not has_judge:
                res = {
                    "label": "not_checked",
                    "confidence": 0.0,
                    "reason": "未配置 LLM judge（DEEPSEEK_API_KEY 未设置）",
                    "evidence": "",
                    "claim": claim_text,
                }
            else:
                res = judge_support(claim_text, abstract, best_title, ref.doi)
                judged += 1
                if res is None:
                    res = {
                        "label": "not_checked",
                        "confidence": 0.0,
                        "reason": "LLM judge 调用失败，本条未判定",
                        "evidence": "",
                        "claim": claim_text,
                    }
                else:
                    res["claim"] = claim_text
        results.append(res)
        step(
            90 + int(6 * (i + 1) / max(len(refs), 1)),
            f"支持度判定 {min(judged, cap)}/{min(candidates, cap)}",
        )

    meta = {
        "judge_available": has_judge,
        "cap": cap,
        "candidates": candidates,
        "judged": judged,
        "skipped_by_cap": skipped_by_cap,
        "skipped_no_abstract": skipped_no_abstract,
        "skipped_no_claim": skipped_no_claim,
        "skipped_unreliable_match": skipped_unreliable_match,
    }
    return results, meta


def run_job(
    job_id: str,
    *,
    file_path: str | None = None,
    text: str | None = None,
    support_max: int | None = None,
    library=None,
) -> dict:
    """Run the analysis for a web job and write report.json/html/md to disk."""
    if file_path:
        manager.update(job_id, progress=4, stage="读取文件")
        text, input_meta = extract_text_with_meta(file_path)
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

    def progress(pct: int, stage: str) -> None:
        manager.update(job_id, progress=pct, stage=stage)

    source_name = Path(file_path).name if file_path else "粘贴文本"
    report = analyze_text(
        text or "",
        source_name,
        support_max=support_max,
        progress=progress,
        library=library,
        input_meta=input_meta,
    )
    report["job_id"] = job_id

    out_dir = config.DATA_DIR / "jobs" / job_id
    save_report(report, out_dir, stem="report")
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manager.update(job_id, progress=98, stage="生成报告")

    # Privacy: do not keep the uploaded paper after extraction.
    if file_path:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
    return report
