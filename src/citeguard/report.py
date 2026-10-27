"""Report builders: JSON / Markdown / HTML."""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .format_gbt import format_from_candidate, format_reference_list
from .gbt7714 import ComplianceResult
from .metadata_verify import VerifyResult
from .reference_parser import InTextCitation, Reference

STATUS_LABEL = {
    "Exact": "真实且元数据一致",
    "Minor": "存在元数据偏差",
    "Major": "疑似虚构或错配",
    "Unverified": "未找到匹配记录",
    "Unknown": "无法核验（网络/数据源问题）",
}

STATUS_COLOR = {
    "Exact": "#1f9d55",
    "Minor": "#d97706",
    "Major": "#dc2626",
    "Unverified": "#8a6d3b",
    "Unknown": "#6b7280",
}


def _stats(verify: list[VerifyResult]) -> dict:
    counts = {"Exact": 0, "Minor": 0, "Major": 0, "Unverified": 0, "Unknown": 0}
    for v in verify:
        # ``--no-verify`` (CLI) passes None entries; treat those as Unknown
        # instead of raising, so an offline report still renders.
        status = getattr(v, "status", None) or "Unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _review_summary(
    items: list[dict],
    counts: dict,
    support_counts: Optional[dict],
    consistency: dict,
    total: int,
) -> dict:
    """Reviewer-style verdict: aggregate every check into one decision.

    This is deliberately conservative about language: it says 「建议核对/修改」
    rather than asserting misconduct, because the checks are automated and
    can be wrong (unindexed Chinese papers, parse noise).
    """
    issues: list[dict] = []
    for it in items:
        idx = it.get("index")
        v = it.get("verify") or {}
        p = it.get("parsed") or {}
        title = (p.get("title") or it.get("raw") or "")[:48]
        if v.get("status") == "Major":
            issues.append(
                {"index": idx, "severity": "blocker", "kind": "可能虚构/错配",
                 "text": f"{title}：DOI 或题名与数据库记录严重不符，请核对原始出处"}
            )
        if v.get("retracted"):
            issues.append(
                {"index": idx, "severity": "blocker", "kind": "已撤稿",
                 "text": f"{title}：OpenAlex 标记为撤稿，引用前必须核对撤稿声明"}
            )
        sup = it.get("support") or {}
        if sup.get("label") == "contradict":
            issues.append(
                {"index": idx, "severity": "blocker", "kind": "引用矛盾",
                 "text": f"{title}：正文引用句与被引原文结论矛盾"}
            )
        elif sup.get("label") == "partial":
            issues.append(
                {"index": idx, "severity": "minor", "kind": "部分支持",
                 "text": f"{title}：原文只部分支持正文表述，注意是否夸大"}
            )
        c = it.get("compliance") or {}
        if c.get("errors"):
            issues.append(
                {"index": idx, "severity": "minor", "kind": "格式错误",
                 "text": f"{title}：GB/T 7714 规则发现 {c['errors']} 处错误级问题"}
            )
    cc = consistency or {}
    if cc.get("numeric_style"):
        for n in (cc.get("uncited_numbers") or [])[:10]:
            issues.append(
                {"index": n, "severity": "minor", "kind": "未被引用",
                 "text": f"[{n}] 列于参考文献表但正文未引用"}
            )
        for n in (cc.get("missing_numbers") or [])[:10]:
            issues.append(
                {"index": n, "severity": "minor", "kind": "编号缺失",
                 "text": f"正文引注 [{n}] 在参考文献表中不存在"}
            )
        if cc.get("order_inversions"):
            issues.append(
                {"index": None, "severity": "minor", "kind": "顺序不一致",
                 "text": f"正文首次引用顺序与编号有 {cc['order_inversions']} 处不一致"}
            )

    blockers = sum(1 for x in issues if x["severity"] == "blocker")
    minors = sum(1 for x in issues if x["severity"] == "minor")
    support = support_counts or {}
    judged = sum(v for k, v in support.items() if k != "not_checked")
    if blockers:
        level = "blocker"
        decision = "建议修改后再投稿：存在可能虚构/错配、引用矛盾或已撤稿文献"
    elif minors:
        level = "minor"
        decision = "建议小修后再投稿：存在元数据偏差、格式或引注规范问题"
    elif counts.get("Unverified"):
        level = "ok"
        decision = "可送审，但建议先人工核对未找到匹配的条目（不等于造假）"
    else:
        level = "ok"
        decision = "可送审：本轮自动检查未发现阻断性问题"

    return {
        "decision": decision,
        "level": level,
        "blockers": blockers,
        "minor_issues": minors,
        "issues": issues[:30],
        "issue_total": len(issues),
        "support_judged": judged,
        "support_contradict": support.get("contradict", 0),
        "retracted": sum(1 for it in items if (it.get("verify") or {}).get("retracted")),
        "note": "审稿视角聚合为自动检查结果，不替代同行评审；未匹配条目请人工核对。",
    }


def build_report(
    input_path: str,
    body: str,
    refs: list[Reference],
    verify: list[VerifyResult],
    compliance: list[ComplianceResult],
    intext: list[InTextCitation],
    support_results: Optional[list[Optional[dict]]] = None,
    support_meta: Optional[dict] = None,
    citation_consistency: Optional[dict] = None,
) -> dict:
    counts = _stats(verify)
    total = len(refs)
    avg_compliance = round(sum(c.score for c in compliance) / total, 1) if total else 0.0
    risk = (
        round(
            100
            * (counts["Major"] + 0.5 * counts["Minor"] + 0.3 * counts["Unverified"])
            / total,
            1,
        )
        if total
        else 0.0
    )

    support_counts = None
    if support_results is not None:
        support_counts = {"support": 0, "partial": 0, "contradict": 0, "no_evidence": 0, "not_checked": 0}
        for r in support_results:
            if not r:
                support_counts["not_checked"] += 1
            else:
                label = r.get("label", "no_evidence")
                support_counts[label] = support_counts.get(label, 0) + 1

    items: list[dict] = []
    for i, (r, v, c) in enumerate(zip(refs, verify, compliance)):
        status = getattr(v, "status", None) if v else None
        # Only matched references get a metadata-derived entry; for an
        # unverified reference the "best" candidate is noise and must not be
        # presented as a corrected version of the user's citation.
        best = getattr(v, "best", None) if (v and status in {"Exact", "Minor", "Major"}) else None
        items.append(
            {
                "index": r.index,
                "raw": r.raw,
                "parsed": r.to_dict(),
                "verify": v.to_dict() if v else None,
                "compliance": c.to_dict() if c else None,
                "support": (support_results[i] if support_results and i < len(support_results) else None),
                # Ready-to-paste entry built from the database metadata (empty if
                # the reference could not be matched to any source record).
                "suggested_entry": format_from_candidate(r, best) if best else "",
            }
        )

    consistency = citation_consistency or {
        "numeric_style": False,
        "citations": len(intext),
        "distinct_numbers": 0,
        "missing_numbers": [],
        "uncited_numbers": [],
        "order_inversions": 0,
        "order_examples": [],
        "note": "未做正文引注一致性检查",
    }
    review = _review_summary(items, counts, support_counts, consistency, total)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(input_path),
        "stats": {
            "total": total,
            "intext_citations": len(intext),
            **counts,
            "avg_compliance": avg_compliance,
            "risk_index": risk,
            "support": support_counts,
            "support_meta": support_meta
            or {
                "judge_available": False,
                "cap": 0,
                "candidates": 0,
                "judged": 0,
                "skipped_by_cap": 0,
                "skipped_no_abstract": 0,
                "skipped_unreliable_match": 0,
            },
        },
        "citation_consistency": consistency,
        "review_summary": review,
        "references": items,
        # Re-typeset reference list built from what the paper already cites (no
        # online lookup). Useful as a first pass, but it cannot invent missing
        # fields: the UI/export labels it as "needs checking".
        "formatted_reference_list": format_reference_list(refs),
        "disclaimer": (
            "本报告为研究原型输出：元数据核验依据 OpenAlex/Crossref/arXiv 公开数据；"
            "GB/T 7714-2025 规则引擎基于公开规则事实编码，未复制标准原文，"
            "不构成对标准的权威解释；支持度判定由可选的 LLM judge 给出，仅供参考。"
            "请以国家标准原文与人工复核为准。"
        ),
    }


_INPUT_METHOD_LABEL = {
    "ocr": "OCR 识别（扫描件）",
    "pdf-text": "PDF 文字层",
    "docx": "Word 正文",
    "text": "文本",
}


def _input_meta_summary(meta: dict | None) -> str:
    """Human-readable 'where the text came from' line for exports."""
    if not meta:
        return ""
    parts = [_INPUT_METHOD_LABEL.get(meta.get("method"), meta.get("method") or "")]
    if meta.get("pages"):
        parts.append(f"{meta['pages']} 页")
    if meta.get("chars"):
        parts.append(f"{meta['chars']} 字符")
    summary = " · ".join(p for p in parts if p)
    warnings = [w for w in (meta.get("warnings") or []) if w]
    if warnings:
        summary += "；" + "；".join(warnings)
    return summary


def render_markdown(report: dict) -> str:
    s = report["stats"]
    lines = [
        "# 引证卫士 CiteGuard-CN · 引文体检报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 输入文件：`{report['input']}`",
    ]
    meta_line = _input_meta_summary(report.get("input_meta"))
    if meta_line:
        lines.append(f"- 文字来源：{meta_line}")
    lines += [
        f"- 参考文献：**{s['total']}** 条｜正文引注：**{s['intext_citations']}** 处",
        f"- 核验结果：真实一致 **{s['Exact']}**｜元数据偏差 **{s['Minor']}**｜疑似虚构/错配 **{s['Major']}**｜无法核验 **{s['Unknown']}**",
        f"- 新国标合规均分：**{s['avg_compliance']}/100**｜风险指数：**{s['risk_index']}**",
        f"- 结论：{_markdown_verdict(s)}",
    ]
    cfg = report.get("run_config") or {}
    if cfg:
        lines.append(
            "- 运行配置：引擎 {engine}｜离线 {off}｜在线核验 {online}｜支持度审计 {audit}（prompt {prompt}）｜万方 {wanfang}".format(
                engine=cfg.get("engine", "citeguard"),
                off="是" if cfg.get("offline") else "否",
                online="开" if cfg.get("online_verify") else "关",
                audit="开" if cfg.get("support_audit") else "关",
                prompt=cfg.get("support_prompt", "?"),
                wanfang="开" if cfg.get("wanfang") else "关",
            )
        )
    lines += [
        "",
    ]
    review = report.get("review_summary") or {}
    if review.get("decision"):
        lines += ["## 审稿视角（自动汇总，仅供参考）", "", f"- **{review['decision']}**"]
        for x in (review.get("issues") or [])[:10]:
            prefix = f"[{x.get('index')}] " if x.get("index") is not None else ""
            lines.append(f"- {prefix}{x.get('kind', '')}：{x.get('text', '')}")
        lines += [f"- {review.get('note', '')}", ""]
    consistency = report.get("citation_consistency") or {}
    lines += ["## 正文引注一致性", ""]
    if not consistency.get("numeric_style"):
        lines.append(f"- {consistency.get('note') or '未检测到数字型正文引注，跳过一致性检查'}")
    else:
        lines.append(
            f"- 正文数字引注 {consistency.get('citations', 0)} 处，覆盖 "
            f"{consistency.get('distinct_numbers', 0)} 个编号"
        )
        uncited = consistency.get("uncited_numbers") or []
        missing = consistency.get("missing_numbers") or []
        if uncited:
            shown = "、".join(str(n) for n in uncited[:20])
            more = f" 等 {len(uncited)} 条" if len(uncited) > 20 else ""
            lines.append(f"- 参考文献表中未被正文引用：{shown}{more}")
        if missing:
            lines.append("- 正文引注编号在文献表中不存在：" + "、".join(str(n) for n in missing))
        if consistency.get("order_inversions"):
            lines.append(
                f"- 首次引用顺序与编号不一致：{consistency['order_inversions']} 处"
                "（顺序编码制应按正文首次引用顺序编号）"
            )
        if not uncited and not missing and not consistency.get("order_inversions"):
            lines.append("- 未发现正文引注与参考文献表不一致")
    lines += [
        "| # | 状态 | 支持度 | 题名 | 年 | 来源 | 证据 | 合规分 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in report["references"]:
        p = item["parsed"]
        v = item["verify"] or {}
        c = item["compliance"] or {}
        status = v.get("status", "Unknown")
        best = v.get("best") or {}
        evidence = best.get("url") or best.get("doi") or ""
        title = (p.get("title") or "")[:42]
        sup = item.get("support") or {}
        sup_label = {
            "support": "支持",
            "partial": "部分支持",
            "contradict": "矛盾",
            "no_evidence": "无证据",
            "not_checked": "未检测",
        }.get(sup.get("label"), "—")
        lines.append(
            f"| {item.get('index', '')} | {STATUS_LABEL.get(status, status)} | {sup_label} | {title} | "
            f"{p.get('year', '')} | {p.get('venue', '')[:18]} | {evidence} | {c.get('score', '')} |"
        )
    suggested = [
        (item.get("index"), item.get("suggested_entry"))
        for item in report["references"]
        if item.get("suggested_entry")
    ]
    if suggested:
        lines += ["", "## 建议替换条目（按数据库元数据生成，请核对）", ""]
        for index, entry in suggested:
            lines.append(f"- [{index}] {entry}")
    formatted = report.get("formatted_reference_list") or []
    if formatted:
        lines += ["", "## GB/T 7714-2025 参考文献表（按原文重排，未核验字段需自行补齐）", ""]
        for item in formatted:
            if item.get("entry"):
                lines.append(f"[{item.get('index', '')}] {item['entry']}")
    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def _markdown_verdict(stats: dict) -> str:
    """One-line conclusion for the markdown export."""
    support = stats.get("support") or {}
    parts: list[str] = []
    if stats.get("Major"):
        parts.append(f"{stats['Major']} 条疑似虚构或错配，优先核对")
    if support.get("contradict"):
        parts.append(f"{support['contradict']} 条引用与被引原文矛盾，正文论点可能站不住")
    if stats.get("Minor"):
        parts.append(f"{stats['Minor']} 条元数据与数据库不一致")
    if support.get("partial"):
        parts.append(f"{support['partial']} 条引用仅被部分支持")
    if stats.get("Unverified"):
        parts.append(f"{stats['Unverified']} 条未找到匹配（不等于造假，建议人工核对）")
    if stats.get("Unknown"):
        parts.append(f"{stats['Unknown']} 条本次无法核验")
    return "；".join(parts) if parts else "未发现疑似虚构、元数据偏差或格式错误（建议仍抽查 1–2 条）"


def render_html(report: dict) -> str:
    s = report["stats"]
    support = s.get("support") or {}
    verdict_items: list[str] = []
    if s.get("Major"):
        verdict_items.append(f"<b>{s['Major']}</b> 条疑似虚构或错配，请优先核对")
    if support.get("contradict"):
        verdict_items.append(
            f"<b>{support['contradict']}</b> 条引用与被引原文矛盾（正文论点可能站不住），请优先核对"
        )
    if s.get("Minor"):
        verdict_items.append(f"<b>{s['Minor']}</b> 条元数据与数据库不一致（年份/卷期/页/作者）")
    if support.get("partial"):
        verdict_items.append(f"<b>{support['partial']}</b> 条引用仅被原文部分支持，建议核对表述是否夸大")
    if s.get("Unverified"):
        verdict_items.append(
            f"<b>{s['Unverified']}</b> 条在公开数据库未找到匹配（不等于造假；可导入本地题录库或人工核对）"
        )
    if not verdict_items:
        verdict_items.append("未发现疑似虚构、元数据偏差或格式错误；建议仍人工抽查 1–2 条。")
    verdict_html = (
        '<div class="verdict"><div class="verdict-head">体检结论</div><ul>'
        + "".join(f"<li>{item}</li>" for item in verdict_items)
        + "</ul></div>"
    )
    consistency = report.get("citation_consistency") or {}
    consistency_html = ""
    if consistency.get("numeric_style"):
        items: list[str] = []
        uncited = consistency.get("uncited_numbers") or []
        missing = consistency.get("missing_numbers") or []
        if uncited:
            shown = "、".join(str(n) for n in uncited[:20])
            more = f" 等 {len(uncited)} 条" if len(uncited) > 20 else ""
            items.append(f"参考文献表中未被正文引用：{shown}{more}")
        if missing:
            items.append("正文引注编号在文献表中不存在：" + "、".join(str(n) for n in missing))
        if consistency.get("order_inversions"):
            items.append(
                f"首次引用顺序与编号不一致：{consistency['order_inversions']} 处"
                "（顺序编码制应按正文首次引用顺序编号）"
            )
        if not items:
            items.append("正文引注与参考文献表一致")
        color = "#d97706" if (uncited or missing or consistency.get("order_inversions")) else "#1f9d55"
        consistency_html = (
            f'<div class="verdict" style="border-left-color:{color}">'
            '<div class="verdict-head">正文引注一致性</div><ul>'
            + "".join(f"<li>{html.escape(item)}</li>" for item in items)
            + "</ul></div>"
        )
    elif consistency.get("note"):
        consistency_html = (
            '<div class="verdict" style="border-left-color:#6b7280">'
            '<div class="verdict-head">正文引注一致性</div><ul>'
            f"<li>{html.escape(consistency['note'])}</li></ul></div>"
        )
    review = report.get("review_summary") or {}
    review_html = ""
    if review.get("decision"):
        r_color = {"blocker": "#dc2626", "minor": "#d97706", "ok": "#1f9d55"}.get(
            review.get("level"), "#6b7280"
        )
        r_items = "".join(
            "<li>"
            + (f"[{html.escape(str(x.get('index')))}] " if x.get("index") is not None else "")
            + f"<b>{html.escape(x.get('kind', ''))}</b>：{html.escape(x.get('text', ''))}"
            + "</li>"
            for x in (review.get("issues") or [])[:10]
        )
        review_html = (
            f'<div class="verdict" style="border-left-color:{r_color}">'
            '<div class="verdict-head">审稿视角 · 自动汇总（仅供参考）</div>'
            f'<div style="font-size:14px;font-weight:600;margin-bottom:6px;color:{r_color}">'
            f"{html.escape(review['decision'])}</div>"
            f'<div style="font-size:12px;color:#6b7280;margin-bottom:6px">阻断级问题 '
            f"{review.get('blockers', 0)} 项 · 提示级问题 {review.get('minor_issues', 0)} 项"
            + (f" · 撤稿标记 {review.get('retracted')} 条" if review.get("retracted") else "")
            + "</div>"
            + (f"<ul>{r_items}</ul>" if r_items else "")
            + f'<div style="font-size:12px;color:#6b7280;margin-top:6px">{html.escape(review.get("note", ""))}</div>'
            "</div>"
        )
    cards: list[str] = []
    for item in report["references"]:
        p = item["parsed"]
        v = item["verify"] or {}
        c = item["compliance"] or {}
        status = v.get("status", "Unknown")
        color = STATUS_COLOR.get(status, "#6b7280")
        best = v.get("best") or {}
        evidence = best.get("url") or (f"https://doi.org/{best.get('doi')}" if best.get("doi") else "")
        issues = c.get("issues") or []
        issue_html = "".join(
            f'<li class="issue {html.escape(i["level"])}">[{html.escape(i["level"])}] '
            f'{html.escape(i["message"])}'
            + (f'<span class="sugg">建议：{html.escape(i["suggestion"])}</span>' if i.get("suggestion") else "")
            + "</li>"
            for i in issues
        )
        authors = ", ".join(p.get("authors") or []) or "（未解析）"
        sup = item.get("support") or {}
        sup_label = {
            "support": "支持",
            "partial": "部分支持",
            "contradict": "矛盾",
            "no_evidence": "无证据",
            "not_checked": "未检测",
        }.get(sup.get("label"), "")
        sup_color = {
            "support": "#1f9d55",
            "partial": "#d97706",
            "contradict": "#dc2626",
            "no_evidence": "#6b7280",
            "not_checked": "#9ca3af",
        }.get(sup.get("label"), "#6b7280")
        support_html = ""
        if sup_label:
            support_html = (
                '<div style="margin-top:8px;font-size:12px;color:#374151">'
                f'<span class="badge" style="background:{sup_color}">支持度：{sup_label}</span>'
                f'<div style="margin-top:4px">引用句：{html.escape(sup.get("claim", ""))}</div>'
                f'<div>理由：{html.escape(sup.get("reason", ""))}</div>'
                + (f'<div>证据：{html.escape(sup.get("evidence", ""))}</div>' if sup.get("evidence") else "")
                + "</div>"
            )
        cards.append(
            f"""
            <div class="card" style="border-left-color:{color}">
              <div class="card-head">
                <span class="idx">[{item.get('index', '')}]</span>
                <span class="badge" style="background:{color}">{STATUS_LABEL.get(status, status)}</span>
                <span class="score">合规 {c.get('score', '—')}/100</span>
              </div>
              <div class="title">{html.escape(p.get('title') or item['raw'][:120])}</div>
              <div class="meta">{html.escape(authors)} · {p.get('year', '')} · {html.escape(p.get('venue', ''))}</div>
              <div class="raw">{html.escape(item['raw'])}</div>
              <div class="evidence">
                核验：title_sim={v.get('title_sim', 0):.2f} · year_match={v.get('year_match')} · author_match={v.get('author_match', 0):.2f}
                {f' · <a href="{html.escape(evidence)}" target="_blank">查看证据</a>' if evidence else ''}
              </div>
              {support_html}
              {f'<ul class="issues">{issue_html}</ul>' if issue_html else '<div class="ok">本规则集未发现字段/标点问题（不覆盖排版与语义错误）</div>'}
              {f'<div class="suggested"><span>按数据库元数据生成的规范条目（核对后替换）</span><code>{html.escape(item["suggested_entry"])}</code></div>' if item.get("suggested_entry") else ''}
            </div>
            """
        )

    formatted = report.get("formatted_reference_list") or []
    formatted_html = ""
    if formatted:
        lis = "".join(
            f'<li><span class="idx">[{html.escape(str(it.get("index", "")))}]</span> '
            f'{html.escape(it.get("entry", ""))}</li>'
            for it in formatted
            if it.get("entry")
        )
        if lis:
            formatted_html = (
                '<div class="card" style="margin-top:22px">'
                '<div class="title" style="font-size:15px">GB/T 7714-2025 参考文献表（按原文重排）</div>'
                '<div class="meta">只做格式重排，不补缺失字段；请与原文核对后再替换。</div>'
                f'<ol class="refs-list">{lis}</ol>'
                "</div>"
            )

    input_meta = report.get("input_meta") or {}
    input_summary = _input_meta_summary(input_meta)
    input_suffix = f" · 文字来源 {html.escape(input_summary)}" if input_summary else ""
    ocr_note = ""
    if input_meta.get("ocr"):
        ocr_note = (
            '<div class="verdict" style="border-left-color:#d97706">'
            '<div class="verdict-head">文字来源提示</div>'
            "<ul><li>本报告基于扫描件的 OCR 识别文字；识别错字会传递到引文解析与核验结论，"
            "请对照原文复核后再采用。</li></ul></div>"
        )

    cfg = report.get("run_config") or {}
    run_config_html = ""
    if cfg:
        run_config_html = (
            '<p class="sub">运行配置：离线 {off} · 在线核验 {online} · 支持度审计 {audit}'
            "（prompt {prompt}） · 万方 {wanfang}</p>"
        ).format(
            off="是" if cfg.get("offline") else "否",
            online="开" if cfg.get("online_verify") else "关",
            audit="开" if cfg.get("support_audit") else "关",
            prompt=html.escape(str(cfg.get("support_prompt", "?"))),
            wanfang="开" if cfg.get("wanfang") else "关",
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>引证卫士 CiteGuard-CN · 引文体检报告</title>
<style>
  :root {{ --bg:#f6f7f9; --card:#fff; --text:#111827; --muted:#6b7280; --line:#e5e7eb; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }}
  header {{ display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:20px; }}
  h1 {{ font-size:22px; margin:0; }}
  .sub {{ color:var(--muted); font-size:13px; margin-top:6px; }}
  .stats {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin:20px 0 28px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }}
  .stat b {{ display:block; font-size:24px; }}
  .verdict {{ background:#fff; border:1px solid var(--line); border-left:4px solid #A63D2F; border-radius:12px; padding:14px 18px; margin:0 0 20px; }}
  .verdict-head {{ font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:#A63D2F; margin-bottom:6px; }}
  .verdict ul {{ margin:0; padding-left:18px; font-size:13px; line-height:1.8; color:#374151; }}
  .stat span {{ color:var(--muted); font-size:12px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-left:4px solid #6b7280; border-radius:12px; padding:16px 18px; margin:14px 0; }}
  .card-head {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
  .idx {{ color:var(--muted); font-size:13px; }}
  .badge {{ color:#fff; font-size:12px; padding:2px 10px; border-radius:999px; }}
  .score {{ margin-left:auto; color:var(--muted); font-size:12px; }}
  .title {{ font-size:16px; font-weight:600; margin:4px 0 6px; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:8px; }}
  .raw {{ background:#f9fafb; border-radius:8px; padding:8px 10px; font-size:12px; color:#374151; word-break:break-all; }}
  .evidence {{ color:var(--muted); font-size:12px; margin-top:8px; }}
  .issues {{ margin:10px 0 0; padding-left:18px; font-size:13px; }}
  .issue.error {{ color:#b91c1c; }}
  .issue.warning {{ color:#b45309; }}
  .issue.info {{ color:#1d4ed8; }}
  .sugg {{ color:var(--muted); margin-left:6px; }}
  .ok {{ color:#15803d; font-size:13px; margin-top:8px; }}
  .suggested {{ margin-top:10px; border-top:1px dashed var(--line); padding-top:10px; font-size:12px; color:var(--muted); }}
  .suggested span {{ display:block; margin-bottom:4px; }}
  .suggested code {{ display:block; color:var(--text); background:#f9fafb; border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-family: "Microsoft YaHei", sans-serif; line-height:1.7; white-space:pre-wrap; }}
  .refs-list {{ margin:8px 0 0; padding-left:20px; font-size:12px; color:#374151; line-height:1.9; }}
  .refs-list li {{ margin-bottom:4px; }}
  footer {{ color:var(--muted); font-size:12px; margin-top:28px; line-height:1.7; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>引证卫士 CiteGuard-CN · 引文体检报告</h1>
      <div class="sub">生成时间 {html.escape(report['generated_at'])} · 输入 {html.escape(report['input'])}{input_suffix}</div>
    </div>
  </header>
  {run_config_html}
  {ocr_note}
  <div class="stats">
    <div class="stat"><b>{s['total']}</b><span>参考文献</span></div>
    <div class="stat"><b style="color:#1f9d55">{s['Exact']}</b><span>真实且一致</span></div>
    <div class="stat"><b style="color:#d97706">{s['Minor']}</b><span>元数据偏差</span></div>
    <div class="stat"><b style="color:#dc2626">{s['Major']}</b><span>疑似虚构/错配</span></div>
    <div class="stat"><b style="color:#6b7280">{s.get('Unverified', 0)}</b><span>未找到匹配</span></div>
    <div class="stat"><b>{s['avg_compliance']}</b><span>新国标合规均分</span></div>
  </div>
  {verdict_html}
  {review_html}
  {consistency_html}
  {''.join(cards)}
  {formatted_html}
  <footer>{html.escape(report['disclaimer'])}</footer>
</div>
</body>
</html>"""


def save_report(report: dict, out_dir: str | Path, stem: str = "report") -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    html_path = out_dir / f"{stem}.html"
    refs_path = out_dir / f"{stem}.refs.txt"
    ris_path = out_dir / f"{stem}.ris"
    enw_path = out_dir / f"{stem}.enw"
    bib_path = out_dir / f"{stem}.bib"
    csl_path = out_dir / f"{stem}.csl.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    refs_path.write_text(render_reference_list(report), encoding="utf-8")
    # RIS / EndNote bundles so the report can be dropped straight into
    # EndNote, NoteExpress or Zotero (common in Chinese university workflows).
    from citeguard.exporters import (
        refs_from_parsed,
        refs_to_bibtex,
        refs_to_csl,
        refs_to_enw,
        refs_to_ris,
    )

    parsed_refs = refs_from_parsed(report.get("references") or [])
    ris_path.write_text(refs_to_ris(parsed_refs), encoding="utf-8")
    enw_path.write_text(refs_to_enw(parsed_refs), encoding="utf-8")
    bib_path.write_text(refs_to_bibtex(parsed_refs), encoding="utf-8")
    csl_path.write_text(refs_to_csl(parsed_refs), encoding="utf-8")
    return {
        "json": str(json_path),
        "md": str(md_path),
        "html": str(html_path),
        "refs": str(refs_path),
        "ris": str(ris_path),
        "enw": str(enw_path),
        "bib": str(bib_path),
        "csl": str(csl_path),
    }


def render_reference_list(report: dict) -> str:
    """Plain-text GB/T-style reference list (one ``[n] entry`` per line)."""
    lines: list[str] = []
    for item in report.get("formatted_reference_list") or []:
        entry = (item.get("entry") or "").strip()
        if entry:
            lines.append(f"[{item.get('index', '')}] {entry}")
    return "\n".join(lines) + ("\n" if lines else "")
