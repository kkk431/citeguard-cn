"""Compute a descriptive prevalence report over real-corpus analysis reports.

Reads existing ``data/jobs/*/report.json`` files (no network, no LLM), keeps the
newest completed run per input filename, and reports how often common citation
problems occur. This is a descriptive measurement of our own corpus, not an
accuracy benchmark and not a human audit.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "data" / "jobs"
OUT = ROOT / "data" / "experiments" / "corpus_prevalence.json"
CJK = re.compile(r"[\u4e00-\u9fff]")


def _latest_reports() -> list[dict]:
    best: dict[str, tuple[float, dict]] = {}
    for path in JOBS.glob("*/report.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta_path = path.parent.parent / f"{path.parent.name}.json"
            name = ""
            if meta_path.exists():
                try:
                    name = json.loads(meta_path.read_text(encoding="utf-8")).get("filename") or ""
                except ValueError:
                    name = ""
            if not name:
                raw_input = data.get("input")
                if isinstance(raw_input, dict):
                    name = raw_input.get("name") or path.parent.name
                else:
                    name = Path(str(raw_input)).name if raw_input else path.parent.name
            if not name.lower().endswith(".pdf"):
                continue
            mtime = path.stat().st_mtime
            if name not in best or mtime > best[name][0]:
                best[name] = (mtime, data)
        except (OSError, ValueError):
            continue
    return [data for _, (_, data) in sorted(best.items())]


def main() -> int:
    reports = _latest_reports()
    refs = [ref for report in reports for ref in (report.get("references") or [])]
    issue_fields = Counter()
    issue_levels = Counter()
    with_issue = 0
    missing = Counter()
    status = Counter()
    chinese = Counter()
    uncited = 0
    papers_with_issue = 0
    for report in reports:
        report_has = False
        for ref in report.get("references") or []:
            comp = ref.get("compliance") or {}
            issues = comp.get("issues") or []
            if issues:
                with_issue += 1
                report_has = True
            for issue in issues:
                issue_fields[issue.get("field") or "other"] += 1
                issue_levels[issue.get("level") or "unknown"] += 1
            parsed = ref.get("parsed") or {}
            for field in ("doi", "pages", "venue", "year", "authors"):
                value = parsed.get(field)
                if not value or (isinstance(value, list) and not value):
                    missing[field] += 1
            status[(ref.get("verify") or {}).get("status") or "Unknown"] += 1
            raw = ref.get("raw") or ""
            is_cn = bool(CJK.search(raw))
            if is_cn:
                chinese[(ref.get("verify") or {}).get("status") or "Unknown"] += 1
        if report_has:
            papers_with_issue += 1
        uncited += len((report.get("citations") or {}).get("coverage", {}).get("uncited") or [])
    n = len(refs)
    report = {
        "papers": len(reports),
        "references": n,
        "papers_with_format_issue": papers_with_issue,
        "refs_with_format_issue": with_issue,
        "refs_with_format_issue_ratio": round(with_issue / n, 4) if n else 0,
        "papers_with_format_issue_ratio": round(papers_with_issue / len(reports), 4) if reports else 0,
        "issue_levels": dict(issue_levels),
        "issue_fields_top": issue_fields.most_common(10),
        "missing_field_refs": {k: {"count": v, "ratio": round(v / n, 4) if n else 0} for k, v in missing.items()},
        "verify_status": dict(status),
        "chinese_refs": sum(chinese.values()),
        "chinese_status": dict(chinese),
        "chinese_unresolved": chinese.get("Unverified", 0) + chinese.get("Unknown", 0),
        "uncited_refs": uncited,
        "note": "Descriptive only: newest completed report per input PDF; format issues counted by the GB/T rule engine; unresolved includes Unverified/Unknown; no human labels.",
        "files": [ (r.get("input") or {}).get("name") if isinstance(r.get("input"), dict) else Path(str(r.get("input"))).name for r in reports ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
