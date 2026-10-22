"""Demo: how CiteGuard decides whether a citation is real.

Run:  PYTHONPATH=src python3 scripts/demo_verify.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from citeguard.metadata_verify import verify_reference  # noqa: E402
from citeguard.reference_parser import parse_reference  # noqa: E402

REFS = [
    (
        "real_with_doi",
        "[1] 中国疾病预防控制中心. 新型冠状病毒肺炎流行病学特征分析[J]. 中华流行病学杂志, 2020, 41(2): 145-151. "
        "DOI: 10.3760/cma.j.issn.0254-6450.2020.02.003.",
    ),
    (
        "real_but_wrong_year",
        "[2] 中国疾病预防控制中心. 新型冠状病毒肺炎流行病学特征分析[J]. 中华流行病学杂志, 2019, 41(2): 145-151. "
        "DOI: 10.3760/cma.j.issn.0254-6450.2020.02.003.",
    ),
    (
        "fabricated",
        "[3] 张三, 李四. 基于量子纠缠的中文引文核验方法[J]. 计算机学报, 2024, 47(1): 1-10. "
        "DOI: 10.9999/fake.2024.001.",
    ),
]


def main() -> None:
    for name, s in REFS:
        ref = parse_reference(s)
        v = verify_reference(ref)
        print(f"\n[{name}]")
        print(f"  parsed title : {ref.title}")
        print(f"  parsed year  : {ref.year}   doi: {ref.doi}")
        print(f"  status       : {v.status}")
        print(f"  title_sim    : {v.title_sim}   year_match: {v.year_match}   author_match: {v.author_match}")
        print(f"  notes        : {'; '.join(v.notes)}")
        if v.best:
            print(f"  best match   : {v.best.source} | {v.best.title[:90]} | {v.best.year} | {v.best.doi}")


if __name__ == "__main__":
    main()
