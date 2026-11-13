"""CiteGuard Live 评测：30 条真实中文引用句 -> hit@3 / 延迟 / 四档标签分布。

评测对象是产品里的 ``check_claim(claim, page_url="", page_title="")``（见
``src/citeguard/live_check.py``），不启动 Web 服务、不经过浏览器扩展。

指标
----
- hit@1 / hit@3：模型给出的候选文献（按模块内部排序）前 1/前 3 中是否命中
  句子所引用的那篇文献；命中判定为 DOI 相同，或标题归一化后相等/高度相似。
- 延迟：单次 ``check_claim`` 墙钟耗时（含 OpenAlex/Crossref 检索）的 P50/P95。
- 标签分布：support / partial / contradict / no_evidence 四档计数。

边界
----
- 30 句来自 ``data/real_corpus`` 的真实正文（不是模板造句），句子的出处是本地
  PDF；``page_id`` 指向 Live 场景里打开的公开页面（上下文页），不是句子出处。
- 本集不提供 stance 金标；标签分布是模型的输出分布，不是准确率。四档意图的
  覆盖方式见 ``docs/live_eval.md``。
- 结果只写 id、标签、候选数与延迟，不落盘摘要或候选全文。

用法
----
    python scripts/eval_live.py --check        # 只校验数据完整性
    PYTHONPATH=src python scripts/eval_live.py # 跑 30 句，写 data/live_eval/live_eval.json
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
CLAIM_FIELDS = {"id", "sentence", "source_title", "source_doi", "page_id"}
PAGE_FIELDS = {"id", "url", "title", "fetched_at", "license"}
EXPECTED_PAGES = 5
EXPECTED_CLAIMS = 30
K = 3
TZ = timezone(timedelta(hours=8))

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
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


def validate(pages: list[dict], claims: list[dict]) -> list[str]:
    """校验评测数据（不依赖 live_check），返回错误列表；空列表表示通过。"""
    errors: list[str] = []
    if len(pages) != EXPECTED_PAGES:
        errors.append(f"pages 应为 {EXPECTED_PAGES} 个，实际 {len(pages)}")
    page_ids: set[str] = set()
    for index, page in enumerate(pages, 1):
        if not isinstance(page, dict):
            errors.append(f"pages[{index}] 不是对象")
            continue
        missing = PAGE_FIELDS - set(page)
        if missing:
            errors.append(f"pages[{index}] 缺字段: {sorted(missing)}")
        pid = str(page.get("id") or "")
        if not pid:
            errors.append(f"pages[{index}] id 为空")
        elif pid in page_ids:
            errors.append(f"pages[{index}] id 重复: {pid}")
        page_ids.add(pid)
        url = str(page.get("url") or "")
        if not url.startswith(("http://", "https://")):
            errors.append(f"pages[{index}] url 不是 http(s): {url!r}")
        if not str(page.get("title") or "").strip():
            errors.append(f"pages[{index}] title 为空")
        if not _iso_ok(page.get("fetched_at")):
            errors.append(f"pages[{index}] fetched_at 不是 ISO 时间: {page.get('fetched_at')!r}")
        if not str(page.get("license") or "").strip():
            errors.append(f"pages[{index}] license 为空")

    if len(claims) != EXPECTED_CLAIMS:
        errors.append(f"claims 应为 {EXPECTED_CLAIMS} 条，实际 {len(claims)}")
    claim_ids: set[str] = set()
    used_pages: set[str] = set()
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            errors.append(f"claims[{index}] 不是对象")
            continue
        fields = set(claim)
        if fields != CLAIM_FIELDS:
            errors.append(f"claims[{index}] 字段应恰为 {sorted(CLAIM_FIELDS)}，实际 {sorted(fields)}")
        cid = str(claim.get("id") or "")
        if not cid:
            errors.append(f"claims[{index}] id 为空")
        elif cid in claim_ids:
            errors.append(f"claims[{index}] id 重复: {cid}")
        claim_ids.add(cid)
        sentence = str(claim.get("sentence") or "").strip()
        if len(sentence) < 10 or not CJK_RE.search(sentence):
            errors.append(f"claims[{index}] 句子过短或非中文: {sentence[:30]!r}")
        if not str(claim.get("source_title") or "").strip():
            errors.append(f"claims[{index}] source_title 为空")
        if not normalize_doi(str(claim.get("source_doi") or "")):
            errors.append(f"claims[{index}] source_doi 不是 DOI: {claim.get('source_doi')!r}")
        page_id = str(claim.get("page_id") or "")
        if page_id not in page_ids:
            errors.append(f"claims[{index}] page_id 不在 pages 中: {page_id!r}")
        else:
            used_pages.add(page_id)
    for pid in sorted(page_ids - used_pages):
        errors.append(f"页面未被任何 claim 使用: {pid}")
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
    records: list[dict] = []
    failures: list[dict] = []
    latencies: list[float] = []
    label_counts = {label: 0 for label in LABELS}

    for claim in claims:
        page = page_by_id[str(claim["page_id"])]
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
        records.append(
            {
                "id": claim["id"],
                "page_id": claim["page_id"],
                "label": label,
                "confidence": confidence,
                "n_candidates": len(candidates),
                "hit@1": rank == 1,
                "hit@3": bool(rank and rank <= k),
                "first_hit_rank": rank,
                "latency_ms": elapsed_ms,
            }
        )

    n = len(claims)
    hit1 = sum(1 for r in records if r["hit@1"])
    hit3 = sum(1 for r in records if r["hit@3"])
    no_candidates = sum(1 for r in records if r["n_candidates"] == 0)
    result = {
        "generated_at": _now(),
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


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="CiteGuard Live 30 句评测")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="只校验 pages/claims 完整性")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（预览用）")
    args = parser.parse_args(argv)

    pages_path = args.data_dir / "pages.json"
    claims_path = args.data_dir / "claims.jsonl"
    try:
        pages = load_pages(pages_path)
        claims = load_claims(claims_path)
    except (OSError, ValueError) as exc:
        print(f"数据读取失败: {exc}", file=sys.stderr)
        return 1

    errors = validate(pages, claims)
    if args.check:
        if errors:
            print("数据校验失败:")
            for error in errors:
                print(f"- {error}")
            return 1
        print(f"OK: {len(pages)} 个公开页 / {len(claims)} 条引用句，来源字段齐全")
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
    result["data"] = {"pages": str(pages_path.relative_to(ROOT)), "claims": str(claims_path.relative_to(ROOT))}
    result["checker"] = "citeguard.live_check.check_claim"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_summary(result)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
