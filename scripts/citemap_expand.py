"""Semi-automatic CiteMap expansion: candidates first, human confirmation later.

This script never writes the human evidence layer unless the caller explicitly
promotes a candidate that a human marked as accepted.  Generated candidates are
always ``machine=true`` / ``needs_human=true`` and use a separate output area
(``data/evidence_map/expansion/``).

The extraction strategy is intentionally conservative and offline-first:

* For an existing topic, candidate claims are the paper's own abstract result
  sentence.  The sentence is selected only when it carries an explicit result
  cue; the exact sentence is the quote.  This avoids pretending that a lexical
  matcher can translate a Chinese claim into an English abstract; the human
  reviewer decides whether the proposed claim/evidence pair belongs in the topic.
* A DOI/query mode uses OpenAlex metadata and abstract text, but still produces
  only candidates.

Run ``python scripts/citemap_expand.py --topic ai_education`` from the repo root.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from citeguard import citemap_builder  # noqa: E402
from citeguard import citemap_verify  # noqa: E402
from citeguard import evidence_map  # noqa: E402

SCHEMA_VERSION = "1.0"
DEFAULT_TOPIC = "ai_education"
DEFAULT_EXPERIMENT = Path("data/experiments/opt_e3_citemap_expand_2026-11-27.json")
MIN_CANDIDATES = 5
MAX_CANDIDATES = 100
DECISIONS = ("accept", "reject")


class ExpandError(ValueError):
    """Raised when expansion input or a candidate is not usable."""


def _norm(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _candidate_id(topic_id: str, index: int) -> str:
    return f"cand-{topic_id}-{index:03d}"


def _claim_id(topic_id: str, index: int) -> str:
    return f"exp-{topic_id}-c{index:03d}"


def _evidence_id(topic_id: str, index: int) -> str:
    return f"exp-{topic_id}-e{index:03d}"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExpandError(f"无法读取 {path}：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise ExpandError(f"{path} 不是合法 JSON：{exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _abstract_index(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Map paper_id -> abstract record from the local abstracts cache."""
    path = data_dir / "abstracts.json"
    if not path.exists():
        return {}
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ExpandError("abstracts.json 必须是对象")
    out: dict[str, dict[str, Any]] = {}
    for key, record in raw.items():
        if not isinstance(record, dict):
            continue
        paper_id = str(record.get("paper_id") or "").strip()
        if paper_id:
            out[paper_id] = {**record, "_openalex_key": str(key)}
    return out


def _paper_view(paper: evidence_map.Paper) -> dict[str, Any]:
    return {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "url": paper.url,
        "license": paper.license,
        "fulltext_available": paper.fulltext_available,
    }


RESULT_CUES = (
    "findings", "results show", "results suggest", "results indicate",
    "results revealed", "we find", "we show", "our results", "we conclude",
    "conclusion", "concluded", "significantly", "associated with", "improved",
    "increased", "decreased", "higher", "lower", "outperform", "accuracy",
    "effective", "effect", "suggest that", "indicate that",
)
_METHOD_CUES = (
    "this study examines", "this study is centered", "this study investigates",
    "this study aims", "the research seeks", "we collected", "data was collected",
    "this paper describes", "this review examines", "employing",
)
# A claim needs an actual result signal.  Without one, a sentence such as
# "The emergence of online education..." is merely background, and presenting it
# as a candidate claim would waste human review time.
_STRONG_RESULT_CUES = (
    "results show", "results showed", "results indicate", "results suggest",
    "results revealed", "results demonstrate", "findings show", "findings suggest",
    "findings indicate", "findings revealed", "finding suggests", "finding indicates",
    "we find", "we found", "we show", "we showed", "our results",
    "results of this study", "showed that", "shows that", "show that",
    "indicate that", "indicates that", "suggests that", "suggest that", "suggests that",
    "revealed that", "demonstrated that", "in conclusion", "we conclude", "concluded that",
    "significantly", "outperform", "accuracy",
)
_SECTION_PREFIX_RE = re.compile(
    r"^(?:(?:abstract|background|objectives?|methods?|materials? and methods?|"
    r"results? and conclusions?|conclusions?|discussion)"
    r"\b[\s:：.\-–—]*)",
    re.IGNORECASE,
)


def _clean_sentence(text: str) -> str:
    """Remove section labels such as ``Results and Conclusions``."""
    cleaned = _norm(text)
    for _ in range(3):
        match = _SECTION_PREFIX_RE.match(cleaned)
        if not match or match.end() == 0:
            break
        cleaned = _norm(cleaned[match.end():])
    return cleaned


def _result_sentence(abstract: str) -> str:
    """Pick a result-bearing abstract sentence, or return "".

    ``citemap_builder._best_sentence`` is the shared baseline, but it can return
    a background/method sentence.  For a human-review queue, a weak candidate is
    worse than no candidate, so this function requires an explicit result cue.
    It never rewrites text beyond stripping a leading section label.
    """
    sentences = citemap_verify.split_sentences(abstract, min_len=60, max_sentences=80)
    if not sentences:
        return ""
    scored: list[tuple[int, int, str]] = []
    for raw_sentence in sentences:
        sentence = _clean_sentence(raw_sentence)
        if len(sentence) < 60:
            continue
        lowered = sentence.lower()
        if not any(cue in lowered for cue in _STRONG_RESULT_CUES):
            continue
        cues = sum(3 for cue in RESULT_CUES if cue in lowered)
        methods = sum(2 for cue in _METHOD_CUES if cue in lowered)
        # A result sentence should be substantive but not a whole paragraph.
        length = 1 if 80 <= len(sentence) <= 460 else 0
        scored.append((cues - methods, length, sentence))
    if not scored:
        return ""
    scored.sort(key=lambda item: (item[0], item[1], len(item[2])), reverse=True)
    best = scored[0]
    if best[0] <= 0:
        return ""
    return best[2]


def _candidate_from_sentence(
    *,
    topic_id: str,
    index: int,
    paper: evidence_map.Paper,
    abstract: str,
    sentence: str,
    source: str,
    candidate_type: str = "new_claim",
    claim_id: str | None = None,
    claim_text: str | None = None,
    parent_claim_id: str = "",
    candidate_id: str | None = None,
    stance: str = "support",
    confidence: float = 0.35,
    notes: str = "",
) -> dict[str, Any]:
    text = _clean_sentence(sentence)
    if len(text) < 60:
        raise ExpandError("候选句过短，无法作为候选")
    if len(text) > 1200:
        raise ExpandError("候选句过长，无法作为候选")
    source_text = _norm(abstract)
    if text not in source_text:
        # _result_sentence works on collapsed whitespace; a mismatch means the
        # quote is not verbatim and must not be emitted.
        raise ExpandError("候选句不是摘要原文，拒绝生成")
    proposed_claim = _norm(claim_text) if claim_text else text
    if not proposed_claim:
        raise ExpandError("候选 claim 不能为空")
    return {
        "candidate_id": candidate_id or _candidate_id(topic_id, index),
        "candidate_type": candidate_type,
        "topic_id": topic_id,
        "claim_id": claim_id or _claim_id(topic_id, index),
        "parent_claim_id": parent_claim_id,
        "claim": proposed_claim,
        "quote": text,
        "locator": "Abstract",
        "quote_lang": "en",
        "stance": stance,
        "confidence": confidence,
        "machine": True,
        "needs_human": True,
        "status": "pending",
        "source": source,
        "source_kind": "abstract",
        "source_title": paper.title,
        "source_url": paper.url,
        "paper": _paper_view(paper),
        "source_text": source_text,
        "notes": notes or "机器候选：摘要结果句直接作为 proposed claim，未人审；不当作人工证据。",
    }


def _existing_quotes(evidence_map_obj: evidence_map.EvidenceMap) -> set[str]:
    return {
        _norm(item.quote)
        for item in (*evidence_map_obj.evidence, *evidence_map_obj.auto_evidence)
        if item.quote
    }


def _existing_claim_texts(evidence_map_obj: evidence_map.EvidenceMap) -> set[str]:
    return {_norm(claim.text) for claim in evidence_map_obj.claims}


def generate_candidates(
    topic_id: str = DEFAULT_TOPIC,
    *,
    data_dir: str | Path | None = None,
    limit: int = MAX_CANDIDATES,
    min_candidates: int = MIN_CANDIDATES,
    works: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate machine candidates without touching the human layer.

    ``works`` is an optional list of OpenAlex work dictionaries for query/DOI
    mode.  Without it, the existing topic corpus and ``abstracts.json`` are used
    (offline; no network dependency).
    """
    topic_id = (topic_id or "").strip()
    if not topic_id:
        raise ExpandError("topic 不能为空")
    data_root = Path(data_dir) if data_dir is not None else evidence_map.DEFAULT_DATA_DIR
    limit = max(1, min(int(limit), MAX_CANDIDATES))
    if works is not None:
        return _generate_from_works(topic_id, works, limit=limit, min_candidates=min_candidates)

    corpus_path = data_root / evidence_map.CORPUS_DIRNAME / f"{topic_id}.json"
    map_path = data_root / evidence_map.EXTRACTIONS_DIRNAME / f"{topic_id}.json"
    if not corpus_path.exists() or not map_path.exists():
        raise ExpandError(f"找不到主题 {topic_id!r} 的 corpus/extractions")
    corpus = evidence_map.load_corpus(corpus_path)
    evidence_map_obj = evidence_map.load_map(map_path, corpus=corpus)
    abstracts = _abstract_index(data_root)
    existing_quotes = _existing_quotes(evidence_map_obj)
    existing_claims = _existing_claim_texts(evidence_map_obj)
    seen_quotes: set[str] = set()
    candidates: list[dict[str, Any]] = []
    skipped = {"no_abstract": 0, "duplicate": 0, "no_sentence": 0}

    for paper in corpus.papers:
        if len(candidates) >= limit:
            break
        record = abstracts.get(paper.paper_id) or {}
        abstract = str(record.get("abstract") or "")
        if not abstract:
            skipped["no_abstract"] += 1
            continue
        sentence = _result_sentence(abstract)
        if not sentence:
            skipped["no_sentence"] += 1
            continue
        normalized = _norm(sentence)
        if normalized in existing_quotes or normalized in existing_claims:
            # The same sentence is already human evidence or an existing claim.
            skipped["duplicate"] += 1
            continue
        if normalized in seen_quotes:
            skipped["duplicate"] += 1
            continue
        seen_quotes.add(normalized)
        try:
            candidate = _candidate_from_sentence(
                topic_id=topic_id,
                index=len(candidates) + 1,
                paper=paper,
                abstract=abstract,
                sentence=sentence,
                source="existing-topic-abstract",
            )
        except ExpandError:
            skipped["invalid_sentence"] = skipped.get("invalid_sentence", 0) + 1
            continue
        candidates.append(candidate)

    if len(candidates) < min_candidates:
        raise ExpandError(
            f"主题 {topic_id!r} 仅生成 {len(candidates)} 条候选，少于 {min_candidates} 条；"
            "请检查 abstracts.json 或放宽 min_candidates"
        )
    return _bundle(topic_id, corpus.topic.to_dict(), candidates, skipped=skipped, mode="existing-topic")


def _generate_from_works(
    topic_id: str,
    works: Iterable[dict[str, Any]],
    *,
    limit: int,
    min_candidates: int,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped = {"no_abstract": 0, "duplicate": 0}
    for work in works:
        if len(candidates) >= limit:
            break
        abstract = citemap_builder._abstract(work)
        sentence = _result_sentence(abstract)
        paper = citemap_builder._work_to_paper(work, topic_id, len(candidates) + 1)
        if paper is None or not abstract or not sentence:
            skipped["no_abstract"] += 1
            continue
        normalized = _norm(sentence)
        if normalized in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(normalized)
        paper_obj = evidence_map.Paper.from_dict(paper)
        try:
            candidate = _candidate_from_sentence(
                topic_id=topic_id,
                index=len(candidates) + 1,
                paper=paper_obj,
                abstract=abstract,
                sentence=sentence,
                source="openalex-abstract",
            )
        except ExpandError:
            skipped["invalid_sentence"] = skipped.get("invalid_sentence", 0) + 1
            continue
        candidates.append(candidate)
    if len(candidates) < min_candidates:
        raise ExpandError(
            f"仅生成 {len(candidates)} 条候选，少于 {min_candidates} 条；"
            "请扩大 query/DOI 列表或稍后重试"
        )
    topic = {
        "topic_id": topic_id,
        "name_zh": topic_id,
        "name_en": topic_id,
        "question": "",
        "description": "半自动扩展候选；机器候选，未人审。",
    }
    return _bundle(topic_id, topic, candidates, skipped=skipped, mode="external")


def _bundle(
    topic_id: str,
    topic: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    skipped: dict[str, int],
    mode: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "topic_id": topic_id,
        "topic": topic,
        "generated_at": date.today().isoformat(),
        "mode": mode,
        "method": "候选 claim=摘要结果句；quote=同一句逐字摘要；stance 仅为机器提议；未人审。",
        "boundaries": [
            "machine=true / needs_human=true；候选不是证据",
            "未写入 evidence / auto_evidence 人工层",
            "不能据此宣称准确率；需人工逐条确认 claim、quote、locator 与 stance",
        ],
        "counts": {
            "candidates": len(candidates),
            "pending": len(candidates),
            "skipped": skipped,
        },
        "candidates": candidates,
    }


def write_outputs(
    bundle: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> dict[str, str]:
    """Write candidate JSON, blank review CSV, and an experiment summary."""
    topic_id = str(bundle.get("topic_id") or "")
    if not topic_id:
        raise ExpandError("bundle 缺少 topic_id")
    out = Path(output_dir) if output_dir is not None else evidence_map.DEFAULT_DATA_DIR / "expansion"
    out.mkdir(parents=True, exist_ok=True)
    candidates_path = out / f"{topic_id}_candidates.json"
    review_path = out / f"{topic_id}_review.csv"
    _write_json(candidates_path, bundle)

    fields = [
        "candidate_id", "topic_id", "claim_id", "claim", "paper_id", "doi",
        "source", "quote", "locator", "stance", "confidence", "machine",
        "needs_human", "decision", "note", "reviewer",
    ]
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate in bundle.get("candidates") or []:
            paper = candidate.get("paper") or {}
            writer.writerow(
                {
                    "candidate_id": candidate.get("candidate_id", ""),
                    "topic_id": candidate.get("topic_id", ""),
                    "claim_id": candidate.get("claim_id", ""),
                    "claim": candidate.get("claim", ""),
                    "paper_id": paper.get("paper_id", ""),
                    "doi": paper.get("doi", ""),
                    "source": candidate.get("source", ""),
                    "quote": candidate.get("quote", ""),
                    "locator": candidate.get("locator", ""),
                    "stance": candidate.get("stance", ""),
                    "confidence": candidate.get("confidence", ""),
                    "machine": candidate.get("machine", ""),
                    "needs_human": candidate.get("needs_human", ""),
                    "decision": "",
                    "note": "",
                    "reviewer": "",
                }
            )
    result = {
        "topic_id": topic_id,
        "candidates": str(candidates_path),
        "review_csv": str(review_path),
    }
    if summary_path is not None:
        summary_path = Path(summary_path)
        summary = _experiment_summary(bundle, candidates_path, review_path)
        _write_json(summary_path, summary)
        result["summary"] = str(summary_path)
    return result


def _experiment_summary(
    bundle: dict[str, Any], candidates_path: Path, review_path: Path
) -> dict[str, Any]:
    candidates = list(bundle.get("candidates") or [])
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": "opt_e3_citemap_expand_2026-11-27",
        "generated_at": bundle.get("generated_at"),
        "topic_id": bundle.get("topic_id"),
        "mode": bundle.get("mode"),
        "candidate_count": len(candidates),
        "candidate_ids": [item.get("candidate_id") for item in candidates],
        "claims": [item.get("claim_id") for item in candidates],
        "papers": sorted({str((item.get("paper") or {}).get("paper_id") or "") for item in candidates}),
        "sources": sorted({str(item.get("source") or "") for item in candidates}),
        "machine": all(bool(item.get("machine")) for item in candidates),
        "needs_human": all(bool(item.get("needs_human")) for item in candidates),
        "human_layer_written": False,
        "candidates_path": str(candidates_path),
        "review_csv": str(review_path),
        "boundaries": bundle.get("boundaries") or [],
        "skipped": (bundle.get("counts") or {}).get("skipped") or {},
    }


def validate_candidate(candidate: dict[str, Any], *, data_dir: str | Path | None = None) -> None:
    """Validate a candidate before promotion.  Raises :class:`ExpandError`."""
    if not isinstance(candidate, dict):
        raise ExpandError("candidate 必须是对象")
    for field in ("candidate_id", "topic_id", "claim_id", "claim", "quote", "locator", "stance"):
        if not str(candidate.get(field) or "").strip():
            raise ExpandError(f"candidate 缺少字段 {field}")
    if candidate.get("machine") is not True or candidate.get("needs_human") is not True:
        raise ExpandError("candidate 必须是 machine=true、needs_human=true")
    if candidate.get("status") not in {"pending", "accepted"}:
        raise ExpandError("candidate.status 必须是 pending/accepted")
    if candidate.get("stance") not in evidence_map.STANCES:
        raise ExpandError(f"candidate.stance 非法：{candidate.get('stance')!r}")
    quote = _norm(str(candidate.get("quote") or ""))
    if not quote:
        raise ExpandError("candidate.quote 不能为空")
    source_text = _norm(str(candidate.get("source_text") or ""))
    if source_text and quote not in source_text:
        raise ExpandError("candidate.quote 不是来源摘要的逐字片段")
    paper = candidate.get("paper") or {}
    if not str(paper.get("paper_id") or "").strip():
        raise ExpandError("candidate.paper.paper_id 不能为空")
    if data_dir is not None:
        root = Path(data_dir)
        corpus_path = root / evidence_map.CORPUS_DIRNAME / f"{candidate['topic_id']}.json"
        if not corpus_path.exists():
            raise ExpandError(f"找不到主题 {candidate['topic_id']!r} 的 corpus")
        corpus = evidence_map.load_corpus(corpus_path)
        paper_ids = {item.paper_id for item in corpus.papers}
        if paper["paper_id"] not in paper_ids:
            raise ExpandError(
                "候选论文不在该主题 corpus 中；请先把论文加入 corpus 再 promote"
            )


@dataclass
class Promotion:
    patch: dict[str, Any]
    accepted: bool
    written: bool = False
    path: Path | None = None
    skipped_reason: str = ""


def _load_topic(data_dir: Path, topic_id: str) -> tuple[evidence_map.CorpusManifest, dict[str, Any]]:
    corpus_path = data_dir / evidence_map.CORPUS_DIRNAME / f"{topic_id}.json"
    map_path = data_dir / evidence_map.EXTRACTIONS_DIRNAME / f"{topic_id}.json"
    corpus = evidence_map.load_corpus(corpus_path)
    raw = _read_json(map_path)
    evidence_map.load_map(map_path, corpus=corpus)
    return corpus, raw


def promote_candidate(
    candidate: dict[str, Any],
    *,
    decision: str,
    note: str = "",
    reviewer: str = "",
    data_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    write_human_layer: bool = False,
) -> Promotion:
    """Validate a human decision and build an evidence patch.

    ``write_human_layer`` defaults to False: promotion produces a patch under
    ``expansion/promotions/`` but does not modify the canonical extraction.  A
    caller that has explicit human confirmation can pass True to append the
    validated claim/evidence to ``extractions/<topic>.json``.
    """
    choice = (decision or "").strip().lower()
    if choice not in DECISIONS:
        raise ExpandError("decision 必须是 accept 或 reject")
    root = Path(data_dir) if data_dir is not None else evidence_map.DEFAULT_DATA_DIR
    validate_candidate(candidate, data_dir=root)
    if choice == "reject":
        return Promotion(patch={"candidate_id": candidate["candidate_id"], "decision": choice}, accepted=False)

    topic_id = str(candidate["topic_id"])
    corpus, raw = _load_topic(root, topic_id)
    paper = next(
        (item for item in corpus.papers if item.paper_id == candidate["paper"]["paper_id"]),
        None,
    )
    if paper is None:
        raise ExpandError("候选论文不在 corpus 中")
    if _norm(str(candidate["paper"].get("doi") or "")) != _norm(paper.doi):
        raise ExpandError("候选论文 DOI 与 corpus 不一致")

    claims = list(raw.get("claims") or [])
    evidence = list(raw.get("evidence") or [])
    claim_ids = {str(item.get("claim_id")) for item in claims}
    claim_id = str(candidate["claim_id"])
    new_claim = claim_id not in claim_ids
    claim_text = _norm(str(candidate["claim"]))
    existing_claim = next((item for item in claims if str(item.get("claim_id")) == claim_id), None)
    if existing_claim is not None and _norm(str(existing_claim.get("text") or "")) != claim_text:
        raise ExpandError("候选 claim_id 已存在但文本不同，拒绝覆盖")
    if not new_claim:
        raise ExpandError("候选 claim 已存在；本 spike 只 promote 新 claim 候选")

    claim = {
        "claim_id": claim_id,
        "topic_id": topic_id,
        "text": claim_text,
        "population": "",
        "outcome": "",
        "direction": "",
        "notes": f"人工确认机器候选 {candidate['candidate_id']}；reviewer={reviewer or '未署名'}",
    }
    used_evidence_ids = {str(item.get("evidence_id")) for item in evidence}
    next_index = len(evidence) + 1
    evidence_id = _evidence_id(topic_id, next_index)
    while evidence_id in used_evidence_ids:
        next_index += 1
        evidence_id = _evidence_id(topic_id, next_index)
    summary = _norm(f"人工确认：{paper.title} 的摘要结果句")
    evidence_record = {
        "evidence_id": evidence_id,
        "claim_id": claim_id,
        "paper_id": paper.paper_id,
        "stance": candidate["stance"],
        "summary": summary[:2000],
        "quote": _norm(str(candidate["quote"])),
        "quote_lang": str(candidate.get("quote_lang") or "en"),
        "locator": str(candidate.get("locator") or "Abstract"),
        "confidence": float(candidate.get("confidence") or 0.5),
        "extracted_by": "human:promoted-candidate",
        "verified": True,
        "notes": (
            f"由机器候选 {candidate['candidate_id']} 人工确认后 promote；"
            f"reviewer={reviewer or '未署名'}；note={note or '无'}"
        )[:3000],
    }
    # Validate the records through the canonical schema before writing anything.
    evidence_map.Claim.from_dict(claim)
    evidence_map.Evidence.from_dict(evidence_record)
    patched = {
        **raw,
        "claims": claims + [claim],
        "evidence": evidence + [evidence_record],
    }
    evidence_map.EvidenceMap.from_dict(patched)
    evidence_map.validate_map(evidence_map.EvidenceMap.from_dict(patched), corpus=corpus)

    patch = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate["candidate_id"],
        "topic_id": topic_id,
        "decision": choice,
        "reviewer": reviewer,
        "note": note,
        "promoted_at": date.today().isoformat(),
        "claim": claim,
        "evidence": evidence_record,
        "human_layer_written": False,
        "boundaries": ["只有 accept 才产生 patch；patch 仍需应用/审计后才进入人工层"],
    }
    out = Path(output_dir) if output_dir is not None else root / "expansion" / "promotions"
    out.mkdir(parents=True, exist_ok=True)
    patch_path = out / f"{candidate['candidate_id']}.json"
    if write_human_layer:
        map_path = root / evidence_map.EXTRACTIONS_DIRNAME / f"{topic_id}.json"
        _write_json(map_path, patched)
        patch["human_layer_written"] = True
        patch["human_layer_path"] = str(map_path)
    _write_json(patch_path, patch)
    return Promotion(patch=patch, accepted=True, written=bool(write_human_layer), path=patch_path)


def _external_works(*, query: str, dois: list[str], limit: int) -> list[dict[str, Any]]:
    try:
        if dois:
            return citemap_builder.lookup_dois(dois)
        return citemap_builder.search_works(query, limit=max(limit * 2, 10))
    except RuntimeError as exc:
        raise ExpandError(str(exc)) from exc


def _load_candidate_file(path: Path, candidate_id: str) -> dict[str, Any]:
    raw = _read_json(path)
    for candidate in raw.get("candidates") or []:
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    raise ExpandError(f"未找到候选 {candidate_id}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CiteMap 半自动扩展：候选 + 人工确认")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="主题 id（默认 ai_education）")
    parser.add_argument("--data-dir", default=None, help="evidence_map 数据根目录")
    parser.add_argument("--limit", type=int, default=MAX_CANDIDATES)
    parser.add_argument("--min-candidates", type=int, default=MIN_CANDIDATES)
    parser.add_argument("--query", default="", help="OpenAlex 检索查询；联网模式")
    parser.add_argument("--doi", action="append", default=[], help="候选论文 DOI；可重复")
    parser.add_argument("--output-dir", default=None, help="候选/CSV 输出目录")
    parser.add_argument("--summary", default=None, help="实验摘要 JSON 路径")
    parser.add_argument("--promote", metavar="CANDIDATE_ID", default="")
    parser.add_argument("--decision", default="", choices=("", *DECISIONS))
    parser.add_argument("--note", default="")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--write-human-layer", action="store_true")
    parser.add_argument("--candidates-file", default="", help="promote 时读取的候选 JSON")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        data_dir = Path(args.data_dir) if args.data_dir else evidence_map.DEFAULT_DATA_DIR
        if args.promote:
            candidates_file = Path(args.candidates_file) if args.candidates_file else (
                Path(args.output_dir) if args.output_dir else data_dir / "expansion"
            ) / f"{args.topic}_candidates.json"
            candidate = _load_candidate_file(candidates_file, args.promote)
            promotion = promote_candidate(
                candidate,
                decision=args.decision,
                note=args.note,
                reviewer=args.reviewer,
                data_dir=data_dir,
                output_dir=args.output_dir,
                write_human_layer=args.write_human_layer,
            )
            print(json.dumps(promotion.patch, ensure_ascii=False, indent=2))
            return 0
        if args.query or args.doi:
            works = _external_works(query=args.query, dois=args.doi, limit=args.limit)
            bundle = generate_candidates(
                args.topic, data_dir=data_dir, limit=args.limit,
                min_candidates=args.min_candidates, works=works,
            )
        else:
            bundle = generate_candidates(
                args.topic, data_dir=data_dir, limit=args.limit,
                min_candidates=args.min_candidates,
            )
        result = write_outputs(
            bundle,
            output_dir=args.output_dir,
            summary_path=args.summary,
        )
        payload = {
            "ok": True,
            "topic_id": bundle["topic_id"],
            "mode": bundle["mode"],
            "candidate_count": bundle["counts"]["candidates"],
            **result,
            "counts": bundle["counts"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except (ExpandError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
