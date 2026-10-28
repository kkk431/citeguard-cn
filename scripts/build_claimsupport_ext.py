"""Build ClaimSupport-CN-Ext: a disjoint 60-item extension of ClaimSupport-CN.

The construction rules are identical to ``build_claimsupport.py`` (support = core
abstract sentence; partial = evidence is the first assertion clause; contradict =
antonym-flipped claim; no_evidence = unrelated paper).  Source works are limited
to those NOT used by the original 100 items, so the extension is disjoint at the
paper level and the original dataset/sha256 is unchanged.

The extension is reported separately: it is still a *constructed* dataset, not
new human annotation.

Usage:
    PYTHONPATH=src python3 scripts/build_claimsupport_ext.py [--refresh]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_claimsupport as B  # noqa: E402

N_SUPPORT, N_PARTIAL, N_CONTRADICT, N_NO_EVIDENCE = 24, 15, 12, 9
N_TOTAL = N_SUPPORT + N_PARTIAL + N_CONTRADICT + N_NO_EVIDENCE
SEED = 20261028


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="refetch OpenAlex source units")
    args = ap.parse_args(argv)

    base_path = B.DATA_DIR / "claimsupport_cn.jsonl"
    used: set[str] = set()
    for line in base_path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        used.add(item["claim_source"]["openalex_id"])
        used.add(item["evidence_source"]["openalex_id"])

    units, stats = B.load_or_fetch_sources(refresh=args.refresh, target=400)
    unused = [u for u in units if u["id"] not in used and u["sentences"]]
    print(f"[sources] total={stats['units']} used_by_base={len(used)} unused={len(unused)}")

    B.N_SUPPORT, B.N_PARTIAL, B.N_CONTRADICT, B.N_NO_EVIDENCE = (
        N_SUPPORT,
        N_PARTIAL,
        N_CONTRADICT,
        N_NO_EVIDENCE,
    )
    B.N_TOTAL = N_TOTAL
    rng = random.Random(SEED)
    items = B.build_items(unused, rng)
    for index, item in enumerate(items, 1):
        item["id"] = f"cx-{index:04d}"

    failures = []
    for item in items:
        problems = B.check_item(item)
        if problems:
            failures.append((item["id"], problems))
    if failures:
        print(f"[fatal] {len(failures)} construction failures: {failures[:3]}", file=sys.stderr)
        return 2

    out = B.DATA_DIR / "claimsupport_cn_ext.jsonl"
    out.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
        encoding="utf-8",
        newline="\n",
    )
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    meta = {
        "dataset": "ClaimSupport-CN-Ext",
        "version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": SEED,
        "n": len(items),
        "counts": {
            "support": N_SUPPORT,
            "partial": N_PARTIAL,
            "contradict": N_CONTRADICT,
            "no_evidence": N_NO_EVIDENCE,
        },
        "disjoint_from": {
            "dataset": "ClaimSupport-CN",
            "note": "source works (OpenAlex IDs) are disjoint from the original 100 items",
        },
        "sha256": digest,
        "source_cache": "data/claimsupport_cn/claimsupport_cn.sources.json",
        "labels": {
            "support": "claim = a core abstract sentence; evidence contains it",
            "partial": "evidence is only the first assertion clause",
            "contradict": "one assertion flipped to its antonym",
            "no_evidence": "evidence is an unrelated paper with low title/fragment similarity",
        },
        "note": "constructed probes; labels are a property of the construction, not model output",
    }
    (B.DATA_DIR / "claimsupport_cn_ext.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(f"[done] {len(items)} items -> {out.name} sha256={digest[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
