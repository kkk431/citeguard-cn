"""Version-aware entity resolution for citation matching.

A citation is not always a single record: the same work can appear as an
arXiv preprint, a conference paper, a journal article, and a correction.  This
module groups candidate records by DOI/arXiv alias, reports which version the
citation names, and separates "same title, different work" from "same work,
different version".  It is deliberately pure: no network, no global state.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from rapidfuzz import fuzz

from .metadata_verify import Candidate
from .reference_parser import Reference

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
_ARXIV_RE = re.compile(r"(?:arxiv(?:\.org/(?:abs|pdf)/)?[:\s/]*)(\d{4}\.\d{4,5})(?:v\d+)?", re.I)


def normalize_doi(value: str) -> str:
    text = (value or "").strip()
    text = _DOI_PREFIX.sub("", text)
    return text.rstrip(".,;）)").lower()


def extract_arxiv_id(value: str) -> str:
    m = _ARXIV_RE.search(value or "")
    return m.group(1) if m else ""


def norm_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    return "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def version_kind(candidate: Candidate) -> str:
    """preprint / published / unknown, based on identifiers and venue."""
    doi = normalize_doi(candidate.doi)
    source = (candidate.source or "").lower()
    if "arxiv" in source or "arxiv" in (candidate.url or "").lower() or doi.startswith("10.48550/arxiv") or extract_arxiv_id(candidate.url):
        return "preprint"
    if candidate.venue or (doi and not doi.startswith("10.48550/arxiv")):
        return "published"
    return "unknown"


@dataclass
class VersionResolution:
    status: str  # same_version / version_family / conflict / insufficient
    chosen: Optional[Candidate] = None
    alternatives: list[Candidate] = field(default_factory=list)
    cited_year_supported: bool = False
    conflicts: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "cited_year_supported": self.cited_year_supported,
            "conflicts": self.conflicts,
            "provenance": self.provenance,
            "notes": self.notes,
            "chosen": {
                "source": self.chosen.source,
                "doi": self.chosen.doi,
                "year": self.chosen.year,
                "venue": self.chosen.venue,
                "title": self.chosen.title,
            } if self.chosen else None,
            "alternatives": [
                {"source": c.source, "doi": c.doi, "year": c.year, "venue": c.venue}
                for c in self.alternatives
            ],
        }


def _first_author_family(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "," in value:
        return norm_title(value.split(",", 1)[0])
    parts = value.split()
    return norm_title(parts[-1]) if parts else ""


def _candidate_year(c: Candidate) -> Optional[int]:
    return int(c.year) if isinstance(c.year, int) else None


def _title_sim(a: str, b: str) -> float:
    return fuzz.ratio(norm_title(a), norm_title(b)) / 100.0


def _author_sim(ref: Reference, c: Candidate) -> float:
    if not (ref.authors and c.authors):
        return 0.0
    a = _first_author_family(ref.authors[0])
    b = _first_author_family(c.authors[0])
    if not a or not b:
        return 0.0
    return 1.0 if (a in b or b in a) else 0.0


def _identity(c: Candidate) -> str:
    doi = normalize_doi(c.doi)
    if doi:
        # arXiv DOIs and arXiv ids are one family, not two versions.
        aid = extract_arxiv_id(doi) or extract_arxiv_id(c.url)
        return f"arxiv:{aid}" if aid else f"doi:{doi}"
    aid = extract_arxiv_id(c.url) or extract_arxiv_id(c.title)
    if aid:
        return f"arxiv:{aid}"
    return f"title:{norm_title(c.title)}"


def resolve_versions(ref: Reference, candidates: list[Candidate]) -> VersionResolution:
    """Group candidates into work families and explain the cited version.

    Strictness matters: a title match from a different first author is treated
    as ``conflict`` (book review / same-title work), never silently upgraded.
    """
    if not (ref.title or "").strip():
        return VersionResolution("insufficient", notes=["引文题名为空，无法做版本消解"])
    usable = [c for c in candidates if c and c.title and _title_sim(ref.title, c.title) >= 0.90]
    if not usable:
        return VersionResolution("insufficient", notes=["没有题名相似度 ≥0.90 的候选，无法判断版本"])

    usable.sort(key=lambda c: (_title_sim(ref.title, c.title), _author_sim(ref, c), 1 if _candidate_year(c) == ref.year else 0), reverse=True)
    chosen = usable[0]
    families: dict[str, list[Candidate]] = {}
    for c in usable:
        families.setdefault(_identity(c), []).append(c)
    alt = [c for c in usable if _identity(c) != _identity(chosen)][:8]

    conflicts: list[str] = []
    if ref.authors and chosen.authors and _author_sim(ref, chosen) == 0.0:
        conflicts.append("authors")
    if ref.venue and chosen.venue and norm_title(ref.venue) not in norm_title(chosen.venue) and norm_title(chosen.venue) not in norm_title(ref.venue):
        # Venue strings are noisy; only record when both are long enough to compare.
        if len(norm_title(ref.venue)) >= 4 and len(norm_title(chosen.venue)) >= 4:
            conflicts.append("venue")
    if ref.year and chosen.year and int(ref.year) != int(chosen.year):
        conflicts.append("year")

    cited_year_supported = any(_candidate_year(c) == ref.year for c in usable) if ref.year else False
    provenance = [
        {
            "source": c.source,
            "identity": _identity(c),
            "kind": version_kind(c),
            "doi": c.doi,
            "year": c.year,
            "venue": c.venue,
            "url": c.url,
        }
        for c in [chosen] + alt
    ]

    if "authors" in conflicts:
        return VersionResolution("conflict", chosen, alt, cited_year_supported, conflicts, provenance,
                                 notes=["题名一致但第一作者不一致，可能是书评/同名作品；不得当作同一版本"])
    if len(families) > 1:
        kinds = {version_kind(c) for c in usable}
        note = "同一作品存在多个版本/来源（" + "、".join(sorted(kinds)) + "）"
        if cited_year_supported:
            note += "；引文年份可由其中一个版本支持"
        return VersionResolution("version_family", chosen, alt, cited_year_supported, conflicts, provenance, notes=[note])
    if conflicts:
        return VersionResolution("conflict", chosen, alt, cited_year_supported, conflicts, provenance,
                                 notes=["同一记录存在字段冲突：" + ",".join(conflicts)])
    return VersionResolution("same_version", chosen, alt, cited_year_supported, conflicts, provenance,
                             notes=["题名/作者一致，未发现多版本证据"])
