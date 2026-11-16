"""CiteMap: schema, loaders and validation for the CiteGuard evidence map.

CiteMap turns a literature topic into an auditable graph::

    Topic ──< Paper
      │
      ├──< Claim ──< Evidence >── Paper
      │                │
      │                ├── Method
      │                └── Sample
      └──< Gap

The module is intentionally dependency-free (standard library only) so the web
app, tests and offline tooling can share one definition.  JSON files under
``data/evidence_map/`` are the single source of truth; the dataclasses below
describe and validate them, they do not replace them.

Directory layout (relative to ``data/evidence_map/``)::

    index.json                     topic index (order + file pointers)
    verification.json              DOI / license verification evidence
    corpus/<topic_id>.json         one manifest per topic (papers only)
    extractions/<topic_id>.json    claims + evidence + gaps (human samples)
    graph/<topic_id>.json          projected paper/claim/evidence graph (spike)

Public API
----------
``SCHEMA_VERSION``, ``DEFAULT_DATA_DIR``
``EvidenceMapError``, ``UnknownTopicError``
``parse_corpus`` / ``load_corpus`` / ``validate_corpus``
``parse_map`` / ``load_map`` / ``validate_map``
``list_topics`` / ``topic_payload``
``build_graph`` / ``write_graph`` / ``validate_graph``
``main`` (CLI: ``python -m citeguard.evidence_map --check``)

Invariants enforced here (not all can be expressed in JSON Schema):
- identifiers are unique inside a document and stable across references;
- every ``Evidence`` points at a known claim (and, when a manifest is given,
  at a known paper);
- every paper carries a non-empty license, a normalized DOI and an OpenAlex id;
- ``fulltext_available`` implies an OA URL, and a license of ``unknown`` /
  ``closed`` cannot be combined with ``is_oa: true``;
- an evidence quote requires a locator (page/section/figure);
- ``method.sample_size`` and ``sample.size`` must agree when both are present;
- JSON with duplicate object keys is rejected instead of silently overwritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import types
from collections.abc import Mapping as MappingABC
from dataclasses import MISSING, asdict, dataclass, fields, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Union, get_args, get_origin, get_type_hints

__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_DATA_DIR",
    "STANCES",
    "GAP_KINDS",
    "SEVERITIES",
    "Stance",
    "Topic",
    "Paper",
    "Claim",
    "Method",
    "Sample",
    "Evidence",
    "Gap",
    "CorpusManifest",
    "EvidenceMap",
    "EvidenceMapError",
    "UnknownTopicError",
    "normalize_doi",
    "read_json",
    "parse_corpus",
    "load_corpus",
    "validate_corpus",
    "parse_map",
    "load_map",
    "validate_map",
    "list_topics",
    "topic_payload",
    "build_graph",
    "write_graph",
    "validate_graph",
    "main",
]

SCHEMA_VERSION = "1.0"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "evidence_map"

INDEX_FILENAME = "index.json"
VERIFICATION_FILENAME = "verification.json"
CORPUS_DIRNAME = "corpus"
EXTRACTIONS_DIRNAME = "extractions"
GRAPH_DIRNAME = "graph"
GRAPH_NODE_TYPES: tuple[str, ...] = ("paper", "claim", "evidence")
GRAPH_EDGE_KINDS: tuple[str, ...] = ("supports", "contradicts", "none", "abstract_only")
GRAPH_LEVELS: tuple[str, ...] = ("fulltext", "abstract", "machine")

STANCES: tuple[str, ...] = ("support", "contradict", "neutral")
GAP_KINDS: tuple[str, ...] = ("evidence", "method", "sample", "outcome", "theory")
SEVERITIES: tuple[str, ...] = ("low", "medium", "high")
RISK_OF_BIAS: tuple[str, ...] = ("low", "some", "high", "unclear")
OA_STATUSES: tuple[str, ...] = (
    "gold",
    "hybrid",
    "green",
    "bronze",
    "diamond",
    "closed",
    "unknown",
)
DIRECTIONS: tuple[str, ...] = (
    "",
    "positive",
    "negative",
    "no_effect",
    "mixed",
    "unclear",
)
LICENSE_UNKNOWN_VALUES: tuple[str, ...] = ("unknown", "closed")

_TOPIC_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_RECORD_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{1,63}$")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_OPENALEX_ID_RE = re.compile(r"^W\d{6,}$")
_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_LICENSE_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)


class EvidenceMapError(ValueError):
    """Raised when an evidence-map document violates the schema.

    ``context`` is filled in by loaders with the file path (and, for nested
    records, the JSON path) so an error is actionable for a data maintainer.
    """

    def __init__(self, message: str, *, context: str | None = None) -> None:
        self.message = message
        self.context = context
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        return f"{self.context}: {self.message}" if self.context else self.message


class UnknownTopicError(EvidenceMapError):
    """Raised when a topic id is not present in ``index.json``."""

    def __init__(self, topic_id: str, known: list[str]) -> None:
        self.topic_id = topic_id
        self.known = known
        sql = "、".join(known) if known else "（无）"
        super().__init__(f"未知主题 {topic_id!r}；已知主题：{sql}")


class Stance(str, Enum):
    """How a paper's finding relates to a claim."""

    SUPPORT = "support"
    CONTRADICT = "contradict"
    NEUTRAL = "neutral"


# ---------------------------------------------------------------------------
# Small validation helpers
# ---------------------------------------------------------------------------


def _text(
    value: Any,
    name: str,
    *,
    required: bool = True,
    max_len: int = 4000,
) -> str:
    if not isinstance(value, str):
        raise EvidenceMapError(f"{name} 必须是字符串，实际为 {type(value).__name__}")
    value = value.strip()
    if required and not value:
        raise EvidenceMapError(f"{name} 不能为空")
    if len(value) > max_len:
        raise EvidenceMapError(f"{name} 超过 {max_len} 字符上限")
    return value


def _text_tuple(
    value: Any,
    name: str,
    *,
    allow_empty: bool = False,
    max_len: int = 500,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise EvidenceMapError(f"{name} 必须是字符串数组")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise EvidenceMapError(f"{name}[{index}] 必须是非空字符串")
        item = item.strip()
        if len(item) > max_len:
            raise EvidenceMapError(f"{name}[{index}] 超过 {max_len} 字符上限")
        items.append(item)
    if not items and not allow_empty:
        raise EvidenceMapError(f"{name} 不能为空数组")
    return tuple(items)


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise EvidenceMapError(f"{name} 必须是布尔值，实际为 {type(value).__name__}")
    return value


def _integer(
    value: Any,
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceMapError(f"{name} 必须是整数，实际为 {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise EvidenceMapError(f"{name} 不能小于 {minimum}（实际 {value}）")
    if maximum is not None and value > maximum:
        raise EvidenceMapError(f"{name} 不能大于 {maximum}（实际 {value}）")
    return value


def _number(value: Any, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceMapError(f"{name} 必须是数字，实际为 {type(value).__name__}")
    value = float(value)
    if not minimum <= value <= maximum:
        raise EvidenceMapError(f"{name} 必须位于 [{minimum}, {maximum}]（实际 {value}）")
    return value


def _choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise EvidenceMapError(f"{name} 必须是字符串")
    value = value.strip().lower()
    if value not in choices:
        raise EvidenceMapError(f"{name} 取值 {value!r} 非法，允许：{', '.join(choices)}")
    return value


def _record_id(value: Any, name: str) -> str:
    value = _text(value, name, max_len=64)
    if not _RECORD_ID_RE.fullmatch(value):
        raise EvidenceMapError(
            f"{name} 格式非法：{value!r}（需以字母开头，仅含字母/数字/_.:-，长度 2-64）"
        )
    return value


def _topic_id(value: Any, name: str) -> str:
    value = _text(value, name, max_len=40)
    if not _TOPIC_ID_RE.fullmatch(value):
        raise EvidenceMapError(
            f"{name} 格式非法：{value!r}（小写字母开头，仅含小写字母/数字/下划线）"
        )
    return value


def _date_text(value: Any, name: str) -> str:
    value = _text(value, name, required=False, max_len=10)
    if not value:
        return ""
    if not _DATE_RE.fullmatch(value):
        raise EvidenceMapError(f"{name} 必须是 YYYY-MM-DD 格式，实际 {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceMapError(f"{name} 不是合法日期：{value!r}") from exc
    return value


def _check_schema_version(value: Any) -> str:
    if value != SCHEMA_VERSION:
        raise EvidenceMapError(
            f"schema_version 必须为 {SCHEMA_VERSION!r}，实际 {value!r}"
        )
    return SCHEMA_VERSION


def normalize_doi(value: Any) -> str:
    """Return a bare DOI (no resolver prefix), preserving case."""

    doi = _text(value, "paper.doi", max_len=300)
    lowered = doi.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            doi = doi[len(prefix) :].strip()
            break
    if not _DOI_RE.fullmatch(doi):
        raise EvidenceMapError(f"paper.doi 格式非法：{doi!r}（应为 10.xxxx/...）")
    return doi


def _check_license(value: Any) -> str:
    license_id = _text(value, "paper.license", max_len=80).lower()
    if not _LICENSE_RE.fullmatch(license_id):
        raise EvidenceMapError(f"paper.license 格式非法：{license_id!r}")
    return license_id


def _check_url(value: Any, name: str) -> str:
    url = _text(value, name, required=False, max_len=2000)
    if url and not _URL_RE.fullmatch(url):
        raise EvidenceMapError(f"{name} 必须是 http(s) URL，实际 {url!r}")
    return url


def _set(obj: Any, name: str, value: Any) -> None:
    object.__setattr__(obj, name, value)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for value in values:
        if value in seen and value not in dupes:
            dupes.append(value)
        seen.add(value)
    return dupes


def _fail_duplicates(values: list[str], label: str) -> None:
    dupes = _duplicates(values)
    if dupes:
        raise EvidenceMapError(f"{label} 重复：{', '.join(dupes)}")


# ---------------------------------------------------------------------------
# Generic JSON -> dataclass coercion (strict: no unknown fields, no missing ones)
# ---------------------------------------------------------------------------


def _coerce(value: Any, hint: Any, path: str) -> Any:
    origin = get_origin(hint)

    if origin is Union or origin is types.UnionType:
        args = list(get_args(hint))
        optional = type(None) in args
        concrete = [arg for arg in args if arg is not type(None)]
        if value is None:
            if optional:
                return None
            raise EvidenceMapError(f"{path} 不能为 null")
        if len(concrete) == 1:
            return _coerce(value, concrete[0], path)
        last: EvidenceMapError | None = None
        for arg in concrete:
            try:
                return _coerce(value, arg, path)
            except EvidenceMapError as exc:  # try the next union member
                last = exc
        raise last or EvidenceMapError(f"{path} 类型不匹配")

    if origin is tuple:
        args = get_args(hint)
        if not isinstance(value, (list, tuple)):
            raise EvidenceMapError(f"{path} 必须是数组")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(
                _coerce(item, args[0], f"{path}[{index}]")
                for index, item in enumerate(value)
            )
        if len(args) != len(value):
            raise EvidenceMapError(f"{path} 数组长度应为 {len(args)}")
        return tuple(
            _coerce(item, args[index], f"{path}[{index}]")
            for index, item in enumerate(value)
        )

    if origin is not None:
        raise EvidenceMapError(f"{path} 使用了不支持的容器类型 {hint!r}")

    if isinstance(hint, type):
        if issubclass(hint, Enum):
            if isinstance(value, hint):
                return value
            try:
                return hint(value)
            except ValueError as exc:
                allowed = ", ".join(member.value for member in hint)
                raise EvidenceMapError(
                    f"{path} 取值 {value!r} 非法，允许：{allowed}"
                ) from exc
        if hint is bool:
            return _boolean(value, path)
        if hint is int:
            return _integer(value, path)
        if hint is float:
            return _number(value, path, minimum=float("-inf"), maximum=float("inf"))
        if hint is str:
            if not isinstance(value, str):
                raise EvidenceMapError(f"{path} 必须是字符串")
            return value
        if is_dataclass(hint):
            if isinstance(value, hint):
                return value
            if isinstance(value, MappingABC):
                return _from_mapping(hint, value, path)
            raise EvidenceMapError(f"{path} 必须是对象")

    raise EvidenceMapError(f"{path} 不支持的 schema 类型 {hint!r}")


def _from_mapping(cls: type, data: Any, path: str) -> Any:
    if not isinstance(data, MappingABC):
        raise EvidenceMapError(f"{path} 必须是 JSON 对象，实际为 {type(data).__name__}")

    declared = fields(cls)
    known = {field.name for field in declared}
    unknown = sorted(set(data) - known)
    if unknown:
        raise EvidenceMapError(f"{path} 含未知字段：{', '.join(unknown)}")

    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for field in declared:
        if field.name not in data:
            required = field.default is MISSING and field.default_factory is MISSING
            if required:
                raise EvidenceMapError(f"{path}.{field.name} 缺失（必填）")
            continue
        kwargs[field.name] = _coerce(
            data[field.name], hints[field.name], f"{path}.{field.name}"
        )

    try:
        return cls(**kwargs)
    except EvidenceMapError as exc:
        if exc.context is None:
            exc.context = path
        raise


def _plain(value: Any) -> Any:
    """Recursively convert schema objects/enums into JSON-ready values."""

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, MappingABC):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class _JsonModel:
    """Mixin adding strict ``from_dict`` / ``to_dict`` helpers."""

    @classmethod
    def from_dict(cls, data: Any, *, source: str | None = None) -> Any:
        try:
            return _from_mapping(cls, data, cls.__name__)
        except EvidenceMapError as exc:
            if source is not None and exc.context is None:
                exc.context = source
            raise

    def to_dict(self) -> dict[str, Any]:
        return _plain(asdict(self))


# ---------------------------------------------------------------------------
# Schema entities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Topic(_JsonModel):
    topic_id: str
    name_zh: str
    name_en: str
    question: str
    description: str = ""

    def __post_init__(self) -> None:
        _set(self, "topic_id", _topic_id(self.topic_id, "topic.topic_id"))
        _set(self, "name_zh", _text(self.name_zh, "topic.name_zh", max_len=120))
        _set(self, "name_en", _text(self.name_en, "topic.name_en", max_len=160))
        _set(self, "question", _text(self.question, "topic.question", max_len=600))
        _set(self, "description", _text(self.description, "topic.description", required=False, max_len=2000))


@dataclass(frozen=True)
class Paper(_JsonModel):
    paper_id: str
    title: str
    authors: tuple[str, ...]
    year: int
    venue: str
    doi: str
    openalex_id: str
    url: str
    license: str
    is_oa: bool
    fulltext_available: bool
    oa_url: str = ""
    oa_status: str = "unknown"
    language: str = "en"
    topic_id: str = ""
    cn_affiliated: bool = False
    cited_by: int = 0
    source: str = "openalex"
    notes: str = ""

    def __post_init__(self) -> None:
        _set(self, "paper_id", _record_id(self.paper_id, "paper.paper_id"))
        _set(self, "title", _text(self.title, "paper.title", max_len=1200))
        _set(self, "authors", _text_tuple(self.authors, "paper.authors", max_len=200))
        _set(self, "year", _integer(self.year, "paper.year", minimum=1900, maximum=2100))
        _set(self, "venue", _text(self.venue, "paper.venue", max_len=300))
        _set(self, "doi", normalize_doi(self.doi))

        openalex_id = _text(self.openalex_id, "paper.openalex_id", max_len=32).upper()
        if not _OPENALEX_ID_RE.fullmatch(openalex_id):
            raise EvidenceMapError(
                f"paper.openalex_id 格式非法：{openalex_id!r}（应为 W 加数字）"
            )
        _set(self, "openalex_id", openalex_id)

        _set(self, "url", _check_url(self.url, "paper.url"))
        _set(self, "license", _check_license(self.license))
        _set(self, "is_oa", _boolean(self.is_oa, "paper.is_oa"))
        _set(
            self,
            "fulltext_available",
            _boolean(self.fulltext_available, "paper.fulltext_available"),
        )
        _set(self, "oa_url", _check_url(self.oa_url, "paper.oa_url"))
        _set(self, "oa_status", _choice(self.oa_status, "paper.oa_status", OA_STATUSES))
        _set(self, "language", _text(self.language, "paper.language", required=False, max_len=20).lower())

        topic_id = _text(self.topic_id, "paper.topic_id", required=False, max_len=40)
        if topic_id:
            topic_id = _topic_id(topic_id, "paper.topic_id")
        _set(self, "topic_id", topic_id)

        _set(self, "cn_affiliated", _boolean(self.cn_affiliated, "paper.cn_affiliated"))
        _set(self, "cited_by", _integer(self.cited_by, "paper.cited_by", minimum=0))
        _set(self, "source", _text(self.source, "paper.source", max_len=80))
        _set(self, "notes", _text(self.notes, "paper.notes", required=False, max_len=2000))

        if not self.url:
            raise EvidenceMapError("paper.url 不能为空")
        if self.fulltext_available:
            if not self.is_oa:
                raise EvidenceMapError(
                    f"paper {self.paper_id}: fulltext_available=true 需要 is_oa=true"
                )
            if not self.oa_url:
                raise EvidenceMapError(
                    f"paper {self.paper_id}: fulltext_available=true 需要 oa_url"
                )
        if self.is_oa and self.license in LICENSE_UNKNOWN_VALUES:
            raise EvidenceMapError(
                f"paper {self.paper_id}: is_oa=true 时 license 不能为 {self.license!r}"
            )


@dataclass(frozen=True)
class Claim(_JsonModel):
    claim_id: str
    topic_id: str
    text: str
    population: str = ""
    outcome: str = ""
    direction: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        _set(self, "claim_id", _record_id(self.claim_id, "claim.claim_id"))
        _set(self, "topic_id", _topic_id(self.topic_id, "claim.topic_id"))
        _set(self, "text", _text(self.text, "claim.text", max_len=1200))
        _set(self, "population", _text(self.population, "claim.population", required=False, max_len=300))
        _set(self, "outcome", _text(self.outcome, "claim.outcome", required=False, max_len=300))
        _set(self, "direction", _choice(self.direction, "claim.direction", DIRECTIONS))
        _set(self, "notes", _text(self.notes, "claim.notes", required=False, max_len=2000))


@dataclass(frozen=True)
class Method(_JsonModel):
    method_id: str
    design: str
    sample_size: int | None = None
    population: str = ""
    setting: str = ""
    instruments: tuple[str, ...] = ()
    analysis: str = ""
    risk_of_bias: str = "unclear"

    def __post_init__(self) -> None:
        _set(self, "method_id", _record_id(self.method_id, "method.method_id"))
        _set(self, "design", _text(self.design, "method.design", max_len=400))
        if self.sample_size is not None:
            _set(
                self,
                "sample_size",
                _integer(self.sample_size, "method.sample_size", minimum=1),
            )
        _set(self, "population", _text(self.population, "method.population", required=False, max_len=300))
        _set(self, "setting", _text(self.setting, "method.setting", required=False, max_len=300))
        _set(
            self,
            "instruments",
            _text_tuple(self.instruments, "method.instruments", allow_empty=True, max_len=200),
        )
        _set(self, "analysis", _text(self.analysis, "method.analysis", required=False, max_len=400))
        _set(
            self,
            "risk_of_bias",
            _choice(self.risk_of_bias, "method.risk_of_bias", RISK_OF_BIAS),
        )


@dataclass(frozen=True)
class Sample(_JsonModel):
    sample_id: str
    size: int
    unit: str
    population: str
    setting: str = ""
    country: str = ""
    recruitment: str = ""

    def __post_init__(self) -> None:
        _set(self, "sample_id", _record_id(self.sample_id, "sample.sample_id"))
        _set(self, "size", _integer(self.size, "sample.size", minimum=1))
        _set(self, "unit", _text(self.unit, "sample.unit", max_len=80))
        _set(self, "population", _text(self.population, "sample.population", max_len=300))
        _set(self, "setting", _text(self.setting, "sample.setting", required=False, max_len=300))
        _set(self, "country", _text(self.country, "sample.country", required=False, max_len=80))
        _set(self, "recruitment", _text(self.recruitment, "sample.recruitment", required=False, max_len=300))


@dataclass(frozen=True)
class Evidence(_JsonModel):
    evidence_id: str
    claim_id: str
    paper_id: str
    stance: Stance
    summary: str
    quote: str = ""
    quote_lang: str = "en"
    locator: str = ""
    method: Method | None = None
    sample: Sample | None = None
    confidence: float = 0.5
    extracted_by: str = "human"
    verified: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        _set(self, "evidence_id", _record_id(self.evidence_id, "evidence.evidence_id"))
        _set(self, "claim_id", _record_id(self.claim_id, "evidence.claim_id"))
        _set(self, "paper_id", _record_id(self.paper_id, "evidence.paper_id"))
        if not isinstance(self.stance, Stance):
            try:
                _set(self, "stance", Stance(self.stance))
            except ValueError as exc:
                raise EvidenceMapError(
                    f"evidence.stance 取值 {self.stance!r} 非法，允许：{', '.join(STANCES)}"
                ) from exc
        _set(self, "summary", _text(self.summary, "evidence.summary", max_len=2000))
        _set(self, "quote", _text(self.quote, "evidence.quote", required=False, max_len=8000))
        _set(self, "quote_lang", _text(self.quote_lang, "evidence.quote_lang", required=False, max_len=20).lower())
        _set(self, "locator", _text(self.locator, "evidence.locator", required=False, max_len=300))
        _set(self, "confidence", _number(self.confidence, "evidence.confidence", minimum=0.0, maximum=1.0))
        _set(self, "extracted_by", _text(self.extracted_by, "evidence.extracted_by", max_len=120))
        _set(self, "verified", _boolean(self.verified, "evidence.verified"))
        _set(self, "notes", _text(self.notes, "evidence.notes", required=False, max_len=3000))

        if self.method is not None and not isinstance(self.method, Method):
            raise EvidenceMapError("evidence.method 必须是 Method 对象")
        if self.sample is not None and not isinstance(self.sample, Sample):
            raise EvidenceMapError("evidence.sample 必须是 Sample 对象")
        if self.quote and not self.locator:
            raise EvidenceMapError(
                f"evidence {self.evidence_id}: 引用原文时必须有 locator（页码/章节/摘要）"
            )
        if self.verified and not self.locator:
            raise EvidenceMapError(
                f"evidence {self.evidence_id}: verified=true 时必须有 locator"
            )
        if (
            self.method is not None
            and self.sample is not None
            and self.method.sample_size is not None
            and self.method.sample_size != self.sample.size
        ):
            raise EvidenceMapError(
                f"evidence {self.evidence_id}: method.sample_size "
                f"({self.method.sample_size}) 与 sample.size ({self.sample.size}) 不一致"
            )


@dataclass(frozen=True)
class Gap(_JsonModel):
    gap_id: str
    topic_id: str
    kind: str
    description: str
    related_claim_ids: tuple[str, ...] = ()
    severity: str = "medium"
    rationale: str = ""

    def __post_init__(self) -> None:
        _set(self, "gap_id", _record_id(self.gap_id, "gap.gap_id"))
        _set(self, "topic_id", _topic_id(self.topic_id, "gap.topic_id"))
        _set(self, "kind", _choice(self.kind, "gap.kind", GAP_KINDS))
        _set(self, "description", _text(self.description, "gap.description", max_len=2000))
        _set(
            self,
            "related_claim_ids",
            _text_tuple(self.related_claim_ids, "gap.related_claim_ids", allow_empty=True, max_len=64),
        )
        _set(self, "severity", _choice(self.severity, "gap.severity", SEVERITIES))
        _set(self, "rationale", _text(self.rationale, "gap.rationale", required=False, max_len=2000))


@dataclass(frozen=True)
class CorpusManifest(_JsonModel):
    schema_version: str
    topic: Topic
    papers: tuple[Paper, ...]
    generated_at: str = ""
    source: str = ""
    selection: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        _set(self, "schema_version", _check_schema_version(self.schema_version))
        if not isinstance(self.topic, Topic):
            raise EvidenceMapError("corpus.topic 必须是 Topic 对象")
        if not self.papers:
            raise EvidenceMapError("corpus.papers 不能为空")
        _set(self, "generated_at", _date_text(self.generated_at, "corpus.generated_at"))
        _set(self, "source", _text(self.source, "corpus.source", required=False, max_len=1000))
        _set(self, "selection", _text(self.selection, "corpus.selection", required=False, max_len=2000))
        _set(self, "notes", _text(self.notes, "corpus.notes", required=False, max_len=2000))
        _validate_corpus(self)


@dataclass(frozen=True)
class EvidenceMap(_JsonModel):
    schema_version: str
    topic: Topic
    claims: tuple[Claim, ...]
    evidence: tuple[Evidence, ...]
    auto_evidence: tuple[Evidence, ...] = ()
    gaps: tuple[Gap, ...] = ()
    extractor: str = ""
    extracted_at: str = ""
    protocol: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        _set(self, "schema_version", _check_schema_version(self.schema_version))
        if not isinstance(self.topic, Topic):
            raise EvidenceMapError("map.topic 必须是 Topic 对象")
        if not self.claims:
            raise EvidenceMapError("map.claims 不能为空")
        if not self.evidence:
            raise EvidenceMapError("map.evidence 不能为空")
        _set(self, "extractor", _text(self.extractor, "map.extractor", required=False, max_len=200))
        _set(self, "extracted_at", _date_text(self.extracted_at, "map.extracted_at"))
        _set(self, "protocol", _text(self.protocol, "map.protocol", required=False, max_len=3000))
        _set(self, "notes", _text(self.notes, "map.notes", required=False, max_len=3000))
        _validate_map(self)

    def stance_counts(self) -> dict[str, int]:
        counts = {stance: 0 for stance in STANCES}
        for item in self.evidence:
            counts[item.stance.value] += 1
        return counts

    def auto_stance_counts(self) -> dict[str, int]:
        counts = {stance: 0 for stance in STANCES}
        for item in self.auto_evidence:
            counts[item.stance.value] += 1
        return counts


# ---------------------------------------------------------------------------
# Cross-record validation
# ---------------------------------------------------------------------------


def _validate_corpus(manifest: CorpusManifest) -> None:
    _fail_duplicates([paper.paper_id for paper in manifest.papers], "paper_id")
    _fail_duplicates([paper.doi.lower() for paper in manifest.papers], "DOI")
    _fail_duplicates([paper.openalex_id for paper in manifest.papers], "OpenAlex ID")

    for paper in manifest.papers:
        if paper.topic_id != manifest.topic.topic_id:
            raise EvidenceMapError(
                f"paper {paper.paper_id} 的 topic_id {paper.topic_id!r} "
                f"与 manifest 主题 {manifest.topic.topic_id!r} 不一致"
            )


def validate_corpus(manifest: CorpusManifest, *, expected_papers: int | None = None) -> None:
    """Validate a parsed manifest, optionally asserting the paper count."""

    if not isinstance(manifest, CorpusManifest):
        raise EvidenceMapError("validate_corpus 需要 CorpusManifest")
    _validate_corpus(manifest)
    if expected_papers is not None and len(manifest.papers) != expected_papers:
        raise EvidenceMapError(
            f"主题 {manifest.topic.topic_id} 应有 {expected_papers} 篇论文，"
            f"实际 {len(manifest.papers)} 篇"
        )


def _validate_map(evidence_map: EvidenceMap) -> None:
    claim_ids = [claim.claim_id for claim in evidence_map.claims]
    evidence_ids = [item.evidence_id for item in evidence_map.evidence]
    auto_ids = [item.evidence_id for item in evidence_map.auto_evidence]
    gap_ids = [gap.gap_id for gap in evidence_map.gaps]

    _fail_duplicates(claim_ids, "claim_id")
    _fail_duplicates(evidence_ids + auto_ids, "evidence_id")
    _fail_duplicates(gap_ids, "gap_id")

    known_claims = set(claim_ids)
    for claim in evidence_map.claims:
        if claim.topic_id != evidence_map.topic.topic_id:
            raise EvidenceMapError(
                f"claim {claim.claim_id} 的 topic_id 与 map 主题不一致"
            )

    for item in evidence_map.evidence:
        if item.claim_id not in known_claims:
            raise EvidenceMapError(
                f"evidence {item.evidence_id} 引用了未知 claim {item.claim_id!r}"
            )

    for item in evidence_map.auto_evidence:
        if item.claim_id not in known_claims:
            raise EvidenceMapError(
                f"auto_evidence {item.evidence_id} 引用了未知 claim "
                f"{item.claim_id!r}"
            )
        if not item.extracted_by.lower().startswith("auto"):
            raise EvidenceMapError(
                f"auto_evidence {item.evidence_id} 的 extracted_by 必须以 auto 开头"
            )
        if item.verified:
            raise EvidenceMapError(
                f"auto_evidence {item.evidence_id} 不得标记 verified=true"
            )

    for gap in evidence_map.gaps:
        if gap.topic_id != evidence_map.topic.topic_id:
            raise EvidenceMapError(f"gap {gap.gap_id} 的 topic_id 与 map 主题不一致")
        for claim_id in gap.related_claim_ids:
            if claim_id not in known_claims:
                raise EvidenceMapError(
                    f"gap {gap.gap_id} 引用了未知 claim {claim_id!r}"
                )


def validate_map(
    evidence_map: EvidenceMap,
    *,
    corpus: CorpusManifest | None = None,
    expected_evidence: int | None = None,
) -> None:
    """Validate a parsed extraction map against itself and, optionally, a corpus."""

    if not isinstance(evidence_map, EvidenceMap):
        raise EvidenceMapError("validate_map 需要 EvidenceMap")
    _validate_map(evidence_map)

    if corpus is not None:
        if evidence_map.topic.topic_id != corpus.topic.topic_id:
            raise EvidenceMapError(
                f"extraction 主题 {evidence_map.topic.topic_id!r} 与 "
                f"corpus 主题 {corpus.topic.topic_id!r} 不一致"
            )
        if evidence_map.topic != corpus.topic:
            raise EvidenceMapError(
                f"主题 {evidence_map.topic.topic_id} 在 corpus 与 extractions 中的元数据不一致"
            )
        paper_ids = {paper.paper_id for paper in corpus.papers}
        for item in evidence_map.evidence + evidence_map.auto_evidence:
            if item.paper_id not in paper_ids:
                raise EvidenceMapError(
                    f"evidence {item.evidence_id} 引用了 corpus 中不存在的 paper "
                    f"{item.paper_id!r}"
                )

    if expected_evidence is not None and len(evidence_map.evidence) != expected_evidence:
        raise EvidenceMapError(
            f"主题 {evidence_map.topic.topic_id} 应有 {expected_evidence} 条证据，"
            f"实际 {len(evidence_map.evidence)} 条"
        )


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceMapError(f"JSON 存在重复键：{key!r}")
        result[key] = value
    return result


def read_json(path: str | Path) -> Any:
    """Read JSON with UTF-8 and duplicate-key rejection."""

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvidenceMapError(f"无法读取文件：{exc}", context=str(path)) from exc
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise EvidenceMapError(
            f"JSON 解析失败：{exc.msg}（第 {exc.lineno} 行，第 {exc.colno} 列）",
            context=str(path),
        ) from exc
    except EvidenceMapError as exc:
        raise EvidenceMapError(exc.message, context=str(path)) from exc


def _attach_source(exc: EvidenceMapError, path: str | Path) -> EvidenceMapError:
    if exc.context is None:
        exc.context = str(path)
    return exc


def parse_corpus(data: Any, *, source: str | None = None) -> CorpusManifest:
    """Parse an already-decoded JSON object into a :class:`CorpusManifest`."""

    return CorpusManifest.from_dict(data, source=source)


def load_corpus(
    path: str | Path,
    *,
    expected_papers: int | None = None,
) -> CorpusManifest:
    """Load and fully validate one ``corpus/<topic>.json`` manifest."""

    path = Path(path)
    try:
        manifest = parse_corpus(read_json(path))
        validate_corpus(manifest, expected_papers=expected_papers)
    except EvidenceMapError as exc:
        raise _attach_source(exc, path)
    return manifest


def parse_map(
    data: Any,
    *,
    source: str | None = None,
    corpus: CorpusManifest | None = None,
    expected_evidence: int | None = None,
) -> EvidenceMap:
    """Parse an already-decoded JSON object into an :class:`EvidenceMap`."""

    evidence_map = EvidenceMap.from_dict(data, source=source)
    validate_map(
        evidence_map, corpus=corpus, expected_evidence=expected_evidence
    )
    return evidence_map


def load_map(
    path: str | Path,
    *,
    corpus: CorpusManifest | None = None,
    expected_evidence: int | None = None,
) -> EvidenceMap:
    """Load and fully validate one ``extractions/<topic>.json`` file."""

    path = Path(path)
    try:
        evidence_map = parse_map(read_json(path))
        validate_map(
            evidence_map, corpus=corpus, expected_evidence=expected_evidence
        )
    except EvidenceMapError as exc:
        raise _attach_source(exc, path)
    return evidence_map


# ---------------------------------------------------------------------------
# Topic index / web payloads
# ---------------------------------------------------------------------------


def _resolve_under(base: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise EvidenceMapError(f"index.json 不允许绝对路径：{relative!r}")
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise EvidenceMapError(f"index.json 路径越界：{relative!r}") from exc
    return resolved


def _load_index(data_dir: str | Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    base = Path(data_dir)
    index_path = base / INDEX_FILENAME
    index = read_json(index_path)
    if not isinstance(index, MappingABC):
        raise EvidenceMapError("index.json 顶层必须是对象", context=str(index_path))
    if index.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceMapError(
            f"index.json schema_version 必须为 {SCHEMA_VERSION!r}",
            context=str(index_path),
        )
    topics = index.get("topics")
    if not isinstance(topics, list) or not topics:
        raise EvidenceMapError("index.json.topics 必须是非空数组", context=str(index_path))

    required = ("topic_id", "name_zh", "name_en", "question", "corpus", "extractions")
    seen: list[str] = []
    entries: list[dict[str, Any]] = []
    for position, entry in enumerate(topics):
        if not isinstance(entry, MappingABC):
            raise EvidenceMapError(
                f"index.json.topics[{position}] 必须是对象", context=str(index_path)
            )
        missing = [key for key in required if not entry.get(key)]
        if missing:
            raise EvidenceMapError(
                f"index.json.topics[{position}] 缺少字段：{', '.join(missing)}",
                context=str(index_path),
            )
        topic_id = _topic_id(entry["topic_id"], f"index.topics[{position}].topic_id")
        _fail_duplicates(seen + [topic_id], "index topic_id")
        seen.append(topic_id)
        clean = dict(entry)
        clean["topic_id"] = topic_id
        clean["corpus"] = str(entry["corpus"])
        clean["extractions"] = str(entry["extractions"])
        entries.append(clean)
    return base, index, entries


def list_topics(data_dir: str | Path = DEFAULT_DATA_DIR) -> list[dict[str, Any]]:
    """Return validated topic summaries, ordered as in ``index.json``.

    Counts are computed from the files (not trusted from the index) so a stale
    index can never advertise numbers that the corpus does not contain.
    """

    base, _index, entries = _load_index(data_dir)
    summaries: list[dict[str, Any]] = []
    for entry in entries:
        corpus_path = _resolve_under(base, entry["corpus"])
        map_path = _resolve_under(base, entry["extractions"])
        corpus = load_corpus(corpus_path)
        evidence_map = load_map(map_path, corpus=corpus)
        summaries.append(
            {
                "topic_id": entry["topic_id"],
                "name_zh": entry["name_zh"],
                "name_en": entry["name_en"],
                "question": entry["question"],
                "description": corpus.topic.description,
                "papers": len(corpus.papers),
                "claims": len(evidence_map.claims),
                "evidence": len(evidence_map.evidence),
                "auto_evidence": len(evidence_map.auto_evidence),
                "gaps": len(evidence_map.gaps),
                "stances": evidence_map.stance_counts(),
                "auto_stances": evidence_map.auto_stance_counts(),
                "generated_at": corpus.generated_at,
                "corpus": entry["corpus"],
                "extractions": entry["extractions"],
            }
        )
    return summaries


def _topic_entry(topic_id: str, base: Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
    for entry in entries:
        if entry["topic_id"] == topic_id:
            return entry
    raise UnknownTopicError(topic_id, [entry["topic_id"] for entry in entries])


def topic_payload(
    topic_id: str,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict[str, Any]:
    """Return one JSON-ready topic payload for the web layer.

    The payload deliberately duplicates nothing that the client cannot get from
    the files: papers, claims (with stance counts and evidence ids), evidence
    (including method/sample), gaps, counts and provenance are all included.
    """

    base, _index, entries = _load_index(data_dir)
    entry = _topic_entry(topic_id, base, entries)
    corpus = load_corpus(_resolve_under(base, entry["corpus"]))
    evidence_map = load_map(
        _resolve_under(base, entry["extractions"]), corpus=corpus
    )

    claims_payload: list[dict[str, Any]] = []
    for claim in evidence_map.claims:
        related = [
            item for item in evidence_map.evidence if item.claim_id == claim.claim_id
        ]
        auto_related = [
            item
            for item in evidence_map.auto_evidence
            if item.claim_id == claim.claim_id
        ]
        counts = {stance: 0 for stance in STANCES}
        for item in related:
            counts[item.stance.value] += 1
        auto_counts = {stance: 0 for stance in STANCES}
        for item in auto_related:
            auto_counts[item.stance.value] += 1
        item = claim.to_dict()
        item["evidence_ids"] = [evidence.evidence_id for evidence in related]
        item["auto_evidence_ids"] = [
            evidence.evidence_id for evidence in auto_related
        ]
        item["stance_counts"] = counts
        item["auto_stance_counts"] = auto_counts
        claims_payload.append(item)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "topic": corpus.topic.to_dict(),
        "papers": [paper.to_dict() for paper in corpus.papers],
        "claims": claims_payload,
        "evidence": [item.to_dict() for item in evidence_map.evidence],
        "auto_evidence": [
            item.to_dict() for item in evidence_map.auto_evidence
        ],
        "gaps": [gap.to_dict() for gap in evidence_map.gaps],
        "counts": {
            "papers": len(corpus.papers),
            "claims": len(evidence_map.claims),
            "evidence": len(evidence_map.evidence),
            "auto_evidence": len(evidence_map.auto_evidence),
            "gaps": len(evidence_map.gaps),
            "stances": evidence_map.stance_counts(),
            "auto_stances": evidence_map.auto_stance_counts(),
        },
        "provenance": {
            "corpus": entry["corpus"],
            "extractions": entry["extractions"],
            "generated_at": corpus.generated_at,
            "extracted_at": evidence_map.extracted_at,
            "extractor": evidence_map.extractor,
            "corpus_source": corpus.source,
        },
    }

    verification_path = base / VERIFICATION_FILENAME
    if verification_path.exists():
        verification = read_json(verification_path)
        if isinstance(verification, MappingABC):
            payload["verification"] = {
                "checked_at": verification.get("checked_at", ""),
                "method": verification.get("method", ""),
                "summary": verification.get("summary", {}),
            }
    return payload


# ---------------------------------------------------------------------------
# Paper / claim / evidence graph projection (48h spike)
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read an optional audit CSV; a missing or malformed file is not fatal."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error, UnicodeError):
        return []


def _graph_aux_paths(base: Path) -> tuple[Path, Path]:
    """Return the merged audit CSV and the optional 105-cell key."""
    data_dir = base.parent
    repo_root = data_dir.parent
    merged = data_dir / "experiments" / "citemap_audit_105" / "merged.csv"
    # Keep the machine-cell key in data/, not dist/: dist/ is a build artifact,
    # so a clean checkout used to fall back to "no machine evidence".
    key = data_dir / "experiments" / "citemap_audit_105" / "key.csv"
    return merged, key


def _atomic_claims(base: Path, topic_id: str) -> list[dict[str, Any]]:
    path = base / "claims_atomic.json"
    if not path.is_file():
        return []
    data = read_json(path)
    if not isinstance(data, MappingABC):
        return []
    topics = data.get("topics")
    if not isinstance(topics, MappingABC):
        return []
    bucket = topics.get(topic_id)
    if not isinstance(bucket, MappingABC):
        return []
    claims = bucket.get("claims")
    if not isinstance(claims, list):
        return []
    return [dict(item) for item in claims if isinstance(item, MappingABC)]


def _aux_evidence(
    base: Path, dirname: str, topic_id: str
) -> list[dict[str, Any]]:
    path = base / dirname / f"{topic_id}.json"
    if not path.is_file():
        return []
    data = read_json(path)
    if not isinstance(data, MappingABC):
        return []
    records = data.get("evidence")
    if not isinstance(records, list):
        return []
    return [dict(item) for item in records if isinstance(item, MappingABC)]


def _evidence_level(record: Mapping[str, Any]) -> str:
    extractor = str(record.get("extracted_by") or record.get("extractor") or "")
    locator = str(record.get("locator") or "")
    if (
        record.get("fulltext_verdict")
        or "fulltext" in extractor.lower()
        or locator.lower().startswith("full text")
    ):
        return "fulltext"
    if "machine" in extractor.lower():
        return "machine"
    return "abstract"


def _stance(record: Mapping[str, Any]) -> str:
    value = str(record.get("stance") or "neutral")
    return value if value in STANCES else "neutral"


def _edge_kind(stance: str, level: str) -> str:
    if stance == "support":
        return "supports" if level == "fulltext" else "abstract_only"
    if stance == "contradict":
        return "contradicts" if level == "fulltext" else "abstract_only"
    return "abstract_only"


def _audit_index(base: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    merged_path, key_path = _graph_aux_paths(base)
    merged = {row.get("cell_id", ""): row for row in _read_csv(merged_path)}
    # The organizer key lives under dist/ (a build artifact).  A clean checkout
    # does not have it, so fall back to the committed merged grid, which carries
    # cell_kind/machine_stance as well.  Without this fallback every machine cell
    # becomes "none" only on CI, making the graph contract depend on local files.
    key_rows = _read_csv(key_path) if key_path.is_file() else list(merged.values())
    key = {row.get("cell_id", ""): row for row in key_rows}
    return merged, key


def _graph_cells(
    *,
    base: Path,
    topic_id: str,
    corpus: CorpusManifest,
    claims: list[Claim],
    fulltext: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the 105 parent cells and attach any fulltext/audit annotations."""
    merged, key = _audit_index(base)
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for record in fulltext:
        paper_id = str(record.get("paper_id") or "")
        claim_id = str(record.get("parent_claim_id") or record.get("claim_id") or "")
        cell_id = f"full-{topic_id}-{paper_id}-{claim_id}"
        by_cell.setdefault(cell_id, []).append(record)

    cells: list[dict[str, Any]] = []
    for paper in corpus.papers:
        for claim in claims:
            cell_id = f"full-{topic_id}-{paper.paper_id}-{claim.claim_id}"
            audit = merged.get(cell_id)
            key_row = key.get(cell_id)
            records = sorted(
                by_cell.get(cell_id, []),
                key=lambda item: str(item.get("evidence_id") or ""),
            )
            machine = bool(
                key_row
                and key_row.get("cell_kind") == "机器证据"
                and key_row.get("evidence_quote")
            )
            majority = audit.get("majority", "") if audit else ""
            if records:
                category = "fulltext"
            elif machine and majority == "correct":
                category = "abstract"
            else:
                category = "none"
            cells.append(
                {
                    "cell_id": cell_id,
                    "topic_id": topic_id,
                    "paper_id": paper.paper_id,
                    "claim_id": claim.claim_id,
                    "category": category,
                    "records": records,
                    "audit": audit or {},
                    "key": key_row or {},
                    "machine": machine,
                    "majority": majority,
                }
            )
    return cells


def _claim_node(claim: Claim, *, level: str, parent_id: str = "") -> dict[str, Any]:
    meta = claim.to_dict()
    meta.update(
        {
            "claim_level": level,
            "parent_claim_id": parent_id or claim.claim_id,
        }
    )
    return {
        "id": claim.claim_id,
        "type": "claim",
        "label": claim.text,
        "meta": meta,
    }


def _paper_node(paper: Paper) -> dict[str, Any]:
    meta = paper.to_dict()
    meta["paper_id"] = paper.paper_id
    return {
        "id": paper.paper_id,
        "type": "paper",
        "label": paper.title,
        "meta": meta,
    }


def _evidence_node(record: Mapping[str, Any], *, level: str) -> dict[str, Any]:
    evidence_id = str(record.get("evidence_id") or "")
    quote = str(record.get("quote") or "")
    summary = str(record.get("summary") or "")
    meta = {
        "evidence_id": evidence_id,
        "paper_id": str(record.get("paper_id") or ""),
        "claim_id": str(record.get("claim_id") or ""),
        "parent_claim_id": str(record.get("parent_claim_id") or ""),
        "atomic_id": str(record.get("atomic_id") or ""),
        "stance": _stance(record),
        "level": level,
        "summary": summary,
        "quote": quote,
        "locator": str(record.get("locator") or ""),
        "confidence": record.get("confidence", 0.5),
        "verified": bool(record.get("verified", False)),
        "source": str(
            record.get("extracted_by") or record.get("extractor") or "unknown"
        ),
        "fulltext_verdict": str(record.get("fulltext_verdict") or ""),
    }
    return {
        "id": evidence_id,
        "type": "evidence",
        "label": (summary or quote)[:300],
        "meta": meta,
    }


def _graph_edge(
    *,
    source: str,
    target: str,
    kind: str,
    level: str,
    evidence_id: str = "",
    quote: str = "",
    locator: str = "",
    meta: Mapping[str, Any] | None = None,
    index: int,
) -> dict[str, Any]:
    return {
        "id": f"e{index:04d}",
        "source": source,
        "target": target,
        "kind": kind,
        "level": level,
        "evidence_id": evidence_id,
        "quote": quote,
        "locator": locator,
        "page": "",
        "meta": dict(meta or {}),
    }


def _graph_from_aux(
    *,
    corpus: CorpusManifest,
    evidence_map: EvidenceMap,
    atomic: list[dict[str, Any]],
    fulltext_records: list[dict[str, Any]],
    atomic_records: list[dict[str, Any]],
    base: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Build the static-topic graph with 105 parent cells."""
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    def add(node: dict[str, Any]) -> None:
        if node["id"] not in node_ids:
            node_ids.add(node["id"])
            nodes.append(node)

    for paper in corpus.papers:
        add(_paper_node(paper))

    parent_claims = list(evidence_map.claims)
    for claim in parent_claims:
        add(_claim_node(claim, level="parent"))

    atomic_ids: set[str] = set()
    for item in atomic:
        atomic_id = str(item.get("atomic_id") or "")
        parent_id = str(item.get("parent_claim_id") or "")
        text = str(item.get("text") or "")
        if not atomic_id or not text:
            continue
        parent = next(
            (claim for claim in parent_claims if claim.claim_id == parent_id),
            None,
        )
        if parent is None:
            continue
        atomic_ids.add(atomic_id)
        add(
            {
                "id": atomic_id,
                "type": "claim",
                "label": text,
                "meta": {
                    "claim_id": atomic_id,
                    "atomic_id": atomic_id,
                    "parent_claim_id": parent_id,
                    "topic_id": corpus.topic.topic_id,
                    "claim_level": "atomic",
                    "source": "claims_atomic.json",
                },
            }
        )

    evidence_nodes: dict[str, dict[str, Any]] = {}

    def add_evidence(record: Mapping[str, Any], level: str) -> str:
        evidence_id = str(record.get("evidence_id") or "")
        if not evidence_id:
            return ""
        if evidence_id not in evidence_nodes:
            node = _evidence_node(record, level=level)
            evidence_nodes[evidence_id] = node
            add(node)
        return evidence_id

    edges: list[dict[str, Any]] = []
    edge_index = 1

    def add_edge(**kwargs: Any) -> None:
        nonlocal edge_index
        edges.append(_graph_edge(index=edge_index, **kwargs))
        edge_index += 1

    for record in sorted(
        fulltext_records + atomic_records,
        key=lambda item: str(item.get("evidence_id") or ""),
    ):
        level = _evidence_level(record)
        evidence_id = add_evidence(record, level)
        if not evidence_id:
            continue
        target = str(record.get("atomic_id") or "")
        if target not in atomic_ids:
            target = str(record.get("parent_claim_id") or record.get("claim_id") or "")
        if target not in node_ids:
            continue
        add_edge(
            source=str(record.get("paper_id") or ""),
            target=target,
            kind=_edge_kind(_stance(record), level),
            level=level,
            evidence_id=evidence_id,
            quote=str(record.get("quote") or ""),
            locator=str(record.get("locator") or ""),
            meta={
                "edge_scope": "evidence",
                "stance": _stance(record),
                "atomic_id": str(record.get("atomic_id") or ""),
                "parent_claim_id": str(record.get("parent_claim_id") or ""),
            },
        )

    cells = _graph_cells(
        base=base,
        topic_id=corpus.topic.topic_id,
        corpus=corpus,
        claims=parent_claims,
        fulltext=fulltext_records,
    )
    for cell in cells:
        paper_id = cell["paper_id"]
        claim_id = cell["claim_id"]
        category = cell["category"]
        records = cell["records"]
        audit = cell["audit"]
        key_row = cell["key"]
        meta = {
            "edge_scope": "cell",
            "cell_id": cell["cell_id"],
            "cell_kind": str(key_row.get("cell_kind") or ""),
            "audit_majority": cell["majority"],
            "audit_reviewers": {
                name: audit.get(name, "")
                for name in ("reviewer_1", "reviewer_2", "reviewer_3")
                if audit
            },
            "machine_stance": str(key_row.get("machine_stance") or ""),
            "machine_confidence": str(key_row.get("machine_confidence") or ""),
        }
        if category == "fulltext":
            best = sorted(
                records,
                key=lambda item: (
                    {"support": 0, "contradict": 1, "neutral": 2}.get(
                        _stance(item), 3
                    ),
                    str(item.get("evidence_id") or ""),
                ),
            )[0]
            meta["stance"] = _stance(best)
            evidence_id = add_evidence(best, "fulltext")
            add_edge(
                source=paper_id,
                target=claim_id,
                kind=_edge_kind(_stance(best), "fulltext"),
                level="fulltext",
                evidence_id=evidence_id,
                quote=str(best.get("quote") or ""),
                locator=str(best.get("locator") or ""),
                meta=meta,
            )
        elif category == "abstract":
            quote = str(key_row.get("evidence_quote") or "")
            stance = str(key_row.get("machine_stance") or "support")
            meta["stance"] = stance
            synthetic = {
                "evidence_id": f"machine-cell-{cell['cell_id']}",
                "paper_id": paper_id,
                "claim_id": claim_id,
                "parent_claim_id": claim_id,
                "atomic_id": "",
                "stance": stance,
                "summary": "105 格审计中机器证据经人工多数认定为 correct；仅有摘要片段。",
                "quote": quote,
                "locator": "摘要候选片段",
                "confidence": key_row.get("machine_confidence", ""),
                "verified": False,
                "extractor": "machine-cell:audit-correct",
                "fulltext_verdict": "",
            }
            evidence_id = add_evidence(synthetic, "abstract")
            add_edge(
                source=paper_id,
                target=claim_id,
                kind="abstract_only",
                level="abstract",
                evidence_id=evidence_id,
                quote=quote,
                locator="摘要候选片段",
                meta=meta,
            )
        else:
            add_edge(
                source=paper_id,
                target=claim_id,
                kind="none",
                level="machine",
                evidence_id="",
                quote="",
                locator="",
                meta=meta,
            )

    summary = _graph_summary(
        papers=len(corpus.papers),
        claim_nodes=[node for node in nodes if node["type"] == "claim"],
        evidence_nodes=[node for node in nodes if node["type"] == "evidence"],
        edges=edges,
        cells=cells,
        atomic_count=len(atomic_ids),
        parent_count=len(parent_claims),
    )
    return nodes, edges, summary


def _graph_summary(
    *,
    papers: int,
    claim_nodes: list[dict[str, Any]],
    evidence_nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    atomic_count: int,
    parent_count: int,
) -> dict[str, Any]:
    return {
        "papers": papers,
        "claims": len(claim_nodes),
        "parent_claims": parent_count,
        "atomic_claims": atomic_count,
        "evidence": len(evidence_nodes),
        "edges": len(edges),
        "fulltext_edges": sum(1 for edge in edges if edge["level"] == "fulltext"),
        "abstract_edges": sum(1 for edge in edges if edge["level"] == "abstract"),
        "machine_edges": sum(1 for edge in edges if edge["level"] == "machine"),
        "none_edges": sum(1 for edge in edges if edge["kind"] == "none"),
        "cells": len(cells),
        "cells_fulltext": sum(1 for cell in cells if cell["category"] == "fulltext"),
        "cells_abstract_only": sum(
            1 for cell in cells if cell["category"] == "abstract"
        ),
        "cells_none": sum(1 for cell in cells if cell["category"] == "none"),
    }


def _graph_from_base(
    *,
    topic: Topic,
    corpus: CorpusManifest,
    evidence_map: EvidenceMap,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Fallback for dynamic topics without the atomic/105-grid artefacts."""
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    def add(node: dict[str, Any]) -> None:
        if node["id"] not in node_ids:
            node_ids.add(node["id"])
            nodes.append(node)

    for paper in corpus.papers:
        add(_paper_node(paper))
    for claim in evidence_map.claims:
        add(_claim_node(claim, level="parent"))

    evidence_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for index, record in enumerate(evidence_map.evidence, start=1):
        level = _evidence_level(record.to_dict())
        node = _evidence_node(record.to_dict(), level=level)
        if not node["id"] or node["id"] in node_ids:
            continue
        add(node)
        evidence_nodes.append(node)
        edges.append(
            _graph_edge(
                index=index,
                source=record.paper_id,
                target=record.claim_id,
                kind=_edge_kind(record.stance.value, level),
                level=level,
                evidence_id=record.evidence_id,
                quote=record.quote,
                locator=record.locator,
                meta={"edge_scope": "evidence"},
            )
        )

    summary = {
        "papers": len(corpus.papers),
        "claims": len(evidence_map.claims),
        "parent_claims": len(evidence_map.claims),
        "atomic_claims": 0,
        "evidence": len(evidence_nodes),
        "edges": len(edges),
        "fulltext_edges": sum(1 for edge in edges if edge["level"] == "fulltext"),
        "abstract_edges": sum(1 for edge in edges if edge["level"] == "abstract"),
        "machine_edges": sum(1 for edge in edges if edge["level"] == "machine"),
        "none_edges": sum(1 for edge in edges if edge["kind"] == "none"),
        "cells": 0,
        "cells_fulltext": 0,
        "cells_abstract_only": 0,
        "cells_none": 0,
    }
    return nodes, edges, summary


def validate_graph(graph: Mapping[str, Any]) -> None:
    """Validate the graph contract, dangling references and summary counts."""
    if not isinstance(graph, MappingABC):
        raise EvidenceMapError("graph 顶层必须是对象")
    if graph.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceMapError(f"graph.schema_version 必须为 {SCHEMA_VERSION!r}")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    summary = graph.get("summary")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise EvidenceMapError("graph.nodes / graph.edges 必须是数组")
    if not isinstance(summary, MappingABC):
        raise EvidenceMapError("graph.summary 必须是对象")

    node_ids: list[str] = []
    node_types: dict[str, str] = {}
    for position, node in enumerate(nodes):
        if not isinstance(node, MappingABC):
            raise EvidenceMapError(f"nodes[{position}] 必须是对象")
        node_id = str(node.get("id") or "")
        node_type = str(node.get("type") or "")
        if not node_id or not isinstance(node.get("label"), str):
            raise EvidenceMapError(f"nodes[{position}] 缺少 id/label")
        if node_type not in GRAPH_NODE_TYPES:
            raise EvidenceMapError(f"nodes[{position}].type 非法：{node_type!r}")
        if not isinstance(node.get("meta"), MappingABC):
            raise EvidenceMapError(f"nodes[{position}].meta 必须是对象")
        node_ids.append(node_id)
        node_types[node_id] = node_type
    _fail_duplicates(node_ids, "graph node id")

    edge_ids: list[str] = []
    for position, edge in enumerate(edges):
        if not isinstance(edge, MappingABC):
            raise EvidenceMapError(f"edges[{position}] 必须是对象")
        edge_id = str(edge.get("id") or "")
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        kind = str(edge.get("kind") or "")
        level = str(edge.get("level") or "")
        evidence_id = str(edge.get("evidence_id") or "")
        quote = str(edge.get("quote") or "")
        if not edge_id:
            raise EvidenceMapError(f"edges[{position}] 缺少 id")
        if source not in node_types:
            raise EvidenceMapError(f"edges[{position}] source 悬空：{source!r}")
        if target not in node_types:
            raise EvidenceMapError(f"edges[{position}] target 悬空：{target!r}")
        if node_types[source] != "paper":
            raise EvidenceMapError(f"edges[{position}] source 必须是 paper")
        if node_types[target] != "claim":
            raise EvidenceMapError(f"edges[{position}] target 必须是 claim")
        if kind not in GRAPH_EDGE_KINDS:
            raise EvidenceMapError(f"edges[{position}].kind 非法：{kind!r}")
        if level not in GRAPH_LEVELS:
            raise EvidenceMapError(f"edges[{position}].level 非法：{level!r}")
        if kind == "none":
            if evidence_id or quote:
                raise EvidenceMapError(
                    f"edges[{position}] kind=none 不能带 evidence_id/quote"
                )
            if level != "machine":
                raise EvidenceMapError(
                    f"edges[{position}] kind=none 的 level 必须是 machine"
                )
        else:
            if not evidence_id:
                raise EvidenceMapError(f"edges[{position}] 缺少 evidence_id")
            if node_types.get(evidence_id) != "evidence":
                raise EvidenceMapError(
                    f"edges[{position}] evidence_id 未指向 evidence 节点"
                )
            if not quote:
                raise EvidenceMapError(f"edges[{position}] 有证据但缺少 quote")
        if level == "fulltext" and kind not in ("supports", "contradicts", "abstract_only"):
            raise EvidenceMapError(f"edges[{position}] fulltext 边 kind 非法")
        if level == "abstract" and kind != "abstract_only":
            raise EvidenceMapError(f"edges[{position}] abstract 边 kind 必须是 abstract_only")
        edge_ids.append(edge_id)
    _fail_duplicates(edge_ids, "graph edge id")

    claim_nodes = sum(1 for node in nodes if node["type"] == "claim")
    evidence_nodes = sum(1 for node in nodes if node["type"] == "evidence")
    expected = {
        "papers": sum(1 for node in nodes if node["type"] == "paper"),
        "claims": claim_nodes,
        "evidence": evidence_nodes,
        "edges": len(edges),
        "fulltext_edges": sum(1 for edge in edges if edge["level"] == "fulltext"),
        "abstract_edges": sum(1 for edge in edges if edge["level"] == "abstract"),
        "machine_edges": sum(1 for edge in edges if edge["level"] == "machine"),
        "none_edges": sum(1 for edge in edges if edge["kind"] == "none"),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise EvidenceMapError(
                f"graph.summary.{key}={summary.get(key)!r} 与节点/边计数 {value} 不一致"
            )


def build_graph(
    topic_id: str,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict[str, Any]:
    """Project one topic into a paper / claim / evidence graph.

    The static CiteMap topics use the 21 atomic claims and the 105-cell audit
    grid.  A parent claim edge is emitted for every one of the 105 cells; the
    24 fulltext and 9 abstract-only evidence records additionally produce
    atomic-claim edges.  Edges that lack fulltext are always ``abstract_only``
    (or ``none`` when the audit rejected the machine evidence); they are never
    promoted to ``fulltext``.
    """
    base = Path(data_dir).resolve()
    _base, _index, entries = _load_index(base)
    entry = _topic_entry(_topic_id(topic_id, "topic_id"), base, entries)
    corpus = load_corpus(_resolve_under(base, entry["corpus"]))
    evidence_map = load_map(
        _resolve_under(base, entry["extractions"]), corpus=corpus
    )
    atomic = _atomic_claims(base, topic_id)
    fulltext = _aux_evidence(base, "extractions_fulltext", topic_id)
    atomic_records = _aux_evidence(base, "extractions_atomic", topic_id)

    if atomic:
        nodes, edges, summary = _graph_from_aux(
            corpus=corpus,
            evidence_map=evidence_map,
            atomic=atomic,
            fulltext_records=fulltext,
            atomic_records=atomic_records,
            base=base,
        )
        provenance = {
            "corpus": entry["corpus"],
            "extractions": entry["extractions"],
            "claims_atomic": "claims_atomic.json",
            "extractions_fulltext": f"extractions_fulltext/{topic_id}.json",
            "extractions_atomic": f"extractions_atomic/{topic_id}.json",
            "audit_grid": "data/experiments/citemap_audit_105/merged.csv",
            "audit_key": "dist/citemap_audit_full/_organizer_only_key.csv",
        }
    else:
        nodes, edges, summary = _graph_from_base(
            topic=corpus.topic,
            corpus=corpus,
            evidence_map=evidence_map,
        )
        provenance = {
            "corpus": entry["corpus"],
            "extractions": entry["extractions"],
        }

    graph: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "topic": corpus.topic.to_dict(),
        "topic_id": topic_id,
        "generated_at": corpus.generated_at,
        "nodes": nodes,
        "edges": edges,
        "summary": summary,
        "provenance": provenance,
    }
    validate_graph(graph)
    return graph


def write_graph(
    topic_id: str,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path | None = None,
) -> Path:
    """Write one graph JSON under ``data/evidence_map/graph/`` by default."""
    graph = build_graph(topic_id, data_dir)
    base = Path(data_dir).resolve()
    target = Path(output_dir) if output_dir is not None else base / GRAPH_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{topic_id}.json"
    path.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m citeguard.evidence_map",
        description="CiteMap evidence-map schema checker",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"evidence-map data directory (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate every corpus/extraction file and print a summary (default behaviour)",
    )
    parser.add_argument(
        "--topic",
        metavar="TOPIC_ID",
        help="also print the full web payload for one topic",
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="write graph JSON for every topic under data/evidence_map/graph/",
    )
    parser.add_argument(
        "--graph-out",
        type=Path,
        default=None,
        help="output directory for --graph (default: <data-dir>/graph)",
    )
    args = parser.parse_args(argv)

    try:
        topics = list_topics(args.data_dir)
        result: dict[str, Any] = {
            "ok": True,
            "schema_version": SCHEMA_VERSION,
            "data_dir": str(args.data_dir),
            "topics": topics,
            "totals": {
                key: sum(topic[key] for topic in topics)
                for key in ("papers", "claims", "evidence", "gaps")
            },
        }
        if args.topic:
            result["payload"] = topic_payload(args.topic, args.data_dir)
        if args.graph:
            graphs: list[dict[str, Any]] = []
            for topic in topics:
                path = write_graph(
                    topic["topic_id"], args.data_dir, args.graph_out
                )
                graph = read_json(path)
                graphs.append(
                    {
                        "topic_id": topic["topic_id"],
                        "path": str(path),
                        "summary": graph["summary"],
                    }
                )
            result["graphs"] = graphs
    except EvidenceMapError as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
