"""Inspect or roll back the optional SQLite sidecar for the reference library.

    python scripts/migrate_library_sqlite.py --check
    python scripts/migrate_library_sqlite.py --rollback

JSON stays authoritative. ``--rollback`` refuses to overwrite JSON when the
sidecar is empty, so a broken index cannot erase a user's library.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from citeguard import config  # noqa: E402
from citeguard.library_db import (  # noqa: E402
    count,
    db_path_for,
    migrate,
    read_library,
    rollback,
    write_library,
)
from citeguard.local_library import Library  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(config.LIBRARY_FILE))
    ap.add_argument("--db")
    ap.add_argument("--check", action="store_true", help="build/refresh and report parity")
    ap.add_argument("--rollback", action="store_true", help="write JSON from the sidecar")
    args = ap.parse_args()

    json_path = Path(args.json)
    db_path = Path(args.db) if args.db else db_path_for(json_path)

    if args.rollback:
        try:
            result = rollback(db_path, json_path)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False))
        return 0

    library = Library.load(json_path)
    new_json = not json_path.exists()
    write_library(library, db_path)
    payload = {
        "json": str(json_path),
        "db": str(db_path),
        "json_entries": len(library),
        "db_entries": count(db_path),
        "db_read_entries": len(read_library(db_path)),
        "json_created": new_json,
        "has_backup": json_path.with_name(json_path.name + ".bak").exists(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0 if payload["db_entries"] == len(library) else 1


if __name__ == "__main__":
    raise SystemExit(main())
