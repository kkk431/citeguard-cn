"""Report builders: JSON / Markdown / HTML."""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .format_gbt import format_from_candidate
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


def build_report(
    input_path: str,
    body: str,
    refs: list[Reference],
    verify: list[VerifyResult],
    compliance: list[ComplianceResult],
    intext: list[InTextCitation],
    support_results: Optional[list[Optional[dict]]] = None,
    support_meta: Optional[dict] = None,
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
            },
        },
        "references": items,
        "disclaimer": (
            "本报告为研究原型输出：元数据核验依据 OpenAlex/Crossref/arXiv 公开数据；"
            "GB/T 7714-2025 规则引擎基于公开规则事实编码，未复制标准原文，"
            "不构成对标准的权威解释；支持度判定由可选的 LLM judge 给出，仅供参考。"
            "请以国家标准原文与人工复核为准。"
        ),
    }


def render_markdown(report: dict) -> str:
    s = report["stats"]
    lines = [
        "# 引证卫士 CiteGuard-CN · 引文体检报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 输入文件：`{report['input']}`",
        f"- 参考文献：**{s['total']}** 条｜正文引注：**{s['intext_citations']}** 处",
        f"- 核验结果：真实一致 **{s['Exact']}**｜元数据偏差 **{s['Minor']}**｜疑似虚构/错配 **{s['Major']}**｜无法核验 **{s['Unknown']}**",
        f"- 新国标合规均分：**{s['avg_compliance']}/100**｜风险指数：**{s['risk_index']}**",
        "",
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
    lines += ["", f"> {report['disclaimer']}"]
    return "\n".join(lines)


def render_html(report: dict) -> str:
    s = report["stats"]
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
  footer {{ color:var(--muted); font-size:12px; margin-top:28px; line-height:1.7; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>引证卫士 CiteGuard-CN · 引文体检报告</h1>
      <div class="sub">生成时间 {html.escape(report['generated_at'])} · 输入 {html.escape(report['input'])}</div>
    </div>
  </header>
  <div class="stats">
    <div class="stat"><b>{s['total']}</b><span>参考文献</span></div>
    <div class="stat"><b style="color:#1f9d55">{s['Exact']}</b><span>真实且一致</span></div>
    <div class="stat"><b style="color:#d97706">{s['Minor']}</b><span>元数据偏差</span></div>
    <div class="stat"><b style="color:#dc2626">{s['Major']}</b><span>疑似虚构/错配</span></div>
    <div class="stat"><b>{s['avg_compliance']}</b><span>新国标合规均分</span></div>
  </div>
  {''.join(cards)}
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
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path), "html": str(html_path)}
