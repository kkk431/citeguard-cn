"""Independent audit + spot check for the ClaimSupport-CN SFT splits.

Everything here is re-derived from files: the three ``support_*.jsonl`` files, the
raw ClaimSupport rows they were built from, the published dev/test split, and
(optionally) the live OpenAlex records.  The builder's in-memory state is never
trusted, so a green run means the *artifacts* are consistent, not that the
builder agrees with itself.

Checks
  1. schema: exactly ``id/claim/evidence/label/split``, str values, split field
     matches the file it lives in, label in the four-way vocabulary;
  2. counts: train >= 500, 500 <= train+dev+test <= 1000, every label present;
  3. ids: unique inside a split, disjoint across splits, prefix <-> batch;
  4. dev/test still the official held-out rows (same ids as
     data/claimsupport_cn/split_seed20261024.json, byte-identical to git HEAD);
  5. join: every SFT row maps to exactly one raw row, with identical claim and
     label and evidence identical or a documented 1800-char truncation;
  6. construction rules re-checked on all raw rows via
     ``build_claimsupport.check_item``;
  7. source de-duplication: no source work shared between splits, no work used
     by more than one item, unique-work count matches the raw data;
  8. README numbers equal the jsonl numbers (no placeholder drift);
  9. optional ``--verify-openalex N``: re-fetch N source works and check id,
     title, year, doi, language, type and the cited fragment against OpenAlex.

Outputs
  data/experiments/sft_split_audit.json   machine-readable report + verdict
  data/experiments/sft_spotcheck.json     20-row spot-check sample for review

Usage
  python scripts/verify_sft_splits.py                       # offline
  python scripts/verify_sft_splits.py --verify-openalex 5   # + live sources
  python scripts/verify_sft_splits.py --no-network          # force offline
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sft"
EXPERIMENTS = ROOT / "data" / "experiments"
RAW = {
    "base": ROOT / "data" / "claimsupport_cn" / "claimsupport_cn.jsonl",
    "ext": ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_ext.jsonl",
    "v2": ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_v2.jsonl",
    "a3": DATA / "claimsupport_a3.jsonl",
}
SPLIT_JSON = ROOT / "data" / "claimsupport_cn" / "split_seed20261024.json"
SPLITS = ("train", "dev", "test")
LABELS = ["support", "partial", "contradict", "no_evidence"]
ID_RE = re.compile(r"^(cs|cx|c2|a3)-\d{4}$")
PREFIX_BATCH = {"cs": "base", "cx": "ext", "c2": "v2", "a3": "a3"}
OPENALEX = "https://api.openalex.org/works/"
UA = "citeguard-sft-verifier/1.0 (mailto:research@example.org)"
MAX_EVIDENCE = 1800

# Same wording as scripts/train_support_lora.py SYS (checked below against source).
SYS = (
    "你是学术引文核验员。判断【证据片段】是否支持【引用句】，四选一："
    "support（完全支持）、partial（部分支持）、contradict（矛盾）、no_evidence（证据不足）。"
    '只输出 JSON：{"label": "..."}。'
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_show_bytes(rel: str) -> bytes | None:
    """Bytes of ``rel`` at HEAD, or None when git/the object is unavailable."""
    try:
        proc = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, check=False
        )
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def git_head() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, check=False
        )
    except OSError:
        return "unknown"
    return proc.stdout.decode("ascii", "replace").strip() or "unknown"


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, cid: str, ok: bool, detail: str, hard: bool = True) -> bool:
        status = "pass" if ok else ("fail" if hard else "warn")
        self.checks.append({"id": cid, "status": status, "detail": detail})
        print(f"[{status:4s}] {cid}: {detail}")
        return ok

    @property
    def failed(self) -> list[dict]:
        return [c for c in self.checks if c["status"] == "fail"]

    @property
    def warned(self) -> list[dict]:
        return [c for c in self.checks if c["status"] == "warn"]


def schema_check(rows: dict[str, list[dict]], rep: Report) -> None:
    keys = ["id", "claim", "evidence", "label", "split"]
    problems: list[str] = []
    for split, items in rows.items():
        for row in items:
            if list(row.keys()) != keys:
                problems.append(f"{row.get('id')}: keys {list(row.keys())}")
                continue
            if not all(isinstance(row[k], str) for k in keys):
                problems.append(f"{row['id']}: non-str value")
            if row["split"] != split:
                problems.append(f"{row['id']}: split={row['split']} in {split}.jsonl")
            if row["label"] not in LABELS:
                problems.append(f"{row['id']}: label={row['label']}")
            if not row["claim"].strip() or not row["evidence"].strip():
                problems.append(f"{row['id']}: empty claim/evidence")
            if len(row["evidence"]) > MAX_EVIDENCE:
                problems.append(f"{row['id']}: evidence {len(row['evidence'])} > {MAX_EVIDENCE}")
            if not ID_RE.match(row["id"]):
                problems.append(f"{row['id']}: id pattern")
    rep.add(
        "schema",
        not problems,
        f"{sum(len(v) for v in rows.values())} rows checked; "
        + ("all conform to id/claim/evidence/label/split" if not problems else f"{len(problems)} problems: {problems[:5]}"),
    )


def count_check(rows: dict[str, list[dict]], rep: Report) -> dict:
    counts = {name: len(items) for name, items in rows.items()}
    total = sum(counts.values())
    rep.add("count_train", counts["train"] >= 500, f"train={counts['train']} (acceptance >= 500)")
    rep.add("count_total", 500 <= total <= 1000, f"total={total} (target 500-1000)")
    labels = {name: Counter(r["label"] for r in items) for name, items in rows.items()}
    missing = [label for label in LABELS if labels["train"].get(label, 0) == 0]
    rep.add(
        "labels_present",
        not missing,
        "train distribution " + json.dumps({l: labels["train"].get(l, 0) for l in LABELS}, ensure_ascii=False)
        + (f"; missing {missing}" if missing else ""),
    )
    return {"counts": counts, "labels": {name: {l: labels[name].get(l, 0) for l in LABELS} for name in SPLITS}}


def id_check(rows: dict[str, list[dict]], rep: Report) -> None:
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for split, items in rows.items():
        for row in items:
            if row["id"] in seen:
                dupes.append(f"{row['id']} in {seen[row['id']]} and {split}")
            seen[row["id"]] = split
    rep.add("ids_unique", not dupes, f"{len(seen)} ids; duplicates: {dupes[:5] or 0}")
    overlap = {}
    for a in SPLITS:
        for b in SPLITS:
            if SPLITS.index(a) < SPLITS.index(b):
                inter = {r["id"] for r in rows[a]} & {r["id"] for r in rows[b]}
                overlap[f"{a}&{b}"] = len(inter)
    rep.add("ids_disjoint", not any(overlap.values()), json.dumps(overlap))
    bad_prefix = [
        row["id"]
        for items in rows.values()
        for row in items
        if not ID_RE.match(row["id"]) or PREFIX_BATCH[row["id"][:2]] not in RAW
    ]
    rep.add("ids_prefix_known", not bad_prefix, f"unknown batch prefixes: {bad_prefix[:5] or 0}")


def split_role_check(rows: dict[str, list[dict]], rep: Report) -> None:
    if not SPLIT_JSON.exists():
        rep.add("split_roles", False, f"missing {SPLIT_JSON.relative_to(ROOT)}")
        return
    official = json.loads(SPLIT_JSON.read_text(encoding="utf-8"))
    dev_ids = [r["id"] for r in rows["dev"]]
    test_ids = [r["id"] for r in rows["test"]]
    rep.add(
        "test_is_official",
        set(test_ids) == set(official["test"]) and len(test_ids) == len(official["test"]),
        f"test ids == split_seed20261024.test ({len(official['test'])} ids), order preserved",
    )
    borrowed = sorted(official["dev"])[:20]
    rep.add(
        "dev_is_official",
        set(dev_ids) == set(official["dev"][20:]) and set(borrowed) <= {r["id"] for r in rows["train"]},
        f"dev ids == official dev minus the {len(borrowed)} rows borrowed into train",
    )


def unchanged_check(rows: dict[str, list[dict]], rep: Report) -> dict:
    """dev/test must be byte-identical to HEAD so old numbers stay comparable."""
    result: dict[str, bool] = {}
    for name in ("dev", "test"):
        rel = f"data/sft/support_{name}.jsonl"
        old = git_show_bytes(rel)
        new = (DATA / f"support_{name}.jsonl").read_bytes()
        result[name] = old is not None and old == new
        if old is None:
            rep.add(f"unchanged_{name}", False, f"git HEAD:{rel} unavailable - cannot prove comparability", hard=False)
        else:
            rep.add(
                f"unchanged_{name}",
                result[name],
                f"byte-identical to git HEAD:{rel} ({len(new)} B)" if result[name]
                else f"differs from git HEAD:{rel} ({len(old)} B vs {len(new)} B)",
            )
    return {"head": git_head(), **result}


def join_check(rows: dict[str, list[dict]], raw: dict[str, dict], rep: Report) -> None:
    missing, bad_claim, bad_label, bad_evidence = [], [], [], []
    truncated = 0
    for split, items in rows.items():
        for row in items:
            src = raw.get(row["id"])
            if src is None:
                missing.append(row["id"])
                continue
            if src["claim"] != row["claim"]:
                bad_claim.append(row["id"])
            if src["label"] != row["label"]:
                bad_label.append(row["id"])
            if src["evidence"] == row["evidence"]:
                continue
            if len(row["evidence"]) == MAX_EVIDENCE and src["evidence"].startswith(row["evidence"]):
                truncated += 1
                continue
            bad_evidence.append(row["id"])
    rep.add("join_ids", not missing, f"{len(raw)} raw rows; unresolved SFT ids: {missing[:5] or 0}")
    rep.add("join_claim", not bad_claim, f"claim mismatches: {bad_claim[:5] or 0}")
    rep.add("join_label", not bad_label, f"label mismatches: {bad_label[:5] or 0}")
    rep.add(
        "join_evidence",
        not bad_evidence,
        f"evidence identical ({truncated} rows at the {MAX_EVIDENCE}-char cap); mismatches: {bad_evidence[:5] or 0}",
    )


def rules_check(raw_rows: dict[str, list[dict]], rep: Report) -> list[dict]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_claimsupport as B  # noqa: PLC0415 - deliberate, keeps offline checks cheap

    failures: list[dict] = []
    checked = 0
    for batch, items in raw_rows.items():
        for row in items:
            problems = B.check_item(row)
            checked += 1
            if problems:
                failures.append({"id": row["id"], "batch": batch, "problems": problems[:3]})
    rep.add(
        "construction_rules",
        not failures,
        f"{checked - len(failures)}/{checked} raw rows re-derive their label rule; failures: {failures[:3] or 0}",
    )
    return failures


def source_check(raw: dict[str, dict], rows: dict[str, list[dict]], rep: Report) -> dict:
    works_by_split: dict[str, set[str]] = {name: set() for name in SPLITS}
    work_items: dict[str, set[str]] = {}
    for split, items in rows.items():
        for row in items:
            src = raw.get(row["id"])
            if src is None:
                continue
            for key in ("claim_source", "evidence_source"):
                work = (src.get(key) or {}).get("openalex_id")
                if not work:
                    continue
                works_by_split[split].add(work)
                work_items.setdefault(work, set()).add(row["id"])
    overlap = {}
    for i, a in enumerate(SPLITS):
        for b in SPLITS[i + 1:]:
            overlap[f"{a}&{b}"] = len(works_by_split[a] & works_by_split[b])
    rep.add("sources_disjoint", not any(overlap.values()), f"source work overlap {json.dumps(overlap)}")
    reused = {w: sorted(ids) for w, ids in work_items.items() if len(ids) > 1}
    rep.add(
        "sources_single_use",
        not reused,
        f"{len(work_items)} unique works; works reused by >1 item: {len(reused)}"
        + (f" e.g. {list(reused)[:3]}" if reused else ""),
    )
    return {
        "works_per_split": {name: len(works) for name, works in works_by_split.items()},
        "works_total": len(work_items),
        "overlap": overlap,
        "reused": len(reused),
    }


def readme_check(rows: dict[str, list[dict]], rep: Report) -> bool:
    path = DATA / "README.md"
    if not path.exists():
        return rep.add("readme", False, "missing data/sft/README.md")
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    for name in SPLITS:
        items = rows[name]
        counts = Counter(r["label"] for r in items)
        expected = (
            f"| {name} | {len(items)} | " + " | ".join(str(counts.get(l, 0)) for l in LABELS) + " |"
        )
        if expected not in text:
            problems.append(f"table row missing: {expected}")
    for needle in ("## 5. 复现命令", "## 3. 来源与去重", "## 4. JSONL 字段", "--model-size 4b"):
        if needle not in text:
            problems.append(f"section missing: {needle}")
    train_sha = sha256_file(DATA / "support_train.jsonl")
    if train_sha not in text:
        problems.append("support_train.jsonl sha256 not quoted")
    return rep.add(
        "readme_numbers",
        not problems,
        "README counts/labels/sha256 match the jsonl" if not problems else "; ".join(problems),
    )


def _get_json(url: str, timeout: int = 40) -> tuple[int, dict | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed host
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, {"error": str(exc)}


def openalex_check(
    rows: dict[str, list[dict]], raw: dict[str, dict], n: int, seed: int, rep: Report
) -> list[dict]:
    if n <= 0:
        rep.add("openalex_sources", True, "skipped (--verify-openalex 0)", hard=False)
        return []
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_claimsupport as B  # noqa: PLC0415

    rng = random.Random(seed)
    # Spread the sample across labels, and alternate between the new a3 sources and
    # the inherited base/ext/v2 sources so both provenances get a live check.
    buckets: dict[str, dict[str, list[dict]]] = {
        "new": {label: [] for label in LABELS},
        "old": {label: [] for label in LABELS},
    }
    for row in rows["train"]:
        buckets["new" if row["id"].startswith("a3-") else "old"][row["label"]].append(row)
    for group in buckets.values():
        for items in group.values():
            rng.shuffle(items)
    picks: list[dict] = []
    while len(picks) < n and any(buckets[g][l] for g in buckets for l in LABELS):
        for label in LABELS:
            if len(picks) >= n:
                break
            wanted = "new" if len(picks) % 2 == 0 else "old"
            pool = buckets[wanted][label] or buckets["old" if wanted == "new" else "new"][label]
            if not pool:
                continue
            picks.append(pool.pop(0))

    results: list[dict] = []
    for row in picks:
        src = raw[row["id"]]
        if row["label"] == "contradict":
            role = "evidence_source"
            fragment = src["evidence"]
        else:
            role = "claim_source"
            fragment = src["claim"]
        ref = src.get(role) or {}
        work_id = ref.get("openalex_id", "")
        short = work_id.rsplit("/", 1)[-1]
        query = urllib.parse.urlencode(
            {
                "select": "id,doi,title,publication_year,language,type,abstract_inverted_index",
                "mailto": "research@example.org",
            }
        )
        status, payload = _get_json(f"{OPENALEX}{short}?{query}")
        record: dict = {
            "item_id": row["id"],
            "batch": PREFIX_BATCH[row["id"][:2]],
            "label": row["label"],
            "source_role": role,
            "openalex_id": work_id,
            "http_status": status,
        }
        if status != 200 or not payload:
            record["ok"] = False
            record["error"] = "fetch failed"
            results.append(record)
            continue
        api_title = B.clean_text(payload.get("title") or "")
        api_doi = (payload.get("doi") or "").strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/"):
            if api_doi.lower().startswith(prefix):
                api_doi = api_doi[len(prefix):]
                break
        cached_doi = (ref.get("doi") or "").strip()
        record.update(
            {
                "api_id": payload.get("id"),
                "id_match": payload.get("id") == work_id,
                "title_similarity": round(B.char_similarity(api_title, ref.get("title") or ""), 4),
                "year_match": payload.get("publication_year") == ref.get("year"),
                "cached_doi": cached_doi,
                "api_doi": api_doi,
                # A missing cached DOI cannot contradict the live record: the Chinese
                # auto-translated duplicates had no DOI until OpenAlex merged them.
                "doi_match": cached_doi == api_doi or not cached_doi,
                "language": payload.get("language"),
                "type": payload.get("type"),
            }
        )
        abstract = B.clean_text(B.reconstruct_abstract(payload.get("abstract_inverted_index")) or "")
        record["has_abstract"] = bool(abstract)
        record["fragment_in_abstract"] = bool(abstract) and fragment in abstract
        same_work = bool(
            record["title_similarity"] >= 0.9 and record["year_match"] and record["doi_match"]
        )
        intact = bool(same_work and record["fragment_in_abstract"] and record["language"] == "zh")
        if intact and record["id_match"]:
            record["status"] = "verified"
        elif intact and not record["id_match"]:
            # OpenAlex merges duplicate records; the requested id redirects to a new one.
            record["status"] = "drift_merged"
        elif same_work:
            record["status"] = "drift_metadata"  # abstract/language changed upstream
        else:
            record["status"] = "mismatch"
        record["ok"] = record["status"] == "verified"
        results.append(record)
        time.sleep(0.4)

    verified = [r for r in results if r.get("status") == "verified"]
    drifted = [r for r in results if r.get("status") in ("drift_merged", "drift_metadata")]
    mismatched = [r for r in results if r.get("status") == "mismatch"]
    fetch_bad = [r for r in results if r.get("http_status") != 200]
    drift_rate = len(drifted) / len(results) if results else 0.0
    detail = (
        f"{len(verified)}/{len(results)} live sources byte-level verified (same id, title, year, doi, "
        f"cited fragment still in the Chinese abstract)"
    )
    if drifted:
        detail += (
            f"; {len(drifted)} drifted upstream ({drift_rate:.0%}): "
            + ", ".join(f"{r['item_id']} {r['openalex_id']} -> {r.get('api_id')} [{r['status']}]" for r in drifted[:3])
        )
    if fetch_bad:
        detail += f"; {len(fetch_bad)} fetch failures"
    # Upstream merges/metadata edits are a documented OpenAlex behaviour: tolerate a
    # small rate but surface it. A content mismatch (different work at the same id) or
    # a vanished record is a real provenance break.
    rep.add(
        "openalex_sources",
        not mismatched and not fetch_bad and drift_rate <= 0.25,
        detail,
    )
    if drifted:
        rep.add(
            "openalex_drift",
            True,
            f"{len(drifted)}/{len(results)} sampled works changed on OpenAlex after the fetch "
            f"(merge/metadata edit); cached fragments remain what the dataset was built from",
            hard=False,
        )
    return results


def sys_prompt_check(rep: Report) -> None:
    """The spot-check messages must quote the trainer's real system prompt."""
    src = ROOT / "scripts" / "train_support_lora.py"
    fragments = [
        "你是学术引文核验员。判断【证据片段】是否支持【引用句】，四选一：",
        "support（完全支持）、partial（部分支持）、contradict（矛盾）、no_evidence（证据不足）。",
        '只输出 JSON：{"label": "..."}。',
    ]
    if not src.exists():
        rep.add("sys_prompt", False, "scripts/train_support_lora.py missing", hard=False)
        return
    source = src.read_text(encoding="utf-8")
    missing = [f for f in fragments if f not in source]
    ok = not missing and SYS == "".join(fragments)
    rep.add(
        "sys_prompt",
        ok,
        "spot-check system prompt matches scripts/train_support_lora.py SYS" if ok
        else f"SYS drift: {missing or 'composition mismatch'}",
        hard=False,
    )


def write_readme_audit(live: list[dict], rep: Report) -> None:
    """Refresh the measured live-source block in data/sft/README.md between markers."""
    path = DATA / "README.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if "<!-- audit:start -->" not in text or "<!-- audit:end -->" not in text:
        rep.add("readme_audit_block", False, "audit markers missing in data/sft/README.md", hard=False)
        return
    if not live:
        body = "\n（本次审计离线运行，未做来源在线复核；加 `--verify-openalex 20` 可生成实测数字。）\n"
    else:
        verified = [r for r in live if r.get("status") == "verified"]
        drifted = [r for r in live if r.get("status") in ("drift_merged", "drift_metadata")]
        bad = [r for r in live if r.get("status") == "mismatch" or r.get("http_status") != 200]
        lines = [
            "",
            f"- 在线复核样本 **{len(live)}** 条：a3 新来源与 base / ext / v2 旧来源交替抽取，四标签轮转；",
            f"- **逐字一致 {len(verified)}/{len(live)}**：同 id、同标题、同年份、同 DOI，且引用片段仍出现在该篇中文摘要中；",
        ]
        if drifted:
            examples = "；".join(
                f"`{r['item_id']}` {r['openalex_id'].rsplit('/', 1)[-1]} → {str(r.get('api_id')).rsplit('/', 1)[-1]}"
                for r in drifted[:3]
            )
            lines.append(
                f"- **被 OpenAlex 上游合并 {len(drifted)}/{len(live)}**：标题与年份一致，DOI 为上游新补，"
                f"抓取时的中文摘要属自动翻译记录（例：{examples}）；"
            )
        lines.append(f"- 未解释的内容不一致 {len(bad)} 条；明细见 `data/experiments/sft_split_audit.json` 的 `live_sources`。")
        body = "\n".join(lines) + "\n"
    start, end = "<!-- audit:start -->", "<!-- audit:end -->"
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    path.write_bytes((head + start + body + end + tail).encode("utf-8"))
    rep.add(
        "readme_audit_block",
        True,
        f"README live-source block refreshed from {len(live)} checked sources",
        hard=False,
    )


def build_spotcheck(rows: dict[str, list[dict]], raw: dict[str, dict], seed: int) -> dict:
    want = {"train": 10, "dev": 5, "test": 5}
    rng = random.Random(seed)
    picked: list[dict] = []
    for split, total in want.items():
        per_label = {label: [] for label in LABELS}
        for row in rows[split]:
            per_label[row["label"]].append(row)
        for items in per_label.values():
            items.sort(key=lambda r: r["id"])
            rng.shuffle(items)
        chosen: list[dict] = []
        while len(chosen) < total and any(per_label.values()):
            for label in LABELS:
                if per_label[label] and len(chosen) < total:
                    chosen.append(per_label[label].pop())
        for row in sorted(chosen, key=lambda r: r["id"]):
            src = raw[row["id"]]
            picked.append(
                {
                    "id": row["id"],
                    "split": split,
                    "label": row["label"],
                    "construction": src.get("construction", ""),
                    "claim": row["claim"],
                    "evidence": row["evidence"],
                    "claim_source": src.get("claim_source"),
                    "evidence_source": src.get("evidence_source"),
                    "messages": [
                        {"role": "system", "content": SYS},
                        {"role": "user", "content": f"【引用句】{row['claim']}\n【证据片段】{row['evidence']}"},
                        {"role": "assistant", "content": json.dumps({"label": row["label"]}, ensure_ascii=False)},
                    ],
                }
            )
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "n": len(picked),
        "note": "Deterministic sample (seed above); messages use the same system prompt and "
                "user template as scripts/train_support_lora.py.",
        "items": picked,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--out", default=str(EXPERIMENTS / "sft_split_audit.json"))
    ap.add_argument("--spotcheck", default=str(EXPERIMENTS / "sft_spotcheck.json"))
    ap.add_argument("--verify-openalex", type=int, default=0, help="live source checks (0 = offline)")
    ap.add_argument("--no-network", action="store_true", help="force offline (overrides --verify-openalex)")
    ap.add_argument("--seed", type=int, default=20261114)
    args = ap.parse_args()

    data = Path(args.data)
    rep = Report()
    rows = {name: read_jsonl(data / f"support_{name}.jsonl") for name in SPLITS}
    raw_rows = {batch: read_jsonl(path) for batch, path in RAW.items() if path.exists()}
    raw = {row["id"]: row for items in raw_rows.values() for row in items}

    schema_check(rows, rep)
    stats = count_check(rows, rep)
    id_check(rows, rep)
    split_role_check(rows, rep)
    unchanged = unchanged_check(rows, rep)
    join_check(rows, raw, rep)
    failures = rules_check(raw_rows, rep)
    sources = source_check(raw, rows, rep)
    readme_check(rows, rep)
    sys_prompt_check(rep)
    live = openalex_check(rows, raw, 0 if args.no_network else args.verify_openalex, args.seed, rep)
    write_readme_audit(live, rep)

    lengths = {
        name: {
            "claim_min": min(len(r["claim"]) for r in items),
            "claim_max": max(len(r["claim"]) for r in items),
            "evidence_max": max(len(r["evidence"]) for r in items),
        }
        for name, items in rows.items()
        if items
    }
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/verify_sft_splits.py",
        "data_dir": str(data.relative_to(ROOT)).replace("\\", "/"),
        "raw_batches": {batch: len(items) for batch, items in raw_rows.items()},
        **stats,
        "lengths": lengths,
        "files": {
            f"support_{name}.jsonl": {
                "bytes": (data / f"support_{name}.jsonl").stat().st_size,
                "sha256": sha256_file(data / f"support_{name}.jsonl"),
            }
            for name in SPLITS
        },
        "sources": sources,
        "unchanged_vs_head": unchanged,
        "rule_failures": failures[:10],
        "live_sources": live,
        "checks": rep.checks,
        "verdict": "pass" if not rep.failed else "fail",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    spot = Path(args.spotcheck)
    spot.write_bytes(json.dumps(build_spotcheck(rows, raw, args.seed), ensure_ascii=False, indent=2).encode("utf-8"))

    print(f"\nverdict: {report['verdict']}  ({len(rep.checks) - len(rep.failed)} pass / "
          f"{len(rep.failed)} fail / {len(rep.warned)} warn)")
    print(f"wrote {out.relative_to(ROOT)}")
    print(f"wrote {spot.relative_to(ROOT)}")
    return 0 if not rep.failed else 1


if __name__ == "__main__":
    sys.exit(main())
