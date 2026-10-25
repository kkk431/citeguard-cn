"""在真实中文参考文献上探测万方题录命中率。

用法（订阅「万方文献检索」后）::

    set WANFANG_APP_KEY=...            # Windows
    export WANFANG_APP_KEY=...         # bash
    python scripts/probe_wanfang.py --limit 20
    python scripts/probe_wanfang.py --json out/wanfang_probe.json

输入默认取 ``data/experiments/verify_real.json`` 里解析成功的中文条目
（标题含 CJK 且无 DOI 的条目），逐条用「Title:标题」检索并算标题相似度，
只输出聚合结果，不打印题录全文，避免把第三方数据写进日志。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from citeguard import wanfang  # noqa: E402
from citeguard.metadata_verify import norm_title, title_sim  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")


def _load_refs(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("rows") or data.get("items") or (data if isinstance(data, list) else [])
    rows: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ref = item.get("reference") if isinstance(item.get("reference"), dict) else item
        title = (ref.get("title") or "").strip()
        if title and CJK.search(title) and not ref.get("doi"):
            rows.append(ref)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "data/experiments/verify_real.json"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    if not wanfang.available():
        print("未配置 WANFANG_APP_KEY；先在 https://ai.wfdata.com/api-detail?id=17 订阅接口并设置环境变量。")
        return 2
    refs = _load_refs(Path(args.input))[: args.limit]
    if not refs:
        print("没有可探测的中文条目（检查输入文件）")
        return 1

    hits = 0
    exact = 0
    details = []
    try:
        for ref in refs:
            title = (ref.get("title") or "").strip()
            records = wanfang.search(f"Title:{title}", rows=args.rows)
            best = None
            for record in records:
                cand = wanfang.record_to_candidate_fields(record)
                sim = title_sim(norm_title(title), norm_title(cand["title"] or ""))
                if best is None or sim > best[0]:
                    best = (sim, cand)
            hit = bool(best and best[0] >= 0.85)
            hits += int(hit)
            exact += int(bool(best and best[0] >= 0.97))
            details.append({"title": title[:80], "best_sim": round(best[0], 3) if best else 0.0, "hit": hit})
    except wanfang.WanfangNotSubscribed as exc:
        print(f"接口未订阅：{exc}")
        return 3
    except wanfang.WanfangError as exc:
        print(f"万方调用失败：{exc}")
        return 4

    summary = {
        "probed": len(refs),
        "hit_0.85": hits,
        "exact_0.97": exact,
        "hit_rate": round(hits / len(refs), 3),
        "details": details,
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "details"}, ensure_ascii=False, indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"written {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
