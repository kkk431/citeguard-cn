"""CiteGuard Live 评测：两套 30 句数据 -> hit@3 / 延迟 / 四档标签分布。

评测对象是产品里的 ``check_claim(claim, page_url="", page_title="")``（见
``src/citeguard/live_check.py``），不启动 Web 服务、不经过浏览器扩展。

两套数据（不混算）
------------------
1. 跨语言集（默认，``pages.json`` + ``claims.jsonl``）：30 条真实中文引用句，
   句子出处是本地 ``data/real_corpus`` PDF；``page_id`` 是 Live 场景里打开的
   公开上下文页，页面的参考文献列表通常不含被引来源 —— 用于暴露跨语言检索
   的边界，hit@3 预期很低。
2. 公开页集（``pages_public.json`` + ``claims_public.jsonl``）：30 条英文正文
   句子确实出现在 5 篇 arXiv HTML 页面上，``[n]`` 标记与页面参考文献列表一一
   对应；用于检查「页面参考文献列表优先」路径在真实页面上的效果。

指标
----
- hit@1 / hit@3：模型给出的候选文献（按模块内部排序）前 1/前 3 中是否命中
  句子所引用的那篇文献；命中判定为 DOI 相同，或标题归一化后相等/高度相似。
- 延迟：单次 ``check_claim`` 墙钟耗时（含 OpenAlex/Crossref 检索）的 P50/P95。
- 标签分布：support / partial / contradict / no_evidence 四档计数。

边界
----
- 跨语言集不提供 stance 金标；标签分布是模型的输出分布，不是准确率。
- 公开页集只存句子、`[n]` 编号与页面元数据，不复制页面正文；句子长度 40–300
  字符，每页 6 条。两套数据的 hit@3 分母不同、任务难度不同，禁止混算。
- 结果只写 id、标签、候选数与延迟，不落盘摘要或候选全文。

用法
----
    python scripts/eval_live.py --check        # 只校验数据完整性
    PYTHONPATH=src python scripts/eval_live.py # 跑跨语言集，写 live_eval.json
    PYTHONPATH=src python scripts/eval_live.py \
        --claims data/live_eval/claims_public.jsonl \
        --pages data/live_eval/pages_public.json \
        --out data/live_eval/live_eval_public.json
    PYTHONPATH=src python scripts/eval_live.py --limit 5 --out /tmp/live_preview.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "live_eval"
DEFAULT_OUT = DEFAULT_DATA_DIR / "live_eval.json"

LABELS = ("support", "partial", "contradict", "no_evidence")
CJK_CLAIM_FIELDS = {"id", "sentence", "source_title", "source_doi", "page_id"}
PUBLIC_CLAIM_FIELDS = {
    "id",
    "sentence",
    "source_title",
    "source_doi",
    "page_url",
    "page_title",
    "reference_index",
}
PAGE_FIELDS = {"id", "url", "title", "fetched_at", "license"}
PUBLIC_PAGE_FIELDS = {"id", "url", "title", "fetched_at", "license", "source", "references"}
CLAIM_FIELDS = CJK_CLAIM_FIELDS  # 兼容旧引用（测试与外部脚本）
EXPECTED_PAGES = 5
EXPECTED_CLAIMS = 30
PUBLIC_PER_PAGE = 6
PUBLIC_SENTENCE_MIN = 40
PUBLIC_SENTENCE_MAX = 300
K = 3
TZ = timezone(timedelta(hours=8))

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
CITATION_MARKER_RE = re.compile(r"\[([0-9][0-9,\s\u2013-]*?)\]")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def load_pages(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    pages = raw.get("pages") if isinstance(raw, dict) else raw
    if not isinstance(pages, list):
        raise ValueError(f"{path} 缺少 pages 列表")
    return pages


def load_claims(path: Path) -> list[dict]:
    claims: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            claims.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno} 不是合法 JSON: {exc}") from exc
    return claims


def normalize_title(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", (text or "").lower())


def normalize_doi(text: str) -> str:
    match = DOI_RE.search(text or "")
    return match.group(0).lower() if match else ""


def title_matches(source_title: str, candidate_title: str) -> bool:
    left = normalize_title(source_title)
    right = normalize_title(candidate_title)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) >= 20 and shorter in longer:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.88


def candidate_matches(source_title: str, source_doi: str, candidate: dict) -> bool:
    if not isinstance(candidate, dict):
        return False
    doi = normalize_doi(str(candidate.get("doi") or ""))
    if source_doi and doi and doi == normalize_doi(source_doi):
        return True
    url = str(candidate.get("url") or "")
    if source_doi and normalize_doi(url) == normalize_doi(source_doi):
        return True
    return title_matches(source_title, str(candidate.get("title") or ""))


def first_hit_rank(source_title: str, source_doi: str, candidates: list) -> Optional[int]:
    for rank, candidate in enumerate(candidates, 1):
        if candidate_matches(source_title, source_doi, candidate):
            return rank
    return None


def percentile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    value = ordered[low] + (ordered[high] - ordered[low]) * (pos - low)
    return round(value, 1)


def _iso_ok(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def _marker_indexes(sentence: str) -> set[int]:
    """把 [2] / [186, 194] / [10–12] 解析成引用编号集合。"""
    indexes: set[int] = set()
    for raw in CITATION_MARKER_RE.findall(sentence or ""):
        for part in re.split(r",\s*", raw.strip()):
            if re.fullmatch(r"\d+", part):
                indexes.add(int(part))
                continue
            match = re.fullmatch(r"(\d+)\s*[\u2013-]\s*(\d+)", part)
            if match:
                indexes.update(range(int(match.group(1)), int(match.group(2)) + 1))
    return indexes


def dataset_profile(claims: list[dict]) -> str:
    """按字段形状识别数据集：crosslingual / public / unknown。"""
    if not claims:
        return "unknown"
    keys = [set(claim) for claim in claims if isinstance(claim, dict)]
    if keys and all(PUBLIC_CLAIM_FIELDS <= k for k in keys):
        return "public"
    if keys and all(CJK_CLAIM_FIELDS <= k for k in keys):
        return "crosslingual"
    return "unknown"


def validate(pages: list[dict], claims: list[dict]) -> list[str]:
    """校验评测数据（不依赖 live_check），返回错误列表；空列表表示通过。"""
    profile = dataset_profile(claims)
    if profile == "public":
        return _validate_public(pages, claims)
    if profile == "crosslingual":
        return _validate_crosslingual(pages, claims)
    errors: list[str] = []
    _validate_page_common(pages, errors)
    if len(claims) != EXPECTED_CLAIMS:
        errors.append(f"claims 应为 {EXPECTED_CLAIMS} 条，实际 {len(claims)}")
    errors.append("claims 字段形状既不是跨语言集也不是公开页集，无法识别数据集")
    return errors


def _validate_page_common(pages: list[dict], errors: list[str]) -> dict[str, dict]:
    if len(pages) != EXPECTED_PAGES:
        errors.append(f"pages 应为 {EXPECTED_PAGES} 个，实际 {len(pages)}")
    page_by_url: dict[str, dict] = {}
    page_ids: set[str] = set()
    for index, page in enumerate(pages, 1):
        if not isinstance(page, dict):
            errors.append(f"pages[{index}] 不是对象")
            continue
        pid = str(page.get("id") or "")
        if not pid:
            errors.append(f"pages[{index}] id 为空")
        elif pid in page_ids:
            errors.append(f"pages[{index}] id 重复: {pid}")
        page_ids.add(pid)
        url = str(page.get("url") or "")
        if url in page_by_url:
            errors.append(f"pages[{index}] url 重复: {url}")
        page_by_url[url] = page
        if not url.startswith(("http://", "https://")):
            errors.append(f"pages[{index}] url 不是 http(s): {url!r}")
        if not str(page.get("title") or "").strip():
            errors.append(f"pages[{index}] title 为空")
        if not _iso_ok(page.get("fetched_at")):
            errors.append(f"pages[{index}] fetched_at 不是 ISO 时间: {page.get('fetched_at')!r}")
        if not str(page.get("license") or "").strip():
            errors.append(f"pages[{index}] license 为空")
    return page_by_url


def _validate_claim_common(claim: dict, index: int, errors: list[str], seen: set[str]) -> str:
    cid = str(claim.get("id") or "")
    if not cid:
        errors.append(f"claims[{index}] id 为空")
    elif cid in seen:
        errors.append(f"claims[{index}] id 重复: {cid}")
    seen.add(cid)
    if not str(claim.get("source_title") or "").strip():
        errors.append(f"claims[{index}] source_title 为空")
    if not normalize_doi(str(claim.get("source_doi") or "")):
        errors.append(f"claims[{index}] source_doi 不是 DOI: {claim.get('source_doi')!r}")
    return cid


def _validate_crosslingual(pages: list[dict], claims: list[dict]) -> list[str]:
    errors: list[str] = []
    page_by_url = _validate_page_common(pages, errors)
    page_ids = {str(page.get("id")) for page in pages if isinstance(page, dict)}

    if len(claims) != EXPECTED_CLAIMS:
        errors.append(f"claims 应为 {EXPECTED_CLAIMS} 条，实际 {len(claims)}")
    seen: set[str] = set()
    used_pages: set[str] = set()
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            errors.append(f"claims[{index}] 不是对象")
            continue
        if set(claim) != CJK_CLAIM_FIELDS:
            errors.append(f"claims[{index}] 字段应恰为 {sorted(CJK_CLAIM_FIELDS)}，实际 {sorted(set(claim))}")
        _validate_claim_common(claim, index, errors, seen)
        sentence = str(claim.get("sentence") or "").strip()
        if len(sentence) < 10 or not CJK_RE.search(sentence):
            errors.append(f"claims[{index}] 句子过短或非中文: {sentence[:30]!r}")
        page_id = str(claim.get("page_id") or "")
        if page_id not in page_ids:
            errors.append(f"claims[{index}] page_id 不在 pages 中: {page_id!r}")
        else:
            used_pages.add(page_id)
    for pid in sorted(page_ids - used_pages):
        errors.append(f"页面未被任何 claim 使用: {pid}")
    if not page_by_url:
        errors.append("pages 为空")
    return errors


def _validate_public(pages: list[dict], claims: list[dict]) -> list[str]:
    errors: list[str] = []
    page_by_url = _validate_page_common(pages, errors)
    for index, page in enumerate(pages, 1):
        if not isinstance(page, dict):
            continue
        missing = PUBLIC_PAGE_FIELDS - set(page)
        if missing:
            errors.append(f"pages[{index}] 缺字段: {sorted(missing)}")
        references = page.get("references")
        if not isinstance(references, int) or references <= 0:
            errors.append(f"pages[{index}] references 应为正整数: {references!r}")

    if len(claims) != EXPECTED_CLAIMS:
        errors.append(f"claims 应为 {EXPECTED_CLAIMS} 条，实际 {len(claims)}")
    seen: set[str] = set()
    per_url: dict[str, int] = {}
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            errors.append(f"claims[{index}] 不是对象")
            continue
        if set(claim) != PUBLIC_CLAIM_FIELDS:
            errors.append(f"claims[{index}] 字段应恰为 {sorted(PUBLIC_CLAIM_FIELDS)}，实际 {sorted(set(claim))}")
        _validate_claim_common(claim, index, errors, seen)
        sentence = str(claim.get("sentence") or "").strip()
        if not PUBLIC_SENTENCE_MIN <= len(sentence) <= PUBLIC_SENTENCE_MAX:
            errors.append(f"claims[{index}] 长度 {len(sentence)} 不在 {PUBLIC_SENTENCE_MIN}–{PUBLIC_SENTENCE_MAX}: {sentence[:40]!r}")
        if CJK_RE.search(sentence):
            errors.append(f"claims[{index}] 公开页集句子应为英文: {sentence[:40]!r}")
        indexes = _marker_indexes(sentence)
        if not indexes:
            errors.append(f"claims[{index}] 缺少 [n] 引用标记: {sentence[:40]!r}")
        ref_index = claim.get("reference_index")
        if not isinstance(ref_index, int) or ref_index <= 0:
            errors.append(f"claims[{index}] reference_index 应为正整数: {ref_index!r}")
        elif indexes and ref_index not in indexes:
            errors.append(f"claims[{index}] reference_index {ref_index} 不在句子的引用标记 {sorted(indexes)} 中")
        page_url = str(claim.get("page_url") or "")
        page = page_by_url.get(page_url)
        if page is None:
            errors.append(f"claims[{index}] page_url 不在 pages 中: {page_url!r}")
        else:
            per_url[page_url] = per_url.get(page_url, 0) + 1
            if str(claim.get("page_title") or "").strip() != str(page.get("title") or "").strip():
                errors.append(f"claims[{index}] page_title 与 pages 不一致: {claim.get('page_title')!r}")
    for url, page in page_by_url.items():
        count = per_url.get(url, 0)
        if count != PUBLIC_PER_PAGE:
            errors.append(f"页面 {url} 应有 {PUBLIC_PER_PAGE} 条 claim，实际 {count}")
    return errors


def load_checker() -> tuple[Optional[Callable[..., dict]], str]:
    """导入产品的 check_claim；t9 未交付时返回清晰错误而不是堆栈。"""
    try:
        from citeguard.live_check import check_claim  # noqa: PLC0415 - 延迟导入便于 --check
    except ImportError:
        return None, "live_check 未交付，先 --check 数据"
    return check_claim, ""


def run(claims: list[dict], pages: list[dict], checker: Callable[..., dict], k: int = K) -> dict:
    page_by_id = {str(page["id"]): page for page in pages}
    page_by_url = {str(page.get("url") or ""): page for page in pages}
    records: list[dict] = []
    failures: list[dict] = []
    latencies: list[float] = []
    label_counts = {label: 0 for label in LABELS}

    for claim in claims:
        page = page_by_id.get(str(claim.get("page_id") or "")) or page_by_url.get(
            str(claim.get("page_url") or "")
        )
        if page is None:
            failures.append({"id": claim.get("id"), "error": "找不到 claim 对应的页面"})
            continue
        started = time.perf_counter()
        try:
            result = checker(
                str(claim["sentence"]),
                page_url=str(page.get("url") or ""),
                page_title=str(page.get("title") or ""),
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        except Exception as exc:  # noqa: BLE001 - 单条失败不中断整批
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            failures.append({"id": claim["id"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not isinstance(result, dict):
            failures.append({"id": claim["id"], "error": f"返回值不是 dict: {type(result).__name__}"})
            continue
        label = str(result.get("label") or "")
        if label not in LABELS:
            failures.append({"id": claim["id"], "error": f"非法 label: {label!r}"})
            continue
        candidates = result.get("candidates") or []
        if not isinstance(candidates, list):
            failures.append({"id": claim["id"], "error": "candidates 不是列表"})
            continue
        rank = first_hit_rank(str(claim["source_title"]), str(claim["source_doi"]), candidates)
        try:
            confidence = round(float(result.get("confidence") or 0.0), 3)
        except (TypeError, ValueError):
            confidence = 0.0
        latencies.append(elapsed_ms)
        label_counts[label] += 1
        record = {
            "id": claim["id"],
            "page_id": page.get("id"),
            "label": label,
            "confidence": confidence,
            "n_candidates": len(candidates),
            "hit@1": rank == 1,
            "hit@3": bool(rank and rank <= k),
            "first_hit_rank": rank,
            "latency_ms": elapsed_ms,
        }
        if "reference_index" in claim:
            record["reference_index"] = claim["reference_index"]
        records.append(record)

    n = len(claims)
    hit1 = sum(1 for r in records if r["hit@1"])
    hit3 = sum(1 for r in records if r["hit@3"])
    no_candidates = sum(1 for r in records if r["n_candidates"] == 0)
    result = {
        "generated_at": _now(),
        "dataset": dataset_profile(claims),
        "n": n,
        "n_pages": len(pages),
        "k": k,
        "hit@1": round(hit1 / n, 4) if n else None,
        "hit@3": round(hit3 / n, 4) if n else None,
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
        "mean_ms": round(statistics.fmean(latencies), 1) if latencies else None,
        "label_counts": label_counts,
        "n_failures": len(failures),
        "n_no_candidates": no_candidates,
        "failures": failures,
        "records": records,
    }
    return result


def _print_summary(result: dict) -> None:
    print(f"n={result['n']} pages={result['n_pages']} k={result['k']}")
    print(f"hit@1={result['hit@1']} hit@3={result['hit@3']}")
    print(f"latency p50={result['p50_ms']}ms p95={result['p95_ms']}ms mean={result['mean_ms']}ms")
    print(f"labels={result['label_counts']} failures={result['n_failures']} no_candidates={result['n_no_candidates']}")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CiteGuard Live 30 句评测（跨语言集 / 公开页集）")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--claims", type=Path, default=None, help="claims JSONL；默认 <data-dir>/claims.jsonl")
    parser.add_argument("--pages", type=Path, default=None, help="pages JSON；默认 <data-dir>/pages.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="只校验 pages/claims 完整性")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（预览用）")
    args = parser.parse_args(argv)

    pages_path = args.pages if args.pages else args.data_dir / "pages.json"
    claims_path = args.claims if args.claims else args.data_dir / "claims.jsonl"
    try:
        pages = load_pages(pages_path)
        claims = load_claims(claims_path)
    except (OSError, ValueError) as exc:
        print(f"数据读取失败: {exc}", file=sys.stderr)
        return 1

    profile = dataset_profile(claims)
    errors = validate(pages, claims)
    if args.check:
        if errors:
            print("数据校验失败:")
            for error in errors:
                print(f"- {error}")
            return 1
        label = "公开页集" if profile == "public" else "跨语言集"
        print(f"OK: {len(pages)} 个页面 / {len(claims)} 条引用句（{label}），来源字段齐全")
        return 0
    if errors:
        print("数据校验失败（先修数据）:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    checker, message = load_checker()
    if checker is None:
        print(message, file=sys.stderr)
        return 2

    if args.limit > 0:
        claims = claims[: args.limit]
    result = run(claims, pages, checker)
    result["data"] = {"pages": _rel(pages_path), "claims": _rel(claims_path)}
    result["checker"] = "citeguard.live_check.check_claim"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_summary(result)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
