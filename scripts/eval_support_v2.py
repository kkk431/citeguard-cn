"""Evaluate the 140-item ClaimSupport-CN-V2 with the product judge (v10)."""
from __future__ import annotations
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from citeguard import support  # noqa: E402

DATA = ROOT / "data" / "claimsupport_cn" / "claimsupport_cn_v2.jsonl"
OUT = ROOT / "data" / "experiments" / "claimsupport_v2_140.json"
LABELS = ["support", "partial", "contradict", "no_evidence"]


def metrics(rows, preds):
    idx = {l: i for i, l in enumerate(LABELS)}
    cm = [[0]*4 for _ in range(4)]
    for r, p in zip(rows, preds):
        cm[idx[r["label"]]][idx[p]] += 1
    f1s, per = [], {}
    for i, l in enumerate(LABELS):
        tp = cm[i][i]; fp = sum(cm[r][i] for r in range(4)) - tp; fn = sum(cm[i]) - tp
        p = tp/(tp+fp) if tp+fp else 0.0; rec = tp/(tp+fn) if tp+fn else 0.0
        f = 2*p*rec/(p+rec) if p+rec else 0.0
        f1s.append(f); per[l] = {"precision": round(p,4), "recall": round(rec,4), "f1": round(f,4)}
    return {"macro_f1": round(sum(f1s)/4,4), "accuracy": round(sum(cm[i][i] for i in range(4))/len(rows),4), "confusion": cm, "per_class": per}


def one(item):
    claim = item["claim"]; evidence = item["evidence"]
    res = support.judge_support(claim, evidence)
    label = (res or {}).get("label") or "no_evidence"
    return label if label in LABELS else "no_evidence"


def main():
    rows = [json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x.strip()]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        preds = list(ex.map(one, rows))
    m = metrics(rows, preds)
    result = {"n": len(rows), "prompt_version": support.PROMPT_VERSION, "elapsed_s": round(time.time()-t0,1), **m,
              "items": [{"id": r["id"], "label": r["label"], "pred": p} for r, p in zip(rows, preds)]}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("n","macro_f1","accuracy","confusion","elapsed_s")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
