"""Compact parser check: prints one line per sample."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from citeguard.reference_parser import parse_reference  # noqa: E402

SAMPLES = [
    "[1] 张三, 李四, 王五. 基于深度学习的中文文本分类研究[J]. 计算机学报, 2021, 44(3): 123-135. DOI: 10.11897/SP.J.1016.2021.00123.",
    "[2] 李明. 机器学习方法[M]. 北京: 清华大学出版社, 2020: 45-60.",
    "[3] 王芳. 面向教育的人工智能应用研究[D]. 上海: 华东师范大学, 2022.",
    "[4] 陈刚, 刘洋. 大数据时代的信息检索[J]. 情报学报, 2019, 38(5): 10-20.",
    "[5] GB/T 7714-2025 信息与文献 参考文献著录规则[S]. 北京: 中国标准出版社, 2025.",
    "[6] 赵强. 面向听障学生的课堂字幕系统设计[J/OL]. 现代教育技术, 2023, 33(4): 88-95[2026-10-20]. https://example.org/paper/123.",
    "SMITH J, LEE K. A survey of citation verification[J]. Journal of Informetrics, 2022, 16(2): 101-120.",
    "[8] 周敏. 中文引文核验方法研究[D]. 北京: 北京大学, 2024. DOI: 10.1234/abcd.2024.001.",
    "[9] 孙丽, 王强. 面向学术诚信的引文分析[J]. 图书情报工作, 2023, 67(12): 45-56.",
    "[10] 吴磊. 数据集构建方法[DS/OL]. 版本 1.0. 国家科学数据中心(2024-01-01)[2026-10-20]. https://data.example.cn/x.",
]


def main() -> None:
    for s in SAMPLES:
        r = parse_reference(s)
        print(
            f"idx={r.index} type={r.doc_type!r} authors={r.authors} "
            f"title={r.title!r} venue={r.venue!r} year={r.year} "
            f"vol={r.volume!r} issue={r.issue!r} pages={r.pages!r} "
            f"doi={r.doi!r} std={r.standard_no!r} url={r.url!r}"
        )


if __name__ == "__main__":
    main()
