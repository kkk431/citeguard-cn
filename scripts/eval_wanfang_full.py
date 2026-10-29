"""Wanfang full-sample Chinese coverage: probe the Chinese references that the
first batch (Unverified/Unknown only) did not touch, so the coverage number is
reported on all Chinese references, not a filtered subset.  Resumable, hard
limit for the daily trial quota.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_wanfang_batch as base  # noqa: E402
from citeguard import config, wanfang  # noqa: E402

VERIFY = ROOT / "data" / "experiments" / "verify_real.json"
FIRST = ROOT / "data" / "experiments" / "wanfang_batch.json"
STATE = ROOT / "data" / "experiments" / "wanfang_full.json"
CJK = re.compile(r"[\u4e00-\u9fff]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--rows", type=int, default=5)
    args = ap.parse_args()

    base.load_env()
    config.WANFANG_APP_KEY = __import__("os").environ.get("WANFANG_APP_KEY", "").strip()
    if not wanfang.available():
        print("no key", file=sys.stderr)
        return 2

    rows = json.loads(VERIFY.read_text(encoding="utf-8"))["rows"]
    first = json.loads(FIRST.read_text(encoding="utf-8"))["processed"] if FIRST.exists() else {}
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"processed": {}}
    done = state["processed"]

    targets = []
    for i, row in enumerate(rows):
        if not CJK.search(row.get("raw") or ""):
            continue
        if str(i) in done and "error" not in done[str(i)]:
            continue
        if str(i) in first and "error" not in first[str(i)]:
            continue
        targets.append((i, row))

    calls = 0
    started = time.time()
    for i, row in targets[: args.limit]:
        query = base.query_for(row)
        rec = {"index": i, "paper": row.get("paper", ""), "title": row.get("title", ""),
               "year": row.get("year"), "raw": (row.get("raw") or "")[:240]}
        try:
            results = wanfang.search(query, rows=args.rows)
            calls += 1
            best = None
            for item in results:
                score = base.similarity(row.get("title", ""), base.record_title(item))
                if best is None or score > best[0]:
                    best = (score, item)
            if best:
                score, item = best
                rec.update({"hit": True, "title_sim": round(score, 4),
                            "matched_title": base.record_title(item),
                            "matched_year": base.record_year(item),
                            "matched_venue": base.record_venue(item),
                            "n_results": len(results),
                            "year_match": bool(row.get("year")) and base.record_year(item)[:4] == str(row.get("year"))[:4]})
            else:
                rec.update({"hit": False, "title_sim": 0.0, "n_results": 0})
        except Exception as exc:  # noqa: BLE001
            calls += 1
            rec.update({"hit": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            if "QUOTA" in str(exc).upper():
                done[str(i)] = rec
                break
        done[str(i)] = rec
        STATE.write_text(json.dumps({"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "processed": done},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
        if calls % 10 == 0:
            print(f"{calls} calls", flush=True)

    new = [v for k, v in done.items() if "error" not in v]
    old = [v for v in first.values() if "error" not in v]
    old_strong = [v for v in old if v.get("hit") and (v.get("title_sim") or 0) >= 0.92 and v.get("year_match")]
    new_strong = [v for v in new if v.get("hit") and (v.get("title_sim") or 0) >= 0.92 and v.get("year_match")]
    old_hit = [v for v in old if v.get("hit") and (v.get("title_sim") or 0) >= 0.80]
    new_hit = [v for v in new if v.get("hit") and (v.get("title_sim") or 0) >= 0.80]
    total = len(old) + len(new)
    summary = {
        "calls_this_run": calls,
        "new_probed": len(new),
        "new_hit_0.80": len(new_hit),
        "new_strong": len(new_strong),
        "combined_total": total,
        "combined_hit_0.80": len(old_hit) + len(new_hit),
        "combined_strong": len(old_strong) + len(new_strong),
        "combined_rate_0.80": round((len(old_hit) + len(new_hit)) / total, 4) if total else 0,
        "combined_rate_strong": round((len(old_strong) + len(new_strong)) / total, 4) if total else 0,
        "elapsed_s": round(time.time() - started, 1),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
