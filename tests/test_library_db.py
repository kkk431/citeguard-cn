import json

from citeguard import config
from citeguard.library_db import (
    count,
    db_path_for,
    migrate,
    read_library,
    rollback,
    search,
    write_library,
)
from citeguard.local_library import Library, LibraryEntry


def make_library():
    return Library([
        LibraryEntry(title="人工智能发展对教育公平的影响研究", authors=["伍麟", "严昊东"],
                     venue="教育研究", year=2023, doi="10.1234/edu.2023.1"),
        LibraryEntry(title="深度学习在医学影像中的应用", authors=["张三"],
                     venue="中国医学影像学杂志", year=2021),
    ])


def test_sidecar_roundtrip_and_json_fallback(tmp_path):
    path = tmp_path / "library.json"
    lib = make_library()
    lib.save(path)
    db = db_path_for(path)
    assert db.exists()
    assert count(db) == 2
    assert len(Library.load(path)) == 2

    path.unlink()
    restored = Library.load(path)
    assert len(restored) == 2
    assert restored.entries[0].title == "人工智能发展对教育公平的影响研究"
    assert restored.entries[0].authors == ["伍麟", "严昊东"]


def test_migrate_and_rollback_keep_backup(tmp_path):
    path = tmp_path / "library.json"
    make_library().save(path)
    db = db_path_for(path)
    result = migrate(path, db)
    assert result["entries"] == 2
    assert (tmp_path / "library.json.bak").exists()

    # remove JSON, then roll back from the sidecar
    path.unlink()
    out = rollback(db, path)
    assert out["entries"] == 2
    assert json.loads(path.read_text(encoding="utf-8"))["count"] == 2


def test_sidecar_dedupes_doi(tmp_path):
    path = tmp_path / "library.json"
    lib = Library()
    lib.add([
        LibraryEntry(title="同名期刊论文一", doi="10.5555/ABC"),
        LibraryEntry(title="同名期刊论文二", doi="10.5555/abc"),
    ])
    assert len(lib) == 1
    lib.save(path)
    assert count(db_path_for(path)) == 1


def test_corrupt_sidecar_does_not_break_load(tmp_path):
    path = tmp_path / "library.json"
    make_library().save(path)
    db = db_path_for(path)
    db.write_bytes(b"not a sqlite database")
    path.unlink()
    restored = Library.load(path)
    assert len(restored) == 0  # honest empty, no exception


def test_sidecar_search(tmp_path):
    path = tmp_path / "library.json"
    make_library().save(path)
    hits = search(db_path_for(path), "人工智能发展对教育公平的影响研究", year=2023)
    assert hits and hits[0][1].year == 2023
    assert hits[0][0] > 0.9
