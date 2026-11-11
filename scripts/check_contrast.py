"""Audit the two themes against WCAG AA contrast thresholds."""
from __future__ import annotations

import json
import re
from pathlib import Path

from citeguard.contrast import contrast_ratio

CSS = Path("web/static/css/refresh.css")


def tokens(block: str, text: str) -> dict[str, str]:
    m = re.search(rf"(?s){re.escape(block)}\s*\{{(.*?)\}}", text)
    rows = re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", m.group(1) if m else "")
    return {k.lstrip("-"): v for k, v in rows}


def main() -> int:
    text = CSS.read_text(encoding="utf-8")
    dark = tokens(":root", text)
    light = tokens("body.theme-light", text)
    pairs = [
        ("ink", "paper", 4.5), ("ink-2", "paper", 4.5), ("muted", "paper", 4.5),
        ("accent", "paper", 3.0), ("accent-ink", "accent", 4.5),
        ("bad", "paper", 3.0), ("warn", "paper", 3.0), ("ok", "paper", 3.0),
        ("ink", "surface", 4.5), ("ink-2", "surface", 4.5),
    ]
    rows = []
    for name, table in (("dark", dark), ("light", light)):
        for fg, bg, need in pairs:
            if fg not in table or bg not in table:
                continue
            ratio = contrast_ratio(table[fg], table[bg])
            rows.append({"theme": name, "fg": fg, "bg": bg, "ratio": round(ratio, 2),
                         "required": need, "pass": ratio + 1e-9 >= need})
    out = Path("data/experiments/contrast_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows, "failed": [r for r in rows if not r["pass"]]},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        mark = "ok" if r["pass"] else "FAIL"
        print(f'{r["theme"]:5} {r["fg"]:10} on {r["bg"]:10} {r["ratio"]:5.2f} (need {r["required"]}) {mark}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
