"""Offline smoke test for the reference parser (no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from citeguard.reference_parser import parse_intext_citations, parse_reference  # noqa: E402

SAMPLES = [
    "[1] 张三, 李四, 王五. 基于深度学习的中文文本分类研究[J]. 计算机学报, 2021, 44(3): 123-135. DOI: 10.11897/SP.J.1016.2021.00123.",
    "[2] 李明. 机器学习方法[M]. 北京: 清华大学出版社, 2020: 45-60.",
    "[3] 王芳. 面向教育的人工智能应用研究[D]. 上海: 华东师范大学, 2022.",
    "[4] 陈刚, 刘洋. 大数据时代的信息检索[J]. 情报学报, 2019, 38(5): 10-20.",
    "[5] GB/T 7714-2025 信息与文献 参考文献著录规则[S]. 北京: 中国标准出版社, 2025.",
    "[6] 赵强. 面向听障学生的课堂字幕系统设计[J/OL]. 现代教育技术, 2023, 33(4): 88-95[2026-10-20]. https://example.org/paper/123.",
    "SMITH J, LEE K. A survey of citation verification[J]. Journal of Informetrics, 2022, 16(2): 101-120.",
]


def main() -> None:
    for s in SAMPLES:
        r = parse_reference(s)
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=1))
        print("-" * 60)

    body = "已有研究表明该方法有效[1]。张三等[2]进一步指出……（李四, 2021）。另见[3-5]。"
    print("in-text:", json.dumps([c.__dict__ for c in parse_intext_citations(body)], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
