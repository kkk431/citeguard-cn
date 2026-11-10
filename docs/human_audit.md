# ClaimSupport-CN 人工抽检协议

这份协议是给「真找人来标注」用的，不是说我替人标过。现在仓库里没有任何人工金标，
所以对外只能说构造集评测，不能说人工评测。

## 1. 抽哪些

从 ClaimSupport-CN 100 条 + 扩展 60 条 + V2 140 条（共 300 条构造集）里按标签分层抽样 60 条（默认 seed 20261111）：

| 标签 | 抽中 |
|---|---|
| support | 24 |
| partial | 15 |
| contradict | 10 |
| no_evidence | 11 |

生成命令（可复现，同 seed 同结果）：

```bash
python scripts/build_audit_sheet.py --n 60 --seed 20261111
```

输出：

- `data/audit/audit_sheet.csv`：给标注者看的表，**不含标签**，只有
  `item_id / claim / evidence / source_title / human_label / confidence_1_5 / note`；
- `data/audit/audit_key.json`：答案键，标注完成前不给标注者。

## 2. 怎么标

标注者只看 `claim`、`evidence`、`source_title` 三列，按下面四档独立判断：

- **support**：证据直接支持结论，关键数字/对象/方向都对得上；
- **partial**：方向对，但有一处不完整（少了对象、条件、范围，或数字是“平均”被说成“全部”）；
- **contradict**：证据明确否定结论中的关键部分（方向、数字、对象至少一项冲突）；
- **no_evidence**：证据里找不到能判断这句话的依据（跑题、只有标题、空段落）。

要求：

1. 每人不看别人的结果，不查模型输出，不用 AI 代标；
2. 每条记录 `confidence_1_5`（1=完全没把握，5=非常确定），有争议写在 `note`；
3. 单人 60 条约 45–60 分钟，建议分两段做，避免疲劳；
4. 两人独立标 → 第三人仲裁分歧；只有一人时，隔一周自标第二遍做一致性检查。

## 3. 怎么算

- 与答案键比：accuracy、macro-F1、每类 precision/recall；
- 标注者之间：Cohen's κ（两人）或 Fleiss' κ（三人），以及原始一致率；
- 样本标签分布约为 support 24 / partial 16 / contradict 10 / no_evidence 10；
- 报 95% Wilson 置信区间——60 条的区间很宽，结论必须写区间，不写单点；
- 仲裁后的标签作为 `ClaimSupport-CN-human-60` 发布，和构造标签分开放。

## 4. 什么能说、什么不能说

能说：

- “在 60 条人工抽检上，模型与仲裁标签的一致率为 X%（95% CI …），κ=…”；
- “构造集上 0.96，人工抽检集上另行报告，二者不可混用”。

不能说：

- “人工评测 0.96”（除非真做了且数字对得上）；
- 拿构造标签当人工标签；
- 用模型输出当标注结果。

## 5. 交付时带什么

- 填好的 `audit_sheet.csv`（每人一份，文件名加标注者代号）；
- 仲裁记录（分歧条目与最终标签）；
- 指标脚本输出的 JSON（建议 `data/experiments/human_audit_60.json`）；
- 协议版本 + 日期 + 标注者人数（匿名代号即可）。
