"""Analysis pipeline shared by the CLI and the web app."""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .gbt7714 import check_reference_list
from .jobs import manager
from .metadata_verify import verify_many
from .pdf_extract import extract_text, split_references
from .reference_parser import parse_intext_citations, parse_reference_list
from .report import build_report, save_report
from .support import build_claims, judge_support


def run_job(job_id: str, *, file_path: str | None = None, text: str | None = None) -> dict:
    """Run the full analysis and write report.json/html/md under data/jobs/<id>/."""
    if file_path:
        manager.update(job_id, progress=4, stage="读取文件")
        text = extract_text(file_path)
    if not text or not text.strip():
        raise ValueError("没有读到文本内容（PDF 可能是扫描件）")

    manager.update(job_id, progress=8, stage="切分正文与参考文献")
    body, refs_text = split_references(text)
    if not refs_text:
        # The paste box may contain only a reference list.
        refs_text = text
        body = ""

    refs = parse_reference_list(refs_text)
    if not refs:
        raise ValueError("没有解析到参考文献，请检查格式或改用 --refs 方式")
    manager.update(job_id, progress=12, stage=f"解析到 {len(refs)} 条引文")

    intext = parse_intext_citations(body)

    def progress_cb(i: int, n: int) -> None:
        manager.update(job_id, progress=15 + int(70 * i / max(n, 1)), stage=f"多源核验 {i}/{n}")

    verify_results = verify_many(refs, progress_cb=progress_cb)

    manager.update(job_id, progress=88, stage="检查 GB/T 7714-2025 字段")
    compliance = check_reference_list(refs)

    # Claim-level support: only for references that are cited in the body and
    # have an abstract; capped to keep API cost/time bounded.
    claims = build_claims(body, intext, refs)
    support_results: list[dict | None] = []
    checked = 0
    for i, (ref, ver) in enumerate(zip(refs, verify_results)):
        claim_text = claims.get(ref.index)
        abstract = (ver.best.abstract if ver and ver.best else "") or ""
        best_title = ver.best.title if ver and ver.best else ""
        if claim_text and abstract and checked < config.SUPPORT_MAX_REFS:
            res = judge_support(claim_text, abstract, best_title, ref.doi)
            checked += 1
            if res is not None:
                res["claim"] = claim_text
        else:
            res = None
        support_results.append(res)
        manager.update(
            job_id,
            progress=90 + int(6 * (i + 1) / len(refs)),
            stage=f"支持度判定 {i + 1}/{len(refs)}",
        )

    source_name = Path(file_path).name if file_path else "粘贴文本"
    report = build_report(source_name, body, refs, verify_results, compliance, intext, support_results)
    report["job_id"] = job_id

    out_dir = config.DATA_DIR / "jobs" / job_id
    save_report(report, out_dir, stem="report")
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    manager.update(job_id, progress=98, stage="生成报告")

    # Privacy: do not keep the uploaded paper after extraction.
    if file_path:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
    return report
