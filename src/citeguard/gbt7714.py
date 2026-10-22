"""GB/T 7714-2025 compliance rule engine (best-effort v0).

IMPORTANT: this module encodes *rule facts* (field requirements, type codes,
author-name style) derived from the official standard page and public
interpretations. It does NOT reproduce the standard text, and it is not a
substitute for the official standard. Rules that could not be verified against
the standard text are marked as ``unverified`` in the issue message.

Reference: GB/T 7714-2025《信息与文献 参考文献著录规则》
- published 2025-12-02, effective 2026-07-01, replaces GB/T 7714-2015.
- official page: https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=C6CE52E55AC09B9C79A20AEA77CEDD14
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from .reference_parser import Reference

KNOWN_TYPES = {
    "M", "J", "N", "C", "D", "R", "S", "P", "EB", "A", "CM",
    "DS", "PP", "G", "CP", "DB", "Z",
}

TYPE_NAMES = {
    "M": "图书",
    "J": "期刊",
    "N": "报纸",
    "C": "会议录",
    "D": "学位论文",
    "R": "报告",
    "S": "标准",
    "P": "专利",
    "EB": "网站/网页",
    "A": "档案",
    "CM": "地图",
    "DS": "数据集",
    "PP": "预印本",
    "G": "汇编",
    "CP": "计算机程序",
    "DB": "数据库",
    "Z": "其他",
}

# Required fields per type. "warn" means recommended, not hard-required.
REQUIRED: dict[str, list[str]] = {
    "J": ["title", "venue", "year"],
    "M": ["title", "place", "publisher", "year"],
    "D": ["title", "place", "institution", "year"],
    "C": ["title", "venue", "year"],
    "R": ["title", "report_no", "year"],
    "S": ["title", "standard_no"],
    "P": ["title", "patent_no", "year"],
    "EB": ["title", "url"],
    "A": ["title", "archive_no", "year"],
    "CM": ["title", "scale", "place", "publisher", "year"],
    "DS": ["title", "version", "platform", "year"],
    "PP": ["title", "version", "platform", "year"],
    "N": ["title", "venue", "year"],
}

RECOMMENDED: dict[str, list[str]] = {
    "J": ["volume", "pages", "doi"],
    "M": ["doi"],
    "D": ["doi"],
    "C": ["pages"],
    "EB": ["access_date"],
    "DS": ["doi"],
    "PP": ["doi"],
}

FIELD_LABELS = {
    "title": "题名",
    "venue": "来源（期刊/会议/报纸名）",
    "year": "年份",
    "volume": "卷",
    "issue": "期",
    "pages": "页码",
    "doi": "永久标识符（DOI 等）",
    "url": "获取和访问路径",
    "place": "出版地",
    "publisher": "出版者",
    "institution": "学位授予单位",
    "report_no": "报告编号",
    "standard_no": "标准编号",
    "patent_no": "专利申请号/公告号",
    "archive_no": "档号",
    "scale": "比例尺",
    "version": "版本",
    "platform": "发布平台",
    "access_date": "引用日期",
}


@dataclass
class Issue:
    level: str  # error / warning / info
    field: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComplianceResult:
    score: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.level == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.level == "warning")

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "errors": self.errors,
            "warnings": self.warnings,
            "issues": [i.to_dict() for i in self.issues],
        }


def _get(ref: Reference, field_name: str) -> str:
    if field_name == "doi":
        return ref.doi or ref.url
    return str(getattr(ref, field_name, "") or "")


_ALL_CAPS_LATIN = re.compile(r"\b[A-Z]{2,}(?:\s+[A-Z]{2,})?\b")


def check_authors(ref: Reference) -> list[Issue]:
    issues: list[Issue] = []
    if not ref.authors:
        issues.append(
            Issue("warning", "authors", "未解析到作者", "确认作者姓名与分隔符（, / ，）是否正确")
        )
        return issues
    for a in ref.authors:
        if _ALL_CAPS_LATIN.search(a):
            issues.append(
                Issue(
                    "warning",
                    "authors",
                    f"作者“{a}”疑似 2015 版“姓氏全大写”写法",
                    "GB/T 7714-2025 将姓氏改为仅首字母大写；建议核对后改为首字母大写（依据公开解读，需以标准原文复核）",
                )
            )
            break
    return issues


def check_punctuation(ref: Reference) -> list[Issue]:
    issues: list[Issue] = []
    if not ref.title:
        return issues
    if ref.doc_type in KNOWN_TYPES:
        m = re.search(r"(.?)\[%s(?:/OL)?\]" % re.escape(ref.doc_type), ref.raw)
        # GB/T 7714 顺序编码制把文献类型标识紧跟在题名之后（题名[J]），
        # 题名与标识之间不应出现句点；出现「题名.[J]」才是需要报出的缺陷。
        if m and m.group(1) in {".", "．"}:
            issues.append(
                Issue(
                    "error",
                    "punctuation",
                    "题名与文献类型标识之间不应有“.”",
                    "改为“题名[类型标识]”",
                )
            )
    if not re.search(r"[.．。]\s*$", ref.raw.strip()) and not ref.url:
        issues.append(Issue("warning", "punctuation", "条目末尾缺少“.”", "在条目末尾补“.”"))
    return issues


def check_reference(ref: Reference) -> ComplianceResult:
    issues: list[Issue] = []

    if not ref.title:
        issues.append(Issue("error", "title", "未解析到题名", "检查题名与作者之间的“.”分隔"))

    if not ref.doc_type:
        issues.append(
            Issue("error", "doc_type", "未识别文献类型标识", "补充 [J]/[M]/[D]/[C]/[R]/[S]/[EB]/[DS]/[PP] 等")
        )
    elif ref.doc_type not in KNOWN_TYPES:
        issues.append(Issue("warning", "doc_type", f"未知文献类型 [{ref.doc_type}]", "核对类型代码"))

    if ref.doc_type in KNOWN_TYPES:
        for f in REQUIRED.get(ref.doc_type, []):
            if not _get(ref, f):
                issues.append(
                    Issue("error", f, f"缺少{ FIELD_LABELS.get(f, f) }", f"补充{ FIELD_LABELS.get(f, f) }")
                )
        for f in RECOMMENDED.get(ref.doc_type, []):
            if not _get(ref, f):
                issues.append(
                    Issue(
                        "warning",
                        f,
                        f"建议补充{ FIELD_LABELS.get(f, f) }",
                        f"有则必备：{ FIELD_LABELS.get(f, f) }",
                    )
                )

    if ref.doc_type == "J" and not (ref.volume or ref.issue):
        issues.append(Issue("warning", "volume", "期刊条目建议给出卷/期", "补充“卷(期)”"))

    issues.extend(check_authors(ref))
    issues.extend(check_punctuation(ref))

    if ref.doc_type in {"EB", "DS", "PP"} and not ref.has_online_marker:
        issues.append(Issue("info", "online", "电子资源建议标注载体标识 /OL", "视需要写作 [EB/OL]、[DS/OL]、[PP/OL]"))

    score = 100
    for i in issues:
        score -= {"error": 12, "warning": 4, "info": 1}.get(i.level, 1)
    score = max(0, min(100, score))

    return ComplianceResult(score=score, issues=issues)


def check_reference_list(refs: list[Reference]) -> list[ComplianceResult]:
    return [check_reference(r) for r in refs]


def summarize(results: list[ComplianceResult]) -> dict:
    n = len(results)
    if n == 0:
        return {"count": 0, "avg_score": 0, "errors": 0, "warnings": 0, "clean": 0}
    return {
        "count": n,
        "avg_score": round(sum(r.score for r in results) / n, 1),
        "errors": sum(r.errors for r in results),
        "warnings": sum(r.warnings for r in results),
        "clean": sum(1 for r in results if r.errors == 0),
    }
