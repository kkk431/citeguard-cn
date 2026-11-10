"""On-disk cache for PDF text extraction.

Parsing the same PDF repeatedly (job retries, demos, benchmarks) spends most
of its time in the text layer; the result is deterministic for a given file
and extractor version, so cache it keyed by content hash.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import zlib
from pathlib import Path

CACHE_VERSION = 1


def _cache_dir() -> Path:
    return Path(os.environ.get("CITEGUARD_TEXT_CACHE_DIR", "data/cache/text"))


def cache_enabled() -> bool:
    return os.environ.get("CITEGUARD_TEXT_CACHE", "1") not in {"0", "false", "no"}


def file_digest(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:32]


def _slot(path: str | Path, cache_dir: Path | None = None) -> Path:
    root = cache_dir or _cache_dir()
    return root / (file_digest(path) + ".json")


def load_text(path: str | Path, cache_dir: Path | None = None):
    """Return (text, meta) from cache, or None."""
    try:
        raw = json.loads(_slot(path, cache_dir).read_text(encoding="utf-8"))
        if raw.get("version") != CACHE_VERSION:
            return None
        text = zlib.decompress(base64.b64decode(raw["text"])).decode("utf-8")
        return text, dict(raw.get("meta") or {})
    except Exception:
        return None


def save_text(path: str | Path, text: str, meta: dict, cache_dir: Path | None = None) -> None:
    try:
        slot = _slot(path, cache_dir)
        slot.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CACHE_VERSION,
            "text": base64.b64encode(zlib.compress((text or "").encode("utf-8"))).decode("ascii"),
            "meta": meta,
        }
        slot.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass
