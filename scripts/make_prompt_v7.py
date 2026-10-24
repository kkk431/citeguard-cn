"""Build scripts/support_prompt_v7.txt = v4 prompt + four worked examples.

v4 has detailed rules but no worked examples; small local judges tend to copy
their stage-1 verdict into the audit step, so examples that contrast
support/partial/contradict/no_evidence are worth testing.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from citeguard import support  # noqa: E402

EXAMPLES = """

示例（照此格式判定）：
【引用句】数字普惠金融显著提高了农村家庭的消费水平。
【证据片段】数字普惠金融的发展与农村家庭消费水平呈正相关，但影响幅度有限，且存在区域差异。
【判定】{"evidence_quote":"呈正相关，但影响幅度有限","label":"partial","confidence":0.9,"reason":"证据只给相关性且幅度有限，没有『显著提高』的因果与量级"}
【引用句】长期睡眠不足会增加心血管疾病风险。
【证据片段】本研究发现，长期睡眠不足者心血管疾病发生率显著高于睡眠充足者。
【判定】{"evidence_quote":"心血管疾病发生率显著高于睡眠充足者","label":"support","confidence":0.95,"reason":"对象、方向与关系一致"}
【引用句】该政策降低了企业创新投入。
【证据片段】该政策实施后企业研发投入显著上升。
【判定】{"evidence_quote":"研发投入显著上升","label":"contradict","confidence":0.95,"reason":"断言方向相反"}
【引用句】教师职业倦怠与班级规模显著负相关。
【证据片段】本文分析了教师职业倦怠的测量工具与信效度。
【判定】{"evidence_quote":"","label":"no_evidence","confidence":0.9,"reason":"证据只讨论测量工具，未涉及班级规模"}
"""


def main() -> int:
    out = os.path.join(ROOT, "scripts", "support_prompt_v7.txt")
    text = support.PROMPT.rstrip() + EXAMPLES
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("[out]", out, len(text), "chars")
    print(text[:120].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
