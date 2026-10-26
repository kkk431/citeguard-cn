"""万方中文题录覆盖：断点续跑的批量评测。

用途：对 `data/experiments/verify_real.json` 里「含中文且未核验」的引文，
用万方开放平台按题名检索，测量命中率、题名相似度、年份匹配与潜在误配，
并估算启用万方兜底后中文覆盖率能从 12.4% 提到多少。

配额：试用账号 100 次/天、2000 次总额；本脚本默认 --limit 100，
按 `data/experiments/wanfang_batch.json` 断点续跑，跑过的条目不会重复调用。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard import wanfang  # noqa: E402

VERIFY_JSON = ROOT / "data" / "experiments" / "verify_real.json"
STATE_JSON = ROOT / "data" / "experiments" / "wanfang_batch.json"
ENV_FILE = ROOT / ".env.wanfang"

CJK = re.compile(r"[\u4e00-\u9fff]")
SEP = re.compile(r"[\s\u3000:：,，.。;；()（）\[\]【】《》\"'’‘“”\-—/]+")


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    # 兼容历史命名：.env 里是 WANFANG_API_KEY，产品读 WANFANG_APP_KEY。
    if values.get("WANFANG_API_KEY"):
        os.environ.setdefault("WANFANG_APP_KEY", values["WANFANG_API_KEY"])
    os.environ.setdefault("WANFANG_BASE", "https://api.wfdata.com")


def norm(text: str) -> str:
    return SEP.sub("", (text or "").lower())


def similarity(a: str, b: str) -> float:
    left, right = norm(a), norm(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def record_title(record: dict) -> str:
    value = record.get("Title")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def record_year(record: dict) -> str:
    value = record.get("PublishYear")
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "")


def record_venue(record: dict) -> str:
    value = record.get("PeriodicalTitle")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def first_author(record: dict) -> str:
    value = record.get("Creator")
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value or "")


def query_for(row: dict) -> str:
    title = (row.get("title") or "").strip()
    if len(title) >= 6 and CJK.search(title):
        return title
    raw = (row.get("raw") or "").strip()
    return raw[:120]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, help="本次最多调用次数（试用配额 100/天）")
    parser.add_argument("--rows", type=int, default=5, help="每次检索返回条数")
    parser.add_argument("--interval", type=float, default=0.8, help="两次调用最小间隔秒数（默认 0.8，避开平台 429）")
    parser.add_argument("--reset", action="store_true", help="清空断点状态重新开始")
    args = parser.parse_args()

    load_env()
    # config 在 import 时已读环境变量，这里同步一次。
    from citeguard import config

    config.WANFANG_APP_KEY = os.environ.get("WANFANG_APP_KEY", "").strip()
    config.WANFANG_BASE = os.environ.get("WANFANG_BASE", config.WANFANG_BASE).rstrip("/")
    if not wanfang.available():
        print("ERROR: 未配置 WANFANG_APP_KEY（检查 .env.wanfang）", file=sys.stderr)
        return 2

    rows = json.loads(VERIFY_JSON.read_text(encoding="utf-8"))["rows"]
    candidates = [
        (index, row)
        for index, row in enumerate(rows)
        if CJK.search(row.get("raw") or "") and row.get("status") in ("Unverified", "Unknown")
    ]

    if args.reset or not STATE_JSON.exists():
        state = {"updated_at": "", "source": "verify_real.json", "processed": {}}
    else:
        state = json.loads(STATE_JSON.read_text(encoding="utf-8"))
        state.setdefault("processed", {})

    processed = state["processed"]
    # 已成功的不再调用；失败条目允许重试。
    todo = [
        (index, row)
        for index, row in candidates
        if str(index) not in processed or "error" in processed.get(str(index), {})
    ]
    retry_errors = sum(1 for index, row in todo if str(index) in processed)
    if retry_errors:
        print(f"retrying {retry_errors} errored entries")
    print(f"candidates={len(candidates)} done={len(processed)} todo={len(todo)} limit={args.limit}")

    calls = 0
    quota_hit = False
    started = time.time()
    for index, row in todo:
        if calls >= args.limit:
            break
        query = query_for(row)
        record: dict = {
            "index": index,
            "paper": row.get("paper", ""),
            "title": row.get("title", ""),
            "year": row.get("year"),
            "raw": (row.get("raw") or "")[:300],
        }
        try:
            wanfang._MIN_INTERVAL = max(0.3, args.interval)
            results = None
            for attempt in range(3):
                try:
                    results = wanfang.search(query, rows=args.rows)
                    break
                except Exception as exc:  # noqa: BLE001
                    if "429" in str(exc) and attempt < 2:
                        time.sleep(2.0 * (attempt + 1))
                        continue
                    raise
            calls += 1
            best = None
            for item in results:
                score = similarity(row.get("title", ""), record_title(item))
                if best is None or score > best[0]:
                    best = (score, item)
            if best:
                score, item = best
                record.update(
                    {
                        "hit": True,
                        "title_sim": round(score, 4),
                        "matched_title": record_title(item),
                        "matched_year": record_year(item),
                        "matched_venue": record_venue(item),
                        "matched_author": first_author(item),
                        "year_match": bool(row.get("year")) and record_year(item)[:4] == str(row.get("year"))[:4],
                        "n_results": len(results),
                    }
                )
            else:
                record.update({"hit": False, "title_sim": 0.0, "n_results": 0})
        except Exception as exc:  # noqa: BLE001
            calls += 1
            message = str(exc)
            record.update({"hit": False, "error": f"{type(exc).__name__}: {message[:300]}"})
            if "QUOTA" in message.upper() or "配额" in message:
                quota_hit = True
                processed[str(index)] = record
                break
        processed[str(index)] = record
        STATE_JSON.write_text(
            json.dumps({"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "processed": processed},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        if calls % 10 == 0:
            print(f"{calls} calls, {len(processed)}/{len(candidates)} processed", flush=True)

    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    STATE_JSON.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    done = [v for v in processed.values() if "error" not in v]
    hits = [v for v in done if v.get("hit") and (v.get("title_sim") or 0) >= 0.80]
    strong = [v for v in hits if (v.get("title_sim") or 0) >= 0.92 and v.get("year_match")]
    errors = [v for v in processed.values() if "error" in v]
    summary = {
        "calls_this_run": calls,
        "quota_hit": quota_hit,
        "processed_total": len(processed),
        "candidates_total": len(candidates),
        "hit_0.80": len(hits),
        "strong_0.92_and_year": len(strong),
        "errors": len(errors),
        "hit_rate": round(len(hits) / len(done), 4) if done else 0.0,
        "strong_rate": round(len(strong) / len(done), 4) if done else 0.0,
        "elapsed_s": round(time.time() - started, 1),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if quota_hit else 0


if __name__ == "__main__":
    raise SystemExit(main())
