# ClaimSupport-CN 人工抽检协议（100 条 · 三人盲标）

这份协议是给「真找人来标注」用的，不是说我替人标过。现在仓库里没有任何人工金标，
所以对外只能说构造集评测，不能说人工评测。

## 1. 抽哪些

从 ClaimSupport-CN 100 条 + 扩展 60 条 + V2 140 条（共 300 条构造集）里按标签分层抽样 100 条：

| 标签 | 抽中 |
|---|---|
| support | 40 |
| partial | 27 |
| contradict | 17 |
| no_evidence | 16 |

前 60 条沿用早期 `audit_sheet.csv`，新增 40 条与其 claim、来源 work 均不重叠。
生成命令（可复现）：

```bash
python scripts/build_audit_sheet_100.py
```

输出：

- `data/audit/audit_sheet_100.csv`：给标注者看的表，**不含标签**，只有
  `item_id / claim / evidence / source_title / human_label / confidence_1_5 / note`；
- `data/audit/audit_key_100.json`：构造标签答案键，标注完成前不给标注者。

三人盲标包由 `scripts/build_audit_kit.py` 生成到 `dist/audit_kit/`：
`audit_A/B/C.csv` 同一批 100 条、三种随机顺序，另含说明、5 条练习与填表示例；
`_organizer_only/audit_key.json` 只给组织者。

## 2. 怎么标

标注者只看 `claim`、`evidence`、`source_title` 三列，按下面四档独立判断：

- **support**：证据直接支持结论，关键数字/对象/方向都对得上；
- **partial**：方向对，但有一处不完整（少了对象、条件、范围，或数字是“平均”被说成“全部”）；
- **contradict**：证据明确否定结论中的关键部分（方向、数字、对象至少一项冲突）；
- **no_evidence**：证据里找不到能判断这句话的依据（跑题、只有标题、空段落）。

要求：

1. 每人不看别人的结果，不查模型输出，不用 AI 代标；
2. 每条记录 `confidence_1_5`（1=完全没把握，5=非常确定），有争议写在 `note`；
3. 单人 100 条约 1.5–2 小时，建议分 2–3 次做，避免疲劳；
4. 三人独立标，分歧条目由组织者带 1 位标注者仲裁；不要回头改原始三份 CSV。

## 3. 怎么算

```powershell
$env:PYTHONPATH='src'
python scripts/score_audit_kit.py --kit dist/audit_kit --out dist/audit_kit/_results
```

- 标注者之间：两两 Cohen's κ、Fleiss' κ 与原始一致率；
- 多数票金标：三人中至少两人一致的标签；平票条目列入 `disagreements.csv` 仲裁；
- 与构造键只作“参考一致率”，不能把构造标签当人工金标；
- 报 95% Wilson 置信区间——100 条的区间仍不窄，结论必须写区间，不写单点；
- 仲裁后的标签作为 `ClaimSupport-CN-human-100` 发布，和构造标签分开放。

## 4. 什么能说、什么不能说

能说：

- “在 100 条人工盲标上，3 人独立标注，Fleiss κ=…，其中 N 条仲裁”；
- “构造集上 0.96，人工抽检集上另行报告，二者不可混用”。

不能说：

- “人工评测 0.96”（除非真做了且数字对得上）；
- 拿构造标签当人工标签；
- 用模型输出当标注结果；
- “人工金标准覆盖 300 条”。

## 5. 交付时带什么

- 填好的 `audit_A/B/C.csv`（每人一份，文件名不变）；
- 仲裁记录（`human_gold.csv` 中 `needs_adjudication=True` 的条目与最终标签）；
- 评分脚本输出（`agreement_report.json`、`human_gold.csv`、`disagreements.csv`）；
- 协议版本 + 日期 + 标注者人数（匿名代号即可）。
