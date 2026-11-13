"""Build the human blind-audit kit from the existing 60-item audit sheet.

Outputs (under ``dist/audit_kit`` by default):
  instructions_给标注者.md   one-page rules + decision order + edge cases
  practice.csv               5 calibration items with answers
  practice_answers.md        answers and one-line reasons
  audit_A.csv / B / C        same 60 items, three different random orders
  README_组织者.md           what to send, how to collect and score
  _organizer_only/audit_key.json   constructed key (never send to annotators)

The key is the *constructed* label used to build the sample; it is not human
ground truth.  Human majority after adjudication is the gold set.
"""

from __future__ import annotations

import csv
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SOURCE_SHEET = ROOT / "data" / "audit" / "audit_sheet_100.csv"
SOURCE_KEY = ROOT / "data" / "audit" / "audit_key_100.json"
DEFAULT_OUT = ROOT / "dist" / "audit_kit"

INSTRUCTIONS = """# 引文支持度盲标说明（100 条，约 1.5–2 小时）

你的任务：判断 **给出的证据（evidence）是否支持这句话（claim）**。只依据 evidence，不查资料、不看模型结果、不和别人讨论。

## 四个标签

- `support`：证据明确支持该结论；方向、数字、范围一致，没有明显外推。
- `partial`：有支持，但范围/强度/条件不完全一致。例：证据说“可能”，结论说“会”；证据只覆盖亚组，结论推全体；只支持结论的一部分。
- `contradict`：证据与结论方向相反，或关键数字矛盾。
- `no_evidence`：证据没谈到该结论，或信息不足无法判断（例如只给了题名、摘要缺关键结果）。

## 判定顺序

1. 证据是否在谈这个结论？否 → `no_evidence`。
2. 证据是否与结论相反？是 → `contradict`。
3. 证据是否明确、完整地支持？是 → `support`。
4. 以上都不是 → `partial`。

## 边界规则

- 只判断“证据 vs 这句话”，不评价论文整体质量。
- 相关性、动物/细胞实验、不同人群、不同时间段被写成确定因果 → 至少 `partial`。
- 证据写“无显著差异”，结论写“有效/更高” → `contradict`。
- 证据只提到概念、没有结果数字，无法判断 → `no_evidence`。
- 不要用领域常识替证据补全；证据没写就是没写。
- 数字单位、样本量、时间范围不一致 → 至少 `partial`。

## 怎么填

每行填三列：

- `human_label`：四选一，只能填英文标签本身。
- `confidence_1_5`：1=猜的，3=比较有把握，5=很确定。
- `note`：一句话理由，尤其 `partial` / `contradict` / `no_evidence`；不确定也写。

不要改 `item_id`、`claim`、`evidence`，不要增删行，不要改列名。
填完保存为发给你的文件名（如 `audit_A.csv`），只交这一份 CSV。

## 先做 5 条练习题

打开 `practice.csv`，按上面规则填 `human_label`，然后对照 `practice_answers.md`。
如果 5 条里错 2 条以上，先重读“判定顺序”和“边界规则”，再开始正式 100 条。
如果不知道最后三列怎么填，先看 `demo_填写示例.csv`（已填好 3 条）。

## 时间与提交

- 建议分 2–3 次完成（每次 30–40 条），避免疲劳。
- 3 天内交回；中途不要改已提交的标签。
- 有疑问写在 `note`，不要空着。
"""

PRACTICE = [
    {
        "item_id": "P1",
        "claim": "每周进行 150 分钟中等强度运动可以降低心血管疾病风险。",
        "evidence": "一项纳入 12 万人的前瞻性队列研究显示，每周 150 分钟中等强度运动与心血管事件风险下降 20% 相关（HR 0.80, 95% CI 0.74–0.86）。",
        "answer": "support",
        "reason": "证据给出了同方向、同剂量的风险下降，属于明确支持。",
    },
    {
        "item_id": "P2",
        "claim": "该药物对所有糖尿病患者都能有效降低血糖。",
        "evidence": "在一项针对 2 型糖尿病患者的随机试验中，该药物使 HbA1c 平均下降 0.4%，1 型糖尿病和其他人群未纳入研究。",
        "answer": "partial",
        "reason": "只支持 2 型糖尿病亚组，结论外推到“所有糖尿病患者”。",
    },
    {
        "item_id": "P3",
        "claim": "增加每周课时可以显著提高学生数学成绩。",
        "evidence": "一项整群随机试验发现，增加课时组与对照组的期末数学成绩差异无统计学意义（p=0.42）。",
        "answer": "contradict",
        "reason": "证据说无显著差异，结论说显著提高。",
    },
    {
        "item_id": "P4",
        "claim": "AI 辅导能提高农村学生的数学成绩。",
        "evidence": "该文调查了城市中学教师对教育信息化的态度，发现教师使用平板教学的意愿与学校支持力度相关。",
        "answer": "no_evidence",
        "reason": "证据谈教师态度，没有涉及农村学生或数学成绩。",
    },
    {
        "item_id": "P5",
        "claim": "模型 A 的准确率高于模型 B。",
        "evidence": "在同一测试集上，模型 A 的准确率为 0.81，模型 B 为 0.83。",
        "answer": "contradict",
        "reason": "数字方向与结论相反。",
    },
]

ORGANIZER = """# 盲标包使用说明（组织者）

## 包里有什么

- `instructions_给标注者.md`：一页规则，发给每位标注者。
- `practice.csv` + `practice_answers.md`：5 条校准题，发给标注者。
- `audit_A.csv` / `audit_B.csv` / `audit_C.csv`：同一批 100 条，三种随机顺序；每人只发自己那一份。
- `_organizer_only/audit_key.json`：**构造标签，不是人工金标**；绝对不要发给标注者。

## 发放

1. 找 3 位同领域研究生/青年科研人员，非本项目成员。
2. 每人发：`instructions_给标注者.md` + `practice.csv` + `practice_answers.md` + 自己的 `audit_X.csv`。
3. 明确：独立完成、不讨论、不查外部资料、不看模型结果；3 天内交回。
4. 只回收 CSV，文件名不变。

## 回收后评分

在本仓库根目录运行（需要 Python + 本仓库依赖）：

```powershell
$env:PYTHONPATH='src'
python scripts/score_audit_kit.py --kit dist/audit_kit --out dist/audit_kit/_results
```

脚本会自动读取 `audit_A/B/C.csv`，输出：

- `agreement_report.json`：覆盖率、两两 Cohen's κ、Fleiss κ、多数票分布、分歧数、与构造标签的参考一致率。
- `human_gold.csv`：多数票金标；平票条目标 `needs_adjudication=True`，`final_label` 留空。
- `disagreements.csv`：所有不一致条目 + 每人 note，供你仲裁。

## 仲裁

- 两人一致、一人不同：多数票即金标，保留少数意见。
- 三人各不相同：你 + 1 位标注者讨论，写入 `final_label`；不要回头改原始三份 CSV。
- 平票条目在 `human_gold.csv` 里补 `final_label` 后再用于评测。

## 写作口径

- 对外只能写“100 条、3 人独立盲标、Fleiss κ=…、其中 N 条仲裁”。
- 不能写“人工金标准覆盖 300 条”，也不能把构造标签说成人审。
- 标注者个人信息不采集；CSV 只含编号与判断。
"""


def read_rows() -> list[dict[str, str]]:
    with SOURCE_SHEET.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 100:
        raise SystemExit(f"expected 100 audit rows, found {len(rows)}")
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "item_id",
        "claim",
        "evidence",
        "source_title",
        "human_label",
        "confidence_1_5",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def main() -> int:
    out = DEFAULT_OUT
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    rows = read_rows()
    for row in rows:
        row["human_label"] = ""
        row["confidence_1_5"] = ""
        row["note"] = ""

    write_csv(
        out / "practice.csv",
        [
            {
                "item_id": item["item_id"],
                "claim": item["claim"],
                "evidence": item["evidence"],
                "source_title": "",
                "human_label": "",
                "confidence_1_5": "",
                "note": "",
            }
            for item in PRACTICE
        ],
    )
    answers = ["# 练习题答案", ""]
    for item in PRACTICE:
        answers.append(f"## {item['item_id']} — `{item['answer']}`")
        answers.append("")
        answers.append(item["reason"])
        answers.append("")
    (out / "practice_answers.md").write_text("\n".join(answers), encoding="utf-8")

    demo_conf = {"P1": ("5", "证据方向、剂量与结论一致，明确支持。"),
                 "P2": ("4", "只支持 2 型糖尿病亚组，结论外推到所有糖尿病患者。"),
                 "P3": ("5", "证据说差异无统计学意义，结论说显著提高。")}
    write_csv(
        out / "demo_填写示例.csv",
        [
            {
                "item_id": item["item_id"],
                "claim": item["claim"],
                "evidence": item["evidence"],
                "source_title": "",
                "human_label": item["answer"],
                "confidence_1_5": demo_conf[item["item_id"]][0],
                "note": demo_conf[item["item_id"]][1],
            }
            for item in PRACTICE[:3]
        ],
    )

    for name, seed in (("A", 101), ("B", 202), ("C", 303)):
        shuffled = list(rows)
        random.Random(seed).shuffle(shuffled)
        write_csv(out / f"audit_{name}.csv", shuffled)

    (out / "instructions_给标注者.md").write_text(INSTRUCTIONS, encoding="utf-8")
    (out / "README_组织者.md").write_text(ORGANIZER, encoding="utf-8")

    organizer = out / "_organizer_only"
    organizer.mkdir(exist_ok=True)
    shutil.copyfile(SOURCE_KEY, organizer / "audit_key.json")

    print(f"[audit-kit] wrote {out}")
    print(f"[audit-kit] sheets: audit_A/B/C.csv, 100 items each")
    print(f"[audit-kit] key: {organizer / 'audit_key.json'} (do not send)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
