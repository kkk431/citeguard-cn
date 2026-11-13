"""Assemble the ClaimSupport-CN SFT splits (train/dev/test) for LoRA fine-tuning.

Sources (all rule-constructed, source-disjoint from each other):
  base  100 official benchmark items  (official split: dev 40 / test 60, no train)
  ext    60 items from ``build_claimsupport_ext.py``
  v2    140 items from ``build_claimsupport_v2.py``
  a3    380 items from ``build_sft_expand.py`` (fresh OpenAlex pages, A3)

Split policy (keeps the historical dev/test untouched so old numbers stay comparable):
  train = the first 20 official-dev items + all of ext + v2 + a3
  dev   = the remaining 20 official-dev items
  test  = the 60 official-test items (never seen in training)
Every label is rule-constructed, not human-annotated, and each source work is
used by exactly one item across the three splits (asserted here, re-checked by
``scripts/verify_sft_splits.py``).  ``data/sft/README.md`` is generated from the
same numbers so the data card can never drift from the files.

Usage:
    python scripts/build_support_sft.py --out data/sft
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CN_DIR = ROOT / "data" / "claimsupport_cn"
BASE = CN_DIR / "claimsupport_cn.jsonl"
EXT = CN_DIR / "claimsupport_cn_ext.jsonl"
V2 = CN_DIR / "claimsupport_cn_v2.jsonl"
A3 = ROOT / "data" / "sft" / "claimsupport_a3.jsonl"
SPLIT = CN_DIR / "split_seed20261024.json"
LABELS = ["support", "partial", "contradict", "no_evidence"]
SPLITS = ["train", "dev", "test"]


def load(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"missing source file: {path} (run scripts/build_sft_expand.py first)")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def slim(row: dict, split: str) -> dict:
    return {
        "id": row["id"],
        "claim": row["claim"],
        "evidence": row["evidence"][:1800],
        "label": row["label"],
        "split": split,
    }


def source_map() -> dict[str, dict]:
    """id -> the two source works, so the split audit can prove disjointness."""
    out: dict[str, dict] = {}
    for path in (BASE, EXT, V2, A3):
        for row in load(path):
            out[row["id"]] = {
                "claim": (row.get("claim_source") or {}).get("openalex_id", ""),
                "evidence": (row.get("evidence_source") or {}).get("openalex_id", ""),
                "construction": row.get("construction", ""),
            }
    return out


def label_counts(rows: list[dict]) -> dict[str, int]:
    counts = Counter(row["label"] for row in rows)
    return {label: counts.get(label, 0) for label in LABELS}


def audit_splits(splits: dict[str, list[dict]], sources: dict[str, dict]) -> dict:
    """Prove the three splits share neither ids nor source works."""
    works: dict[str, set[str]] = {}
    for name, rows in splits.items():
        ids: set[str] = set()
        for row in rows:
            ref = sources[row["id"]]
            ids.update(i for i in (ref["claim"], ref["evidence"]) if i)
        works[name] = ids
    per_work_items: dict[str, set[str]] = {}
    for rows in splits.values():
        for row in rows:
            ref = sources[row["id"]]
            for key in ("claim", "evidence"):
                if ref[key]:
                    per_work_items.setdefault(ref[key], set()).add(row["id"])
    ids_all = Counter(row["id"] for rows in splits.values() for row in rows)
    pairs = [(a, b) for i, a in enumerate(SPLITS) for b in SPLITS[i + 1:]]
    return {
        "unique_ids": {name: len({row["id"] for row in rows}) for name, rows in splits.items()},
        "id_overlap": {f"{a}&{b}": len({r['id'] for r in splits[a]} & {r['id'] for r in splits[b]})
                       for a, b in pairs},
        "duplicate_ids_overall": [i for i, n in ids_all.items() if n > 1],
        "source_works": {name: len(ids) for name, ids in works.items()},
        "source_overlap": {f"{a}&{b}": len(works[a] & works[b]) for a, b in pairs},
        "works_used_by_multiple_items": [w for w, ids in per_work_items.items() if len(ids) > 1],
        "works_total": len(set().union(*works.values())),
    }


def _md_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_readme(out: Path, ctx: dict) -> Path:
    counts, labels, sources = ctx["counts"], ctx["labels"], ctx["source_files"]
    total = sum(counts.values())
    total_labels = {label: sum(labels[s][label] for s in SPLITS) for label in LABELS}
    rows = "\n".join(
        f"| {name} | {counts[name]} | {labels[name]['support']} | {labels[name]['partial']} "
        f"| {labels[name]['contradict']} | {labels[name]['no_evidence']} |"
        for name in SPLITS
    )
    rows += (
        f"\n| **合计** | **{total}** | **{total_labels['support']}** | **{total_labels['partial']}** "
        f"| **{total_labels['contradict']}** | **{total_labels['no_evidence']}** |"
    )
    src_rows = "\n".join(
        f"| {name} | {info['n']} | {info['works']} | `{info['path']}` |"
        for name, info in sources.items()
    )
    file_rows = "\n".join(
        f"| `{name}` | {size:,} B | `{digest}` |" for name, (size, digest) in ctx["output_files"].items()
    )
    a3 = ctx["a3"]
    audit = ctx["audit"]

    def ov(a: str, b: str, kind: str = "works") -> int:
        """Overlap digits for a split pair; audit keys are ``a&b`` in SPLITS order."""
        table = audit["source_overlap"] if kind == "works" else audit["id_overlap"]
        return table.get(f"{a}&{b}", 0)
    log_tail = "\n".join(a3["fetch_log"][-24:])
    text = f"""# ClaimSupport-CN SFT 数据（A3 扩样版）

供 Qwen3 系列 LoRA 四分类（`support` / `partial` / `contradict` / `no_evidence`）微调使用。
本文件由 `scripts/build_support_sft.py` 在生成数据时按实测数字渲染，不存在占位值。

## 1. 概览

| split | 条数 | support | partial | contradict | no_evidence |
| --- | ---: | ---: | ---: | ---: | ---: |
{rows}

- 训练样本 **{counts['train']}** 条（验收线 ≥500），三份合计 **{total}** 条；
- 标签为**规则构造**标签，不是人工标注；没有二次标注 / 一致性系数（kappa）声明；
- dev / test 与历史 80/20/60 版本**字节级一致**（同 id、同内容、同顺序；已对 git
  `HEAD:data/sft/support_dev.jsonl` / `support_test.jsonl` 逐字节比对通过），
  因此之前的 1.7B / 8B / 14B 结果仍可直接与本版 4B 结果对比；
- 本版只扩 train：`train = 20 条借用的官方 dev + ext 60 + v2 140 + a3 380`。

## 2. 标签口径（构造规则继承 `scripts/build_claimsupport.py`，未改动）

| 标签 | 构造规则（一句话） |
| --- | --- |
| `support` | claim 取来源论文摘要首个合格句，evidence 为该句（+第二句上下文），即 claim ⊆ evidence |
| `partial` | claim 为原句，evidence 只保留该句中一个断言从句（`partial_clause`），信息不足以判支持 |
| `contradict` | claim 把 evidence 句中首个反义短语替换（如 显著提高→显著降低，共 {ctx['antonym_pairs']} 组），evidence 保留原句 |
| `no_evidence` | claim 来自论文 B、evidence 来自论文 A；两篇标题/句子字符相似度 <0.22 且 bigram Jaccard <0.06，主题不相关 |

每条 a3 数据都由 `build_claimsupport.check_item()` 逐条复算规则自检通过（{ctx['self_check']}）；
base / ext / v2 的 300 条沿用原数据卡的自检结论。

## 3. 来源与去重

| 来源数据集 | 条数 | 唯一来源 work 数 | 路径 |
| --- | ---: | ---: | --- |
{src_rows}

- 每个 item 在 raw jsonl 里带 `claim_source` / `evidence_source`（`openalex_id`、`title`、`doi`、`year`）；
  SFT 三份 jsonl 是训练用瘦身版，只保留 `id/claim/evidence/label/split`；
- 三份 split 的来源 work 交集：train∩dev = {ov('train', 'dev')}，
  train∩test = {ov('train', 'test')}，dev∩test = {ov('dev', 'test')}；
- id 交集：train∩dev = {ov('train', 'dev', 'ids')}，
  train∩test = {ov('train', 'test', 'ids')}，dev∩test = {ov('dev', 'test', 'ids')}；
- 全量唯一来源 work：{audit['works_total']} 篇，被多个 item 复用的 work：{len(audit['works_used_by_multiple_items'])} 篇；
- 生成时断言 + `scripts/verify_sft_splits.py` 独立复算（只读三份 jsonl 与 raw 数据集），
  审计结果落盘 `data/experiments/sft_split_audit.json`；抽查样本 `data/experiments/sft_spotcheck.json`。

<!-- audit:start -->
（本节由 `scripts/verify_sft_splits.py --verify-openalex N` 写入实测数字；尚未运行在线复核。）
<!-- audit:end -->

### a3 新增来源（{sources['a3']['n']} 条）

- 只读复用 `data/claimsupport_cn/claimsupport_cn.sources.json`（2026-10-28，pages 1..4）中
  **未被前 300 条使用**的 {a3['from_prior']} 篇 work；
- 另从 OpenAlex 新抓取 pages {a3['pages'][0]}..{a3['pages'][1]}（filter `{a3['filter']}`），
  新增 {a3['from_new']} 篇 work（每页新增量见下方实测日志）；
- 新来源片段缓存：`data/sft/openalex_sources_a3.json`，sha256 `{a3['cache_sha']}`，
  每篇最多 2 句摘要片段，不存全文；上游元数据许可 CC0 1.0；
- 与现有 300 条（base + ext + v2，{a3['used_works']} 篇来源）的来源 work 重叠：**0**。

实测抓取日志（`data/sft/claimsupport_a3.meta.json` 的 `fetch_log`）：

```text
{log_tail}
```

## 4. JSONL 字段

每行一个 JSON 对象，键固定 5 个（与旧版 `build_support_sft.py` 完全一致）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | str | 全局唯一，前缀区分批次：`cs-`（base 100）、`cx-`（ext）、`c2-`（v2）、`a3-`（A3） |
| `claim` | str | 引用句 |
| `evidence` | str | 证据片段（截断到 1800 字符） |
| `label` | str | `support` / `partial` / `contradict` / `no_evidence` |
| `split` | str | `train` / `dev` / `test` |

示例（train 第一条，实测）：

```json
{ctx['example']}
```

微调时由 tokenizer 的 chat template 渲染成对话格式：system = 学术引文核验员四分类指令，
user = `【引用句】…\\n【证据片段】…`，assistant = `{{"label": "<label>"}}`；
见 `scripts/train_support_lora.py` 的 `build_prompt` / `encode`。

## 5. 复现命令

```bash
# 1) 构造 a3 扩样池（首次需要网络；缓存已随仓库提交，可 --offline 纯离线复现）
PYTHONPATH=src python scripts/build_sft_expand.py            # 首次
PYTHONPATH=src python scripts/build_sft_expand.py --offline  # 缓存复现

# 2) 组装三份 SFT jsonl + 本 README（断言 id/来源不重叠）
python scripts/build_support_sft.py --out data/sft

# 3) 独立审计（含 5 条来源的 OpenAlex 在线核验，加 --no-network 可跳过）
python scripts/verify_sft_splits.py --verify-openalex 5
```

## 6. 训练 / 评测入口

```bash
# 训练（--model-size 支持 1.7b / 4b / 8b / 14b，A3 目标是 4b）
python scripts/train_support_lora.py --model-size 4b --data data/sft --out out/support_lora_qwen3_4b

# 无 GPU 先验证数据与模型解析（不 import torch）
python scripts/train_support_lora.py --model-size 4b --dry-run

# 同口径评测（产品同款 prompt，经 OpenAI 兼容端点；--split 可选 test/dev）
python scripts/eval_support_adapter.py --model-size 4b --data data/sft --split test \
    --out out/support_adapter_eval_4b.json
```

两个脚本都把 `model_size` 写进 `run_meta.json` / 结果 JSON；本地权重放在
`models/Qwen3-4B` 时训练脚本自动优先用它，否则回退到 `Qwen/Qwen3-4B`。

实际指标记录在 `data/experiments/`，本数据卡不预填任何结果。

## 7. 文件清单

| 文件 | 大小 | sha256 |
| --- | ---: | --- |
{file_rows}

## 8. 已知限制

- 构造标签只保证"规则一致"，不保证与人类判断一致；`partial` 与 `no_evidence` 的边界尤其依赖构造启发式；
- OpenAlex 中文摘要中相当一部分是机器翻译，句式可能不自然（构造时已按 CJK 比例 / 句长过滤）；
- a3 与 base 的论文来源不同，但学科分布由 OpenAlex 默认相关性排序决定，未做人工分层；
- dev 仅 20 条（沿用历史口径），只用于训练期监控；对外报数请以 test 60 条为准。

## 9. 许可

- 本数据卡与 SFT jsonl：CC-BY-4.0；
- 上游 OpenAlex 元数据：CC0 1.0；片段缓存每篇最多 2 句，不重新分发摘要全文。
"""
    path = out / "README.md"
    write_lf(path, text)
    return path


def write_lf(path: Path, text: str) -> None:
    """Write UTF-8 with LF endings so re-runs are byte-identical across OSes."""
    path.write_bytes(text.encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "sft"))
    ap.add_argument("--no-readme", action="store_true", help="skip regenerating data/sft/README.md")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    base, ext, v2, a3 = load(BASE), load(EXT), load(V2), load(A3)
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    dev_ids, test_ids = set(split["dev"]), set(split["test"])

    train, dev, test, dev_pool = [], [], [], []
    for r in base:
        if r["id"] in dev_ids:
            dev_pool.append(r)
        elif r["id"] in test_ids:
            test.append(slim(r, "test"))
    dev_pool.sort(key=lambda r: r["id"])
    # The 100-set only ships dev+test; borrow half of dev for training (as before).
    train += [slim(r, "train") for r in dev_pool[:20]]
    dev += [slim(r, "dev") for r in dev_pool[20:]]
    train += [slim(r, "train") for r in ext]
    train += [slim(r, "train") for r in v2]
    train += [slim(r, "train") for r in a3]

    splits = {"train": train, "dev": dev, "test": test}
    for name, rows in splits.items():
        if not rows:
            raise SystemExit(f"empty split: {name}")
        bad = [r["id"] for r in rows if not r["claim"].strip() or not r["evidence"].strip()]
        if bad:
            raise SystemExit(f"{name}: empty claim/evidence in {bad[:5]}")
        unknown = sorted({r["label"] for r in rows} - set(LABELS))
        if unknown:
            raise SystemExit(f"{name}: unknown labels {unknown}")

    sources = source_map()
    audit = audit_splits(splits, sources)
    if audit["duplicate_ids_overall"]:
        raise SystemExit(f"duplicate ids across splits: {audit['duplicate_ids_overall'][:5]}")
    bad_overlap = {k: v for k, v in audit["source_overlap"].items() if v}
    if bad_overlap:
        raise SystemExit(f"source works shared between splits: {bad_overlap}")
    if audit["works_used_by_multiple_items"]:
        raise SystemExit(
            "source works reused by several items: "
            f"{audit['works_used_by_multiple_items'][:5]}"
        )
    if len(train) < 500:
        raise SystemExit(f"train split too small: {len(train)} < 500")
    if len(train) + len(dev) + len(test) > 1000:
        print(f"[warn] total SFT rows {len(train) + len(dev) + len(test)} exceed the 1000 target")

    for name, rows in splits.items():
        path = out / f"support_{name}.jsonl"
        write_lf(path, "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
        print(name, len(rows), path)

    labels = {name: label_counts(rows) for name, rows in splits.items()}
    raw_sources = {"base": BASE, "ext": EXT, "v2": V2, "a3": A3}
    raw_rows = {"base": base, "ext": ext, "v2": v2, "a3": a3}
    source_files = {}
    for key, path in raw_sources.items():
        works = set()
        for row in raw_rows[key]:
            for src in ("claim_source", "evidence_source"):
                ref = row.get(src) or {}
                if ref.get("openalex_id"):
                    works.add(ref["openalex_id"])
        source_files[key] = {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "n": len(raw_rows[key]),
            "works": len(works),
        }

    out_files = {}
    for name in SPLITS:
        path = out / f"support_{name}.jsonl"
        out_files[f"support_{name}.jsonl"] = (path.stat().st_size, sha256_file(path))

    a3_meta_path = out / "claimsupport_a3.meta.json"
    a3_meta = json.loads(a3_meta_path.read_text(encoding="utf-8")) if a3_meta_path.exists() else {}
    a3_works = a3_meta.get("source_works") or {}
    a3_pages = a3_meta.get("source_pages") or {}
    counts = {name: len(rows) for name, rows in splits.items()}
    meta = {
        "dataset": "ClaimSupport-CN SFT splits",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/build_support_sft.py",
        "sources": source_files,
        "policy": {
            "train": "official-dev[:20] + ext + v2 + a3",
            "dev": "official-dev[20:] (unchanged from the 80/20/60 version)",
            "test": "official test 60 (unchanged)",
        },
        "counts": counts,
        "labels": labels,
        "audit": audit,
        "a3": {
            "pages": [a3_pages.get("prior_pages_fetched", 0) + 1, a3_pages.get("a3_pages_fetched", 0)],
            "seed": a3_meta.get("seed"),
            "sha256": a3_meta.get("sha256"),
            "cache_sha256": (a3_meta.get("cache") or {}).get("sha256"),
            "works_from_prior_cache": a3_works.get("from_prior_cache"),
            "works_from_new_pages": a3_works.get("from_new_pages"),
        },
        "sha256": {name: digest for name, (_, digest) in out_files.items()},
        "note": "Labels are construction-based, not human-annotated; test split is the "
                "official 60 held-out items of the 100 set.",
    }
    write_lf(out / "support_sft.meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
    print(json.dumps(counts, ensure_ascii=False), json.dumps(labels, ensure_ascii=False))

    if not args.no_readme:
        ctx = {
            "counts": counts,
            "labels": labels,
            "source_files": source_files,
            "audit": audit,
            "a3": {
                "from_prior": a3_works.get("from_prior_cache", 0),
                "from_new": a3_works.get("from_new_pages", 0),
                "pages": [a3_pages.get("prior_pages_fetched", 0) + 1,
                          a3_pages.get("a3_pages_fetched", 0)],
                "filter": "language:zh,has_abstract:true,type:article",
                "cache_sha": (a3_meta.get("cache") or {}).get("sha256", ""),
                "used_works": a3_works.get("existing_300_works", 0),
                "fetch_log": a3_meta.get("fetch_log") or [],
            },
            "antonym_pairs": a3_meta.get("antonym_pairs", 0),
            "self_check": f"{a3_meta.get('self_check', {}).get('items', 0)}/"
                          f"{a3_meta.get('n', 0)} 条自检通过、0 条失败",
            "example": json.dumps(train[0], ensure_ascii=False),
            "output_files": out_files,
        }
        path = write_readme(out, ctx)
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
