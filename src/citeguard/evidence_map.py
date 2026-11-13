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

Public API
----------
``SCHEMA_VERSION``, ``DEFAULT_DATA_DIR``
``EvidenceMapError``, ``UnknownTopicError``
``parse_corpus`` / ``load_corpus`` / ``validate_corpus``
``parse_map`` / ``load_map`` / ``validate_map``
``list_topics`` / ``topic_payload``
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
    "main",
]

SCHEMA_VERSION = "1.0"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "evidence_map"

INDEX_FILENAME = "index.json"
VERIFICATION_FILENAME = "verification.json"
CORPUS_DIRNAME = "corpus"
EXTRACTIONS_DIRNAME = "extractions"

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
    gap_ids = [gap.gap_id for gap in evidence_map.gaps]

    _fail_duplicates(claim_ids, "claim_id")
    _fail_duplicates(evidence_ids, "evidence_id")
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
        for item in evidence_map.evidence:
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
                "gaps": len(evidence_map.gaps),
                "stances": evidence_map.stance_counts(),
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
        counts = {stance: 0 for stance in STANCES}
        for item in related:
            counts[item.stance.value] += 1
        item = claim.to_dict()
        item["evidence_ids"] = [evidence.evidence_id for evidence in related]
        item["stance_counts"] = counts
        claims_payload.append(item)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "topic": corpus.topic.to_dict(),
        "papers": [paper.to_dict() for paper in corpus.papers],
        "claims": claims_payload,
        "evidence": [item.to_dict() for item in evidence_map.evidence],
        "gaps": [gap.to_dict() for gap in evidence_map.gaps],
        "counts": {
            "papers": len(corpus.papers),
            "claims": len(evidence_map.claims),
            "evidence": len(evidence_map.evidence),
            "gaps": len(evidence_map.gaps),
            "stances": evidence_map.stance_counts(),
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
