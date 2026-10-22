"""Build ClaimSupport-CN: 100 constructed Chinese citation-support probes.

Construction (labels are a property of the construction, never of a model):

* support (40)    : claim = a core abstract sentence; evidence = the abstract
                    fragment containing it (the cited paper's own sentence(s));
* partial (25)    : claim = the full core sentence; evidence = only the *first
                    half* (first clause) of it, so the evidence supports part of
                    the claim but not all of it;
* contradict (15) : claim = the same sentence with one assertion flipped to its
                    antonym (提高→降低 etc.); evidence = the original sentence;
* no_evidence (20): claim = a core sentence of paper B; evidence = sentence(s) of
                    an unrelated paper A (low title/fragment similarity, A≠B).

Only CC0 OpenAlex metadata is used.  The dataset stores the claim, a short
evidence fragment, and source IDs — never full abstracts.  The per-work source
cache stores at most two sentence fragments per work so the build is repeatable
offline; it contains no full abstract either.

Usage:
    PYTHONPATH=src python3 scripts/build_claimsupport.py [--seed 20261022] [--refresh]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_DIR = ROOT / "data" / "claimsupport_cn"
DATA_DIR.mkdir(parents=True, exist_ok=True)

JSONL_PATH = DATA_DIR / "claimsupport_cn.jsonl"
META_PATH = DATA_DIR / "claimsupport_cn.meta.json"
SOURCE_CACHE = DATA_DIR / "claimsupport_cn.sources.json"
SPOT_CHECK_PATH = DATA_DIR / "claimsupport_cn.spot_check.json"

OPENALEX_URL = "https://api.openalex.org/works"
OPENALEX_FILTER = "language:zh,has_abstract:true,type:article"
OPENALEX_SELECT = (
    "id,doi,title,publication_year,abstract_inverted_index,type,primary_location"
)
MAILTO = os.environ.get("CITEGUARD_MAILTO", "citeguard@example.org")
USER_AGENT = os.environ.get(
    "CITEGUARD_USER_AGENT",
    "CiteGuard-CN/0.1 (ClaimSupport-CN builder; research prototype)",
)

SEED_DEFAULT = 20261022
N_SUPPORT = 40
N_PARTIAL = 25
N_CONTRADICT = 15
N_NO_EVIDENCE = 20
N_TOTAL = N_SUPPORT + N_PARTIAL + N_CONTRADICT + N_NO_EVIDENCE  # 100
TARGET_UNITS = 180  # source works with a usable core sentence
MAX_PAGES = 12
PER_PAGE = 200

CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
CJK_SPACE_CLASS = "\u4e00-\u9fff，。、；：！？（）“”‘’《》【】"
SENTENCE_END = ("。", "！", "？", "；", "!", "?", ";")

# Longest phrases first: single-pass replacement on the first match.
ANTONYM_PAIRS = [
    ("显著提高", "显著降低"), ("显著增加", "显著减少"), ("显著升高", "显著降低"),
    ("显著下降", "显著上升"), ("正相关", "负相关"), ("负相关", "正相关"),
    ("提高", "降低"), ("降低", "提高"), ("增加", "减少"), ("减少", "增加"),
    ("上升", "下降"), ("下降", "上升"), ("升高", "降低"), ("增长", "减少"),
    ("促进", "抑制"), ("抑制", "促进"), ("增强", "削弱"), ("削弱", "增强"),
    ("改善", "恶化"), ("恶化", "改善"), ("有效", "无效"), ("可行", "不可行"),
    ("优于", "劣于"), ("有助于", "不利于"), ("扩大", "缩小"), ("缩小", "扩大"),
    ("提升", "降低"), ("延长", "缩短"), ("加快", "减慢"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    """Rebuild abstract text from the OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for word, indexes in inverted_index.items():
        for i in indexes or []:
            positions[int(i)] = word
    if not positions:
        return ""
    return " ".join(positions[i] for i in sorted(positions))


def clean_text(text: str) -> str:
    """NFKC, drop spaces between CJK characters (OpenAlex joins tokens by space)."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00a0", " ")
    pattern = rf"(?<=[{CJK_SPACE_CLASS}])\s+(?=[{CJK_SPACE_CLASS}])"
    previous = None
    while previous != text:
        previous = text
        text = re.sub(pattern, "", text)
    text = re.sub(r"[ \t]+", " ", text)
    # OpenAlex's automatic Chinese translations mix ASCII and full-width
    # punctuation; normalise clause punctuation next to CJK to full-width.
    text = re.sub(r"[ \t]*,[ \t]*(?=[\u4e00-\u9fff])", "，", text)
    text = re.sub(r"[ \t]*;[ \t]*(?=[\u4e00-\u9fff])", "；", text)
    text = re.sub(r"[ \t]*:[ \t]*(?=[\u4e00-\u9fff])", "：", text)
    return text.strip()


def cjk_ratio(text: str) -> float:
    cjk = len(CJK.findall(text))
    latin = len(LATIN.findall(text))
    return cjk / (cjk + latin) if cjk + latin else 0.0


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])", text)
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not part.endswith(SENTENCE_END):
            part += "。"
        out.append(part)
    return out


STRUCTURED_PREFIX = re.compile(
    r"^\s*(?:目的|方法|结果|结论|背景|意义|对象与方法|资料与方法|材料与方法|方法学|"
    r"Objective|Methods?|Results?|Conclusions?)\s*[:：]\s*"
)
ASSERTION_WORDS = (
    "表明", "显示", "发现", "是", "为", "提高", "降低", "增加", "减少", "促进",
    "抑制", "导致", "影响", "具有", "成为", "实现", "需要", "建议", "证明", "说明",
    "认为", "提出", "存在", "包括", "构成", "提供", "支持", "改善", "有助于", "显著",
)
BACKGROUND_STARTS = ("随着", "在", "对于", "基于", "通过", "为了", "从", "自", "当", "由于", "近年")


def normalize_sentence(sentence: str) -> str:
    """Clean one sentence and strip structured-abstract labels (目的/方法/…)."""
    sentence = clean_text(sentence)
    sentence = STRUCTURED_PREFIX.sub("", sentence).strip()
    if not sentence:
        return ""
    if not sentence.endswith(SENTENCE_END):
        sentence += "。"
    return sentence


def sentence_ok(sentence: str) -> bool:
    if not sentence or not (20 <= len(sentence) <= 140):
        return False
    if len(CJK.findall(sentence)) < 12:
        return False
    if cjk_ratio(sentence) < 0.75:
        return False
    if re.search(r"[\[\]{}<>]|https?://|\ufffd", sentence):
        return False
    return True


def find_antonym(sentence: str) -> Optional[tuple[str, str]]:
    """First assertion-flip candidate, skipping negated clauses."""
    for negative in ("没有", "并未", "未", "尚未", "不能"):
        if negative in sentence:
            return None
    for word, antonym in ANTONYM_PAIRS:
        if word in sentence:
            return word, antonym
    return None


def partial_clause(sentence: str) -> Optional[str]:
    """Pick the clause that carries the main assertion (used as the partial evidence).

    A partial item keeps the full sentence as the claim, but the evidence is only
    this one clause, so the evidence supports part of the claim.  Background
    fragments ("随着…", "在…") are not used as evidence.
    """
    if not sentence:
        return None
    clauses = [c.strip() for c in re.split(r"[，,；;]", sentence) if c.strip()]
    if len(clauses) < 2:
        return None
    best: Optional[str] = None
    best_score = -1
    for clause in clauses:
        clause = clause.strip().rstrip("。！？!?；;，,、")
        if len(CJK.findall(clause)) < 10:
            continue
        if clause.startswith(BACKGROUND_STARTS):
            continue
        assertion_hits = sum(1 for word in ASSERTION_WORDS if word in clause)
        if assertion_hits == 0:
            continue
        score = assertion_hits * 10 + min(len(clause), 40)
        if score > best_score:
            best_score = score
            best = clause
    return best


def char_similarity(a: str, b: str) -> float:
    """Deterministic normalised-Levenshtein similarity (pure Python)."""
    def norm(text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "").lower()
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)

    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            current[j] = min(
                previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (0 if ca == cb else 1)
            )
        previous = current
    return 1.0 - previous[-1] / max(len(a), len(b))


def bigram_jaccard(a: str, b: str) -> float:
    """CJK character-bigram Jaccard (topic overlap measure for no_evidence pairs)."""
    def bigrams(text: str) -> set[str]:
        chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
        return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}

    left, right = bigrams(a), bigrams(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


# ---------------------------------------------------------------------------
# OpenAlex source units
# ---------------------------------------------------------------------------

def _fetch_page(page: int) -> Optional[dict]:
    params = {
        "filter": OPENALEX_FILTER,
        "per-page": PER_PAGE,
        "page": page,
        "select": OPENALEX_SELECT,
        "mailto": MAILTO,
    }
    last_error = ""
    for attempt in range(3):
        try:
            resp = requests.get(
                OPENALEX_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=60
            )
            if resp.status_code == 200:
                return resp.json()
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1.5 * (attempt + 1))
    print(f"  [warn] OpenAlex page {page} failed: {last_error}")
    return None


def normalize_unit(raw: dict) -> Optional[dict]:
    """Turn one OpenAlex work into a small fragment-only source unit."""
    abstract = clean_text(reconstruct_abstract(raw.get("abstract_inverted_index")))
    if not abstract or cjk_ratio(abstract) < 0.6:
        return None
    sentences = [normalize_sentence(s) for s in split_sentences(abstract)]
    sentences = [s for s in sentences if sentence_ok(s)]
    if not sentences:
        return None
    # Prefer the first valid sentence (usually the core statement of the abstract).
    primary = sentences[0]
    unit_sentences = [primary]
    # Keep one more sentence as optional context (fragment only, max 2 per work).
    for sentence in sentences[1:]:
        if sentence != primary:
            unit_sentences.append(sentence)
            break
    title = clean_text(raw.get("title") or "")
    doi = (raw.get("doi") or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    return {
        "id": (raw.get("id") or "").strip(),
        "title": title,
        "year": raw.get("publication_year"),
        "doi": doi,
        "sentences": unit_sentences,
    }


def _save_sources(units: list[dict], pages_fetched: int) -> None:
    SOURCE_CACHE.write_text(
        json.dumps(
            {
                "meta": {
                    "provider": "OpenAlex",
                    "license": "CC0 1.0 (metadata)",
                    "api": OPENALEX_URL,
                    "filter": OPENALEX_FILTER,
                    "select": OPENALEX_SELECT,
                    "mailto": MAILTO,
                    "pages_fetched": pages_fetched,
                    "fetched_at": _utc_now(),
                    "note": "Fragment-only cache: at most two abstract sentences per work, "
                            "no full abstract is stored.",
                },
                "units": units,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def load_or_fetch_sources(refresh: bool = False, target: int = TARGET_UNITS) -> tuple[list[dict], dict]:
    cached: dict[str, Any] = {}
    if SOURCE_CACHE.exists() and not refresh:
        try:
            cached = json.loads(SOURCE_CACHE.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[warn] could not read {SOURCE_CACHE.name}: {exc}")
            cached = {}
    units: list[dict] = list(cached.get("units") or []) if isinstance(cached, dict) else []
    # Idempotently re-normalise fragments read from an older cache: OpenAlex's
    # automatic translations mix ASCII/full-width punctuation between runs.
    for unit in units:
        unit["sentences"] = [
            s for s in (normalize_sentence(x) for x in (unit.get("sentences") or [])) if sentence_ok(s)
        ]
    units = [u for u in units if u.get("sentences")]
    seen = {u.get("id") for u in units if u.get("id")}
    pages_fetched = int((cached.get("meta") or {}).get("pages_fetched") or 0) if units else 0
    page = pages_fetched + 1
    print(f"[sources] cached units={len(units)} next_page={page}")

    def counts() -> tuple[int, int, int]:
        partial = sum(1 for u in units if partial_clause(u["sentences"][0]))
        contradict = sum(1 for u in units if find_antonym(u["sentences"][0]))
        return len(units), partial, contradict

    while page <= MAX_PAGES:
        total, partial, contradict = counts()
        if total >= target and partial >= N_PARTIAL + 8 and contradict >= N_CONTRADICT + 5:
            break
        payload = _fetch_page(page)
        if not payload:
            break
        added = 0
        for raw in payload.get("results") or []:
            unit = normalize_unit(raw)
            if not unit or unit["id"] in seen:
                continue
            # De-duplicate by primary sentence text as well (translated abstracts repeat).
            if any(u["sentences"][0] == unit["sentences"][0] for u in units):
                continue
            seen.add(unit["id"])
            units.append(unit)
            added += 1
        pages_fetched = page
        _save_sources(units, pages_fetched)
        total, partial, contradict = counts()
        print(f"[sources] page {page}: +{added} units, total={total}, "
              f"partial-capable={partial}, contradict-capable={contradict}")
        page += 1
    total, partial, contradict = counts()
    return units, {
        "pages_fetched": pages_fetched,
        "units": total,
        "partial_capable": partial,
        "contradict_capable": contradict,
    }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def _source_ref(unit: dict) -> dict:
    return {
        "openalex_id": unit["id"],
        "title": unit["title"],
        "doi": unit["doi"],
        "year": unit["year"],
    }


def build_items(units: list[dict], rng: random.Random) -> list[dict]:
    plain = [u for u in units if u["sentences"]]
    partial_pool = [u for u in units if partial_clause(u["sentences"][0])]
    contradict_pool = [u for u in units if find_antonym(u["sentences"][0])]

    if len(plain) < N_SUPPORT + N_PARTIAL + N_CONTRADICT + 2 * N_NO_EVIDENCE:
        raise RuntimeError(
            f"not enough source units: {len(plain)} < "
            f"{N_SUPPORT + N_PARTIAL + N_CONTRADICT + 2 * N_NO_EVIDENCE}"
        )
    if len(partial_pool) < N_PARTIAL:
        raise RuntimeError(f"not enough partial-capable units: {len(partial_pool)} < {N_PARTIAL}")
    if len(contradict_pool) < N_CONTRADICT:
        raise RuntimeError(
            f"not enough contradict-capable units: {len(contradict_pool)} < {N_CONTRADICT}"
        )

    rng.shuffle(plain)
    rng.shuffle(partial_pool)
    rng.shuffle(contradict_pool)

    # Keep works disjoint across roles so every item has its own base paper.
    used: set[str] = set()

    def take(pool: list[dict], role: str, index: int) -> dict:
        for unit in pool:
            if unit["id"] not in used:
                used.add(unit["id"])
                return unit
        raise RuntimeError(f"source pool exhausted while building {role}[{index}]")

    items: list[dict] = []

    # --- support -----------------------------------------------------------
    for i in range(N_SUPPORT):
        unit = take(plain, "support", i)
        sentences = unit["sentences"]
        claim = sentences[0]
        evidence = sentences[0] + (sentences[1] if len(sentences) > 1 else "")
        items.append(
            {
                "id": "",
                "claim": claim,
                "evidence": evidence,
                "label": "support",
                "construction": "support:core_sentence",
                "claim_source": _source_ref(unit),
                "evidence_source": _source_ref(unit),
            }
        )

    # --- partial -----------------------------------------------------------
    for i in range(N_PARTIAL):
        unit = take(partial_pool, "partial", i)
        sentence = unit["sentences"][0]
        clause = partial_clause(sentence)
        if not clause:
            raise RuntimeError(f"partial clause missing for {unit['id']}")
        evidence = clause + "。"
        items.append(
            {
                "id": "",
                "claim": sentence,
                "evidence": evidence,
                "label": "partial",
                "construction": "partial:evidence_is_one_assertion_clause",
                "claim_source": _source_ref(unit),
                "evidence_source": _source_ref(unit),
            }
        )

    # --- contradict --------------------------------------------------------
    for i in range(N_CONTRADICT):
        unit = take(contradict_pool, "contradict", i)
        sentence = unit["sentences"][0]
        pair = find_antonym(sentence)
        if not pair:
            raise RuntimeError(f"antonym pair missing for {unit['id']}")
        word, antonym = pair
        claim = sentence.replace(word, antonym, 1)
        items.append(
            {
                "id": "",
                "claim": claim,
                "evidence": sentence,
                "label": "contradict",
                "construction": f"contradict:antonym {word}->{antonym}",
                "claim_source": _source_ref(unit),
                "evidence_source": _source_ref(unit),
            }
        )

    # --- no_evidence -------------------------------------------------------
    # claim paper B + evidence paper A, A != B, unrelated titles/fragments.
    candidates = [u for u in plain if u["id"] not in used]
    for i in range(N_NO_EVIDENCE):
        claim_unit = candidates.pop(0)
        used.add(claim_unit["id"])
        claim = claim_unit["sentences"][0]
        evidence_unit = None
        for unit in candidates:
            if unit["id"] == claim_unit["id"]:
                continue
            if char_similarity(claim_unit["title"], unit["title"]) >= 0.22:
                continue
            if char_similarity(claim, unit["sentences"][0]) >= 0.22:
                continue
            if bigram_jaccard(claim, unit["sentences"][0]) >= 0.06:
                continue
            evidence_unit = unit
            break
        if evidence_unit is None:
            raise RuntimeError(f"no unrelated evidence paper for {claim_unit['id']}")
        candidates.remove(evidence_unit)
        used.add(evidence_unit["id"])
        evidence = evidence_unit["sentences"][0] + (
            evidence_unit["sentences"][1] if len(evidence_unit["sentences"]) > 1 else ""
        )
        items.append(
            {
                "id": "",
                "claim": claim,
                "evidence": evidence,
                "label": "no_evidence",
                "construction": "no_evidence:cross_paper_disjoint_topic",
                "claim_source": _source_ref(claim_unit),
                "evidence_source": _source_ref(evidence_unit),
            }
        )

    if len(items) != N_TOTAL:
        raise RuntimeError(f"expected {N_TOTAL} items, built {len(items)}")
    rng.shuffle(items)
    for index, item in enumerate(items, 1):
        item["id"] = f"cs-{index:04d}"
    return items


# ---------------------------------------------------------------------------
# Self-check / spot check
# ---------------------------------------------------------------------------

def check_item(item: dict) -> list[str]:
    """Re-verify that the item matches its construction rule."""
    problems: list[str] = []
    label = item["label"]
    claim, evidence = item["claim"], item["evidence"]
    if not claim or not evidence:
        problems.append("empty claim/evidence")
        return problems
    if label == "support":
        if claim not in evidence:
            problems.append("support: claim is not contained in evidence")
    elif label == "partial":
        clause = partial_clause(claim)
        if not clause:
            problems.append("partial: claim has no assertion clause")
        elif evidence.rstrip("。") != clause:
            problems.append("partial: evidence is not one assertion clause of the claim")
        if claim == evidence:
            problems.append("partial: claim equals evidence")
    elif label == "contradict":
        matched = False
        for word, antonym in ANTONYM_PAIRS:
            idx = evidence.find(word)
            if idx >= 0 and evidence[:idx] + antonym + evidence[idx + len(word):] == claim:
                matched = True
                break
        if not matched:
            problems.append("contradict: cannot recover the original sentence from claim")
        if claim == evidence:
            problems.append("contradict: claim equals evidence")
    elif label == "no_evidence":
        if item["claim_source"]["openalex_id"] == item["evidence_source"]["openalex_id"]:
            problems.append("no_evidence: same source paper")
        if char_similarity(item["claim_source"]["title"], item["evidence_source"]["title"]) >= 0.22:
            problems.append("no_evidence: source titles too similar")
        if bigram_jaccard(claim, evidence) >= 0.06:
            problems.append("no_evidence: claim/evidence topic overlap too high")
        if claim in evidence:
            problems.append("no_evidence: claim is contained in evidence")
    else:
        problems.append(f"unknown label {label}")
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    argp = argparse.ArgumentParser(description="Build the ClaimSupport-CN evaluation set.")
    argp.add_argument("--seed", type=int, default=SEED_DEFAULT, help="random seed")
    argp.add_argument("--refresh", action="store_true", help="refetch the OpenAlex source units")
    argp.add_argument("--target-units", type=int, default=TARGET_UNITS)
    args = argp.parse_args(argv)

    rng = random.Random(args.seed)
    units, source_stats = load_or_fetch_sources(refresh=args.refresh, target=args.target_units)
    print(f"[sources] usable units: {source_stats['units']} "
          f"(partial-capable={source_stats['partial_capable']}, "
          f"contradict-capable={source_stats['contradict_capable']})")

    items = build_items(units, rng)

    # Full construction self-check.
    failures = 0
    for item in items:
        problems = check_item(item)
        if problems:
            failures += 1
            print(f"[self-check] {item['id']} {item['label']}: {problems}")
    if failures:
        print(f"[fatal] {failures} items failed the construction self-check", file=sys.stderr)
        return 2

    JSONL_PATH.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
        encoding="utf-8",
        newline="\n",
    )

    import hashlib

    dataset_sha = hashlib.sha256(JSONL_PATH.read_bytes()).hexdigest()

    # 20 % spot check: re-run the construction rule checker on a deterministic sample.
    spot_rng = random.Random(args.seed + 1)
    spot_sample = spot_rng.sample(items, 20)
    spot_rows = []
    spot_failures = 0
    for item in spot_sample:
        problems = check_item(item)
        if problems:
            spot_failures += 1
        spot_rows.append(
            {
                "id": item["id"],
                "label": item["label"],
                "construction": item["construction"],
                "rule_checks": problems or ["ok"],
            }
        )
    SPOT_CHECK_PATH.write_text(
        json.dumps(
            {
                "note": "20% (20/100) construction-rule recheck after building; "
                        "single-annotator review, NOT double annotation and no kappa.",
                "seed": args.seed + 1,
                "sampled": len(spot_rows),
                "failures": spot_failures,
                "items": spot_rows,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    counts: dict[str, int] = {}
    construction_counts: dict[str, int] = {}
    for item in items:
        counts[item["label"]] = counts.get(item["label"], 0) + 1
        construction_counts[item["construction"]] = construction_counts.get(item["construction"], 0) + 1

    meta = {
        "dataset": "ClaimSupport-CN",
        "version": 1,
        "built_at": _utc_now(),
        "seed": args.seed,
        "n": len(items),
        "counts": counts,
        "construction_counts": construction_counts,
        "labels": {
            "support": "claim = a core abstract sentence; evidence = the abstract fragment that contains it",
            "partial": "claim = full core sentence; evidence = only one assertion clause of it, "
                       "so the evidence supports part of the claim",
            "contradict": "claim = the sentence with one assertion flipped to its antonym; "
                          "evidence = the original sentence",
            "no_evidence": "claim = core sentence of paper B; evidence = sentence(s) of a different, "
                           "unrelated paper A",
        },
        "labeling_note": "Labels are fully determined by the construction rules above; "
                         "there is NO human double annotation and NO kappa. "
                         "A 20% (20/100) construction-rule re-check is recorded in "
                         f"{SPOT_CHECK_PATH.name} (single-annotator review).",
        "source": {
            "provider": "OpenAlex",
            "license": "CC0 1.0 (metadata)",
            "api": OPENALEX_URL,
            "filter": OPENALEX_FILTER,
            "select": OPENALEX_SELECT,
            "mailto": MAILTO,
            "note": "Claim/evidence are short Chinese fragments derived from OpenAlex "
                    "Chinese-language abstracts (some abstracts are OpenAlex automatic "
                    "translations). Full abstracts are not re-hosted.",
        },
        "source_stats": source_stats,
        "spot_check": {"sampled": len(spot_rows), "failures": spot_failures},
        "dataset_sha256": dataset_sha,
        "files": {"jsonl": JSONL_PATH.name, "sources": SOURCE_CACHE.name,
                  "spot_check": SPOT_CHECK_PATH.name},
        "build_cmd": "PYTHONPATH=src python3 scripts/build_claimsupport.py",
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[done] wrote {len(items)} items -> {JSONL_PATH}")
    print(f"[done] labels: {counts}")
    print(f"[done] constructions: {construction_counts}")
    print(f"[done] dataset SHA-256: {dataset_sha}")
    print(f"[done] spot check: {len(spot_rows)} sampled, {spot_failures} failures -> {SPOT_CHECK_PATH}")
    print(f"[done] metadata -> {META_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
