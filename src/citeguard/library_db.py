"""SQLite sidecar for the local reference library.

``data/library/library.json`` stays the authoritative, human-readable file:
users can inspect, edit and back it up.  Every ``Library.save`` also rewrites a
SQLite sidecar (same path plus ``.sqlite3``) so that a large library can be
queried without parsing the whole JSON and survives an accidentally deleted
JSON.  Loading still prefers JSON, then falls back to the sidecar; nothing is
ever deleted by this module.

The sidecar is an index, not a second source of truth.  If the two disagree
(e.g. the user edited JSON by hand), JSON wins and the next save refreshes the
index.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from .local_library import Library, LibraryEntry

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    norm_title TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]',
    venue TEXT NOT NULL DEFAULT '',
    year INTEGER,
    volume TEXT NOT NULL DEFAULT '',
    issue TEXT NOT NULL DEFAULT '',
    pages TEXT NOT NULL DEFAULT '',
    doi TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    abstract TEXT NOT NULL DEFAULT '',
    doc_type TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'local',
    raw TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_entries_doi ON entries(doi);
CREATE INDEX IF NOT EXISTS idx_entries_year ON entries(year);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _ensure_tags_column(conn: sqlite3.Connection) -> None:
    """Add ``entries.tags`` to a version-1 sidecar in place (idempotent)."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
    if "tags" not in columns:
        conn.execute("ALTER TABLE entries ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
        conn.commit()


def db_path_for(json_path: str | Path) -> Path:
    path = Path(json_path)
    return path.with_name(path.name + ".sqlite3")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    _ensure_tags_column(conn)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('schema', ?)", (str(SCHEMA_VERSION),)
    )
    return conn


def write_library(library: Library, db_path: str | Path) -> Path:
    """Replace the sidecar with the current library (one transaction)."""
    from .metadata_verify import norm_title

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM entries")
        rows = []
        for entry in library.entries:
            key = norm_title(entry.title)
            if not key:
                continue
            rows.append((
                key, entry.title, json.dumps(entry.authors, ensure_ascii=False),
                entry.venue, entry.year, entry.volume, entry.issue, entry.pages,
                entry.doi, entry.url, entry.abstract, entry.doc_type,
                entry.source, entry.raw, json.dumps(list(entry.tags), ensure_ascii=False),
            ))
        conn.executemany(
            "INSERT OR REPLACE INTO entries "
            "(norm_title, title, authors, venue, year, volume, issue, pages, doi, "
            " url, abstract, doc_type, source, raw, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('count', ?)", (str(len(rows)),)
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def read_library(db_path: str | Path) -> Library:
    db_path = Path(db_path)
    if not db_path.exists():
        return Library()
    conn = sqlite3.connect(db_path)
    try:
        _ensure_tags_column(conn)
        rows = conn.execute(
            "SELECT title, authors, venue, year, volume, issue, pages, doi, url, "
            "abstract, doc_type, source, raw, tags FROM entries ORDER BY id"
        ).fetchall()
    except sqlite3.DatabaseError:
        return Library()
    finally:
        conn.close()
    entries: list[LibraryEntry] = []
    for row in rows:
        try:
            authors = json.loads(row[1] or "[]")
        except Exception:
            authors = []
        try:
            tags = json.loads(row[13] or "[]")
        except Exception:
            tags = []
        if not isinstance(tags, list):
            tags = []
        entries.append(LibraryEntry(
            title=row[0], authors=list(authors), venue=row[2], year=row[3],
            volume=row[4], issue=row[5], pages=row[6], doi=row[7], url=row[8],
            abstract=row[9], doc_type=row[10], source=row[11] or "local", raw=row[12],
            tags=[tag for tag in tags if isinstance(tag, str)],
        ))
    return Library(entries)


def count(db_path: str | Path) -> int:
    db_path = Path(db_path)
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(db_path)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return 0


def search(db_path: str | Path, title: str, year: Optional[int] = None,
           limit: int = 5) -> list[tuple[float, LibraryEntry]]:
    """Search the sidecar; fuzzy scoring stays in Python for consistency."""
    from .local_library import Library

    library = read_library(db_path)
    return library.search(title, year=year, limit=limit)


def migrate(json_path: str | Path, db_path: str | Path | None = None) -> dict:
    """Build the sidecar from JSON (JSON untouched; a .bak is written)."""
    json_path = Path(json_path)
    db_path = Path(db_path) if db_path else db_path_for(json_path)
    library = Library.load(json_path)
    if json_path.exists():
        backup = json_path.with_name(json_path.name + ".bak")
        backup.write_bytes(json_path.read_bytes())
    write_library(library, db_path)
    return {
        "json": str(json_path),
        "db": str(db_path),
        "entries": len(library),
        "backup": str(json_path.with_name(json_path.name + ".bak")) if json_path.exists() else "",
    }


def rollback(db_path: str | Path, json_path: str | Path) -> dict:
    """Write JSON from the sidecar (explicit rollback / disaster recovery)."""
    json_path = Path(json_path)
    library = read_library(db_path)
    if not len(library):
        raise ValueError("sidecar has no entries; refusing to overwrite JSON with empty data")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    library.save(json_path)
    return {"json": str(json_path), "entries": len(library)}
