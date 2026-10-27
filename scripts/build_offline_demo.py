"""Build the self-contained offline demo pack under ``samples/offline_demo/``.

The pack exists so a judge can see a complete analysis with **no network at all**:
a short Chinese body, ten real reference entries (taken from an open-access
paper's bibliography) and a matching RIS library. The last entry is deliberately
fictional and is *not* in the library, so the demo also shows the honest
"未核实" state.

Run::

    python scripts/build_offline_demo.py

The script needs ``data/real_corpus/hanspub_152575.pdf`` (not tracked); the
generated files under ``samples/offline_demo/`` ARE tracked.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from citeguard.exporters import refs_to_ris
from citeguard.pdf_extract import extract_text_with_meta
from citeguard.pipeline import split_references
from citeguard.reference_parser import parse_reference_list

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data" / "real_corpus" / "hanspub_152575.pdf"
OUT = ROOT / "samples" / "offline_demo"

BODY = """中文引文核验离线演示（正文为演示而写，题录均取自公开论文）

人工智能在电商领域的应用越来越广[1]。已有研究从用户行为角度分析了推荐系统的作用[2]，也有工作关注平台治理与隐私保护[3]。在方法层面，图神经网络被用于建模用户—商品关系[4]，而大语言模型为评论理解提供了新工具[5]。不过，现有综述对中文场景的覆盖仍然有限[6]。本文进一步比较了不同方法的适用边界[7]，并讨论了数据质量对结论的影响[8]。最后，我们给出一个可复现的实验流程[9]，以及一个面向中文语料的扩展方向[10]。

另有一条演示用虚构条目[11]，故意不在本地题录库中，用来展示「未核实」而不是被误判为「严重不符」。

参考文献
"""


def main() -> None:
    if not PDF.exists():
        raise SystemExit(f"missing source PDF: {PDF}")
    text, _ = extract_text_with_meta(str(PDF))
    _, raw_refs = split_references(text)
    refs = parse_reference_list(raw_refs)
    chosen, seen = [], set()
    for ref in refs:
        if not ref.title or not ref.authors:
            continue
        key = ref.title.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(ref)
        if len(chosen) == 10:
            break
    if len(chosen) < 10:
        raise SystemExit(f"only {len(chosen)} usable references")
    raw_entries = [re.sub(r"^\[\d+\]\s*", "", r.raw.strip()) for r in chosen]
    raw_entries.append("张某某. 虚构的演示条目：仅用于展示未核实状态[J]. 演示学报, 2024, 1(1): 1-2.")
    numbers = "\n".join(f"[{i}] {entry}" for i, entry in enumerate(raw_entries, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "paper.txt").write_text(BODY + numbers + "\n", encoding="utf-8")
    (OUT / "library.ris").write_text(refs_to_ris(chosen), encoding="utf-8")
    meta = {
        "source": "https://doi.org/10.12677/... (open-access paper bibliography, metadata only)",
        "real_refs": len(chosen),
        "fictional_refs": 1,
        "note": "题录为真实公开文献的元数据；正文句子和最后 1 条题录为演示虚构，不用于任何评测。",
    }
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} ({len(chosen)} real + 1 fictional)")


if __name__ == "__main__":
    main()
