"""Per-report triage state: todo / fixed / ignored.

The state is deliberately kept next to the job data rather than in the report
JSON: a re-run of the same PDF produces a new report, and the old triage notes
must not be silently copied onto a different verdict set.  When the user runs a
re-check, `auto_mark_fixed` closes entries that the diff reports as fixed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import config

STATES = ("todo", "fixed", "ignored")
LABELS = {"todo": "待修", "fixed": "已修", "ignored": "忽略"}
_JOB_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _dir() -> Path:
    return config.DATA_DIR / "triage"


def _path(job_id: str) -> Path:
    if not _JOB_RE.match(job_id or ""):
        raise ValueError("invalid job id")
    return _dir() / f"{job_id}.json"


def _empty() -> dict:
    return {"items": {}, "updated_at": ""}


def _load_raw(job_id: str) -> dict:
    p = _path(job_id)
    if not p.exists():
        return _empty()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _empty()
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    return data


def _write(job_id: str, data: dict) -> None:
    _dir().mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = _path(job_id)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _clean_note(note: str) -> str:
    return (note or "").strip()[:500]


def load(job_id: str) -> dict:
    data = _load_raw(job_id)
    counts = {state: 0 for state in STATES}
    for item in data["items"].values():
        state = item.get("state")
        if state in counts:
            counts[state] += 1
    return {
        "items": data["items"],
        "counts": counts,
        "auto_fixed": data.get("auto_fixed") or 0,
        "updated_at": data.get("updated_at") or "",
    }


def set_state(job_id: str, index: int, state: str, note: str = "") -> dict:
    if state not in STATES:
        raise ValueError(f"state must be one of {STATES}")
    if not isinstance(index, int) or index < 1:
        raise ValueError("index must be a positive integer")
    data = _load_raw(job_id)
    data["items"][str(index)] = {
        "state": state,
        "note": _clean_note(note),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write(job_id, data)
    return load(job_id)


def auto_mark_fixed(job_id: str, fixed_indexes: list[int]) -> int:
    """Mark re-checked entries as fixed, unless the user explicitly ignored them."""
    if not fixed_indexes:
        return 0
    data = _load_raw(job_id)
    changed = 0
    for idx in fixed_indexes:
        key = str(idx)
        item = data["items"].get(key) or {}
        if item.get("state") == "ignored":
            continue
        if item.get("state") == "fixed":
            continue
        data["items"][key] = {
            "state": "fixed",
            "note": "复检 diff 自动标记",
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        changed += 1
    if changed:
        data["auto_fixed"] = int(data.get("auto_fixed") or 0) + changed
        _write(job_id, data)
    return changed
