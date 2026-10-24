"""Build a clean, shareable deliverable zip for CiteGuard-CN.

The archive contains the source tree, tests, docs, scripts, the read-only
CiteBench-CN artifacts and the deployment assets — but **never** secrets or
runtime state:

excluded
    ``.env`` (but ``.env.example`` is kept), ``data/jobs/**``, ``data/cache/**``,
    any cache directory under ``data/`` (name containing ``cache``),
    ``data/uploads/**``, ``__pycache__/``, ``*.pyc``/``*.pyo``, ``.pylibs/``,
    ``dist/``, ``*.log``, ``.git/``, virtualenvs, editor/OS noise.

Usage
    python scripts/package_deliverable.py
    python scripts/package_deliverable.py --name citeguard-cn-0.8.3.zip
    python scripts/package_deliverable.py --root . --out dist --quiet

The script prints the file manifest, the total uncompressed size and the final
zip size + SHA-256, then exits 0. It is import-safe so tests can call
``build_zip`` directly.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import sys
from pathlib import Path
from typing import Iterable, Optional
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "citeguard-cn-0.8.3.zip"

# Directories pruned wherever they appear in the tree.
EXCLUDE_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".pylibs",
    ".venv",
    "venv",
    "env",
    "dist",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
}

# Paths (relative to the project root) pruned together with their contents.
# Third-party raw corpora are downloaded, not redistributed: the evidence JSON
# produced from them stays in the archive, the PDFs/raw dumps do not.
EXCLUDE_DIR_PATHS = {
    "data/jobs",
    "data/cache",
    "data/uploads",
    "data/real_corpus",
    "data/experiments/scifact_raw",
    "out",
}

# File-name globs never shipped.
EXCLUDE_FILE_GLOBS = (
    ".env",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.zip",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
)


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def should_exclude(rel_path: str) -> bool:
    """Return True when a repo-relative POSIX path must not enter the archive."""
    rel_path = rel_path.strip("/")
    if not rel_path:
        return True
    parts = rel_path.split("/")
    if any(part in EXCLUDE_DIR_NAMES for part in parts):
        return True
    if rel_path in EXCLUDE_DIR_PATHS:
        return True
    if any(rel_path.startswith(d + "/") for d in EXCLUDE_DIR_PATHS):
        return True
    # Any cache directory below data/ (e.g. data/citebench_cn/cache,
    # data/experiments/cache_e4, data/experiments/manual_cache).
    if parts[0] == "data" and any("cache" in part.lower() for part in parts[1:-1]):
        return True
    name = parts[-1]
    if any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE_FILE_GLOBS):
        return True
    return False


def collect_files(root: Path) -> list[tuple[Path, str]]:
    """Return ``(absolute_path, repo_relative_path)`` pairs, sorted by path."""
    root = Path(root)
    files: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = _rel(path, root)
        if should_exclude(rel):
            continue
        files.append((path, rel))
    return files


def _human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(num_bytes)} B"


def build_zip(
    root: Path = ROOT,
    out_dir: Optional[Path] = None,
    name: str = DEFAULT_NAME,
    *,
    print_manifest: bool = True,
) -> dict:
    """Create ``<out_dir>/<name>`` and return metadata about the archive."""
    root = Path(root).resolve()
    out_dir = Path(out_dir) if out_dir is not None else root / "dist"
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    files = collect_files(root)
    if not files:
        raise RuntimeError(f"refusing to package an empty tree: {root}")

    zip_path = out_dir / name
    uncompressed = 0
    prefix = root.name or "citeguard"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as zf:
        for abs_path, rel in files:
            zf.write(abs_path, arcname=f"{prefix}/{rel}")
            uncompressed += abs_path.stat().st_size

    zip_size = zip_path.stat().st_size
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    if print_manifest:
        print(f"[package] root: {root}")
        print(f"[package] files: {len(files)}")
        for _abs_path, rel in files:
            print(f"        {rel}")
        print(f"[package] total uncompressed: {_human_size(uncompressed)} ({uncompressed:,} bytes)")
        print(f"[package] zip: {zip_path} ({_human_size(zip_size)}, {zip_size:,} bytes)")
        print(f"[package] sha256: {digest}")

    return {
        "zip_path": zip_path,
        "zip_size": zip_size,
        "uncompressed_size": uncompressed,
        "sha256": digest,
        "files": [rel for _abs, rel in files],
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Package CiteGuard-CN into a clean zip.")
    parser.add_argument("--root", type=Path, default=ROOT, help="project root (default: repo root)")
    parser.add_argument("--out", type=Path, default=None, help="output directory (default: <root>/dist)")
    parser.add_argument("--name", default=DEFAULT_NAME, help=f"zip file name (default: {DEFAULT_NAME})")
    parser.add_argument("--quiet", action="store_true", help="only print the summary lines")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = build_zip(
            root=args.root,
            out_dir=args.out,
            name=args.name,
            print_manifest=not args.quiet,
        )
    except RuntimeError as exc:
        print(f"[package] error: {exc}", file=sys.stderr)
        return 1
    if args.quiet:
        print(
            f"[package] {len(result['files'])} files, "
            f"zip {_human_size(result['zip_size'])}, sha256 {result['sha256'][:12]}…"
        )
        print(f"[package] wrote {result['zip_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

