"""判错反馈本地队列（Phase 1）。

用户在报告里点“判错了”时，把 (任务号, 条目号, 引用句, 原判, 正确标签, 备注)
追加到本地 JSONL。默认不联网、不上传；导出时由用户显式带走。

存储：``data/feedback/feedback.jsonl``（gitignore），一行一条；可用
``CITEGUARD_FEEDBACK_FILE`` 改路径。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import threading
from pathlib import Path

from . import config

LABELS = {"support", "partial", "contradict", "no_evidence", "not_checked"}
_CORRECTABLE = LABELS | {"other"}

_LOCK = threading.Lock()


def default_path() -> Path:
    env = os.environ.get("CITEGUARD_FEEDBACK_FILE")
    if env:
        return Path(env)
    return Path(config.DATA_DIR) / "feedback" / "feedback.jsonl"


def record_feedback(payload: dict, path: Path | str | None = None) -> dict:
    """校验并追加一条反馈，返回落盘后的记录。"""
    item = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "job_id": str(payload.get("job_id") or "")[:64],
        "ref_index": int(payload.get("ref_index") or 0),
        "claim": str(payload.get("claim") or "")[:500],
        "predicted": str(payload.get("predicted") or ""),
        "corrected": payload.get("corrected"),
        "reason": str(payload.get("reason") or "")[:500],
        "source": str(payload.get("source") or "report")[:32],
    }
    if item["predicted"] not in LABELS:
        raise ValueError("predicted 必须是四个支持度标签之一")
    if item["corrected"] is not None:
        item["corrected"] = str(item["corrected"])
        if item["corrected"] not in _CORRECTABLE:
            raise ValueError("corrected 标签不合法")
    if item["ref_index"] < 0:
        raise ValueError("ref_index 不能为负")
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(item, ensure_ascii=False)
    with _LOCK:
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return item


def load_feedback(path: Path | str | None = None) -> list[dict]:
    p = Path(path) if path else default_path()
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def summarize_feedback(items: list[dict]) -> dict:
    corrections: dict[str, int] = {}
    for it in items:
        if it.get("corrected"):
            corrections[it["corrected"]] = corrections.get(it["corrected"], 0) + 1
    return {
        "total": len(items),
        "jobs": len({it.get("job_id") for it in items if it.get("job_id")}),
        "corrections": corrections,
        "latest": items[-1]["ts"] if items else None,
    }
