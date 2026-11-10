"""Build ClaimSupport-CN-V2: 140 more constructed items (total 300 with base+ext).

Disjoint from both ClaimSupport-CN (100) and ClaimSupport-CN-Ext (60) at the
source-paper level. Construction rules are reused from build_claimsupport.py.
Labels are constructed, not human annotated.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_claimsupport as B  # noqa: E402

N_SUPPORT, N_PARTIAL, N_CONTRADICT, N_NO_EVIDENCE = 56, 40, 24, 20
N_TOTAL = N_SUPPORT + N_PARTIAL + N_CONTRADICT + N_NO_EVIDENCE
SEED = 20261110


def main() -> int:
    root = B.DATA_DIR
    used: set[str] = set()
    for name in ("claimsupport_cn.jsonl", "claimsupport_cn_ext.jsonl"):
        for line in (root / name).read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            used.add(item["claim_source"]["openalex_id"])
            used.add(item["evidence_source"]["openalex_id"])

    units, stats = B.load_or_fetch_sources(refresh=False, target=400)
    unused = [u for u in units if u["id"] not in used and u["sentences"]]
    print(f"[sources] total={stats['units']} used={len(used)} unused={len(unused)}")

    B.N_SUPPORT, B.N_PARTIAL, B.N_CONTRADICT, B.N_NO_EVIDENCE = (
        N_SUPPORT, N_PARTIAL, N_CONTRADICT, N_NO_EVIDENCE,
    )
    B.N_TOTAL = N_TOTAL
    items = B.build_items(unused, random.Random(SEED))
    for index, item in enumerate(items, 1):
        item["id"] = f"c2-{index:04d}"
    bad = [(i["id"], B.check_item(i)) for i in items if B.check_item(i)]
    if bad:
        print(f"[fatal] {len(bad)} failures: {bad[:3]}", file=sys.stderr)
        return 2

    out = root / "claimsupport_cn_v2.jsonl"
    out.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8", newline="\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    meta = {
        "dataset": "ClaimSupport-CN-V2",
        "version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": SEED,
        "n": len(items),
        "counts": {"support": N_SUPPORT, "partial": N_PARTIAL, "contradict": N_CONTRADICT, "no_evidence": N_NO_EVIDENCE},
        "disjoint_from": ["ClaimSupport-CN", "ClaimSupport-CN-Ext"],
        "sha256": digest,
        "labels": "constructed probes; not human annotation",
    }
    (root / "claimsupport_cn_v2.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(f"[done] {len(items)} items -> {out.name} sha256={digest[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
