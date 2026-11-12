"""Measure text-parser vs layout-parser reference sets on the blind-test PDFs.

The product keeps the layout candidate only when its titles are healthier; this
script records both candidates, the old +0.02 gate, and the current rule so the
selection change can be reproduced.  Run from the repo root:

    PYTHONPATH=src python scripts/eval_layout_selection.py
"""
from __future__ import annotations

import json
from pathlib import Path

from citeguard.pdf_extract import extract_text_with_meta, split_references
from citeguard.reference_parser import parse_reference_list
from citeguard.refs_layout import extract_reference_entries, title_health

FOLDERS = ["out/blind_test5", "out/blind_test6"]
OUT = Path("data/experiments/refs_layout_selection.json")


def main() -> None:
    rows = []
    for folder in FOLDERS:
        for p in sorted(Path(folder).glob("*.pdf")):
            text, _meta = extract_text_with_meta(str(p))
            _body, refs_text = split_references(text)
            refs = parse_reference_list(refs_text)
            layout_refs = []
            for entry in extract_reference_entries(str(p)) or []:
                layout_refs.extend(parse_reference_list(entry))
            t_health = title_health(refs)
            l_health = title_health(layout_refs)
            old_gate = (
                len(layout_refs) >= len(refs) and l_health >= t_health + 0.02
            )
            new_rule = (
                len(layout_refs) >= 5
                and len(layout_refs) >= len(refs)
                and (
                    l_health > t_health
                    or (l_health == t_health and len(layout_refs) > len(refs))
                )
            )
            rows.append(
                {
                    "paper": p.stem,
                    "text_refs": len(refs),
                    "text_health": round(t_health, 4),
                    "layout_refs": len(layout_refs),
                    "layout_health": round(l_health, 4),
                    "chosen_old": "layout" if old_gate else "text",
                    "chosen_new": "layout" if new_rule else "text",
                }
            )
    data = {
        "n": len(rows),
        "rule": "layout wins when it has >= entries and strictly better titles, "
        "or equal titles and more entries; old gate required +0.02 health",
        "changed": [r for r in rows if r["chosen_old"] != r["chosen_new"]],
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(
            f"{r['paper']:18s} text={r['text_refs']:3d}/{r['text_health']:.3f}  "
            f"layout={r['layout_refs']:3d}/{r['layout_health']:.3f}  "
            f"old={r['chosen_old']:6s} new={r['chosen_new']}"
        )
    print(f"changed: {len(data['changed'])} -> {OUT}")


if __name__ == "__main__":
    main()
