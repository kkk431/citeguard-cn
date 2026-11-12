"""Evaluate retraction detection against OpenAlex's own retraction flag.

This is a data-source agreement test, not an independent ground truth: both the
sample labels and our check read OpenAlex. It answers one narrow question — when
OpenAlex marks a work retracted, does our report surface it (and does a normal
work stay quiet)? A Crossref update relation alone is reported separately and is
not counted as a false positive.

Run:  PYTHONPATH=src python scripts/eval_retraction.py [--n 100]
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from citeguard.metadata_verify import _cached_json
from citeguard.retraction import check_doi, normalise_doi


def sample(n: int, retracted: bool) -> list[dict]:
    """OpenAlex sample of works with/without the retracted flag."""
    out: list[dict] = []
    cursor = "*"
    while len(out) < n and cursor:
        params = {
            "filter": f"is_retracted:{'true' if retracted else 'false'},has_doi:true",
            "per-page": min(100, n - len(out)),
            "cursor": cursor,
            "select": "doi,title,is_retracted",
        }
        resp = requests.get("https://api.openalex.org/works", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for work in data.get("results") or []:
            doi = normalise_doi(work.get("doi") or "")
            if doi:
                out.append({"doi": doi, "title": work.get("title") or ""})
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.2)
    return out[:n]


def run(items: list[dict], workers: int = 4) -> list[dict]:
    results: list[dict] = [{}] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_doi, item["doi"]): i for i, item in enumerate(items)}
        for future in futures:
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as exc:  # pragma: no cover - network path
                results[i] = {"status": "error", "detail": str(exc)}
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--out", default="data/experiments/retraction_eval.json")
    args = parser.parse_args()

    retracted = sample(args.n, True)
    control = sample(args.n, False)
    print(f"sampled retracted={len(retracted)} control={len(control)}")

    started = time.monotonic()
    retracted_results = run(retracted)
    control_results = run(control)
    elapsed = round(time.monotonic() - started, 1)

    def counts(results: list[dict]) -> dict:
        out: dict[str, int] = {}
        for item in results:
            status = item.get("status") or "error"
            out[status] = out.get(status, 0) + 1
        return out

    retracted_counts = counts(retracted_results)
    control_counts = counts(control_results)
    detect = retracted_counts.get("retracted", 0)
    checked = len(retracted) - retracted_counts.get("error", 0)
    fp = control_counts.get("retracted", 0)
    report = {
        "sampled": {"retracted": len(retracted), "control": len(control)},
        "retracted_counts": retracted_counts,
        "control_counts": control_counts,
        "recall_on_checked": round(detect / checked, 4) if checked else None,
        "recall_all": round(detect / len(retracted), 4) if retracted else None,
        "false_positive_rate": round(fp / len(control), 4) if control else None,
        "elapsed_s": elapsed,
        "boundary": "OpenAlex is both the sample label and the check source; "
        "this measures agreement with that flag, not independent truth. "
        "Crossref corrections are counted separately, not as false positives.",
        "samples": {
            "retracted": [
                {"doi": item["doi"], "title": item["title"], "status": res.get("status")}
                for item, res in zip(retracted, retracted_results)
            ][:20],
            "control": [
                {"doi": item["doi"], "title": item["title"], "status": res.get("status")}
                for item, res in zip(control, control_results)
            ][:20],
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
