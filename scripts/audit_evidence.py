"""Audit docs/evidence_index.md: every backticked path must exist on disk."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "evidence_index.md"
SHOTS = ROOT / "docs" / "evidence" / "shots"
OUT = ROOT / "data" / "experiments" / "evidence_audit.json"

PATH_RE = re.compile(r"`([^`]+)`")


def main() -> int:
    text = INDEX.read_text(encoding="utf-8")
    rows = []
    paths: list[str] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        for raw in PATH_RE.findall(line):
            candidate = raw.strip()
            if " " in candidate and not Path(candidate).exists():
                # 一行命令里夹着的路径不单独校验，交给行内其它路径
                continue
            if "/" not in candidate:
                # 裸文件名（如证据包里的 report.json）不是仓库路径，跳过
                continue
            if any(c in candidate for c in ("*", "?", "→")):
                continue
            if not (candidate.endswith(".json") or candidate.endswith(".png") or candidate.endswith(".md")
                    or candidate.endswith(".txt") or candidate.endswith(".csv") or candidate.endswith(".pdf")):
                continue
            if candidate.startswith(("http://", "https://")):
                continue
            paths.append(candidate)
            if line.lstrip().startswith("| E"):
                rows.append({"evidence": line.split("|")[1].strip(), "path": candidate,
                             "exists": (ROOT / candidate).exists()})

    unique = sorted(set(paths))
    missing = sorted({p for p in unique if not (ROOT / p).exists()})
    registered = {Path(p).name for p in unique if p.startswith("docs/evidence/shots/")}
    unregistered_shots = sorted(
        p.name for p in SHOTS.glob("*.png") if p.name not in registered
    ) if SHOTS.exists() else []

    report = {
        "index": str(INDEX.relative_to(ROOT)).replace("\\", "/"),
        "paths_checked": len(unique),
        "missing": missing,
        "rows": rows,
        "shots_registered": len(registered),
        "shots_unregistered": unregistered_shots,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"paths checked: {len(unique)}")
    print(f"missing: {len(missing)}")
    for p in missing:
        print("  MISSING", p)
    print(f"shots registered: {len(registered)}; unregistered: {len(unregistered_shots)}")
    for p in unregistered_shots:
        print("  UNREGISTERED", p)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
