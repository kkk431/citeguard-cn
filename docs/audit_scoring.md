# 人工盲标评分

ClaimSupport-CN 的标签由构造规则决定，不是人工语义标注。要回答“模型在真人眼里准不准”，需要一次**盲标**：标注者只看 `item_id`、引用句、证据原文，不看构造标签，也不看模型输出。

> 当前推荐的是 **100 条、三人独立盲标**：见 [human_audit.md](human_audit.md)、`scripts/build_audit_sheet_100.py`、`scripts/build_audit_kit.py` 与 `scripts/score_audit_kit.py`。下面的 60 条单人流程保留为早期工具，不再作为主口径。

这条工具链有三步：

```bash
# 1) 生成盲标表 + 答案键（标注者只拿 sheet）
PYTHONPATH=src python scripts/build_audit_sheet.py --n 60 --seed 20261111
#    data/audit/audit_sheet.csv  ← 发给标注者
#    data/audit/audit_key.json   ← 自己留好，不要发出去

# 2) 标注者填 human_label（四选一）和可选的 confidence_1_5，回收 CSV

# 3) 评分
PYTHONPATH=src python scripts/score_audit_sheet.py \
  --sheet data/audit/audit_sheet.csv --key data/audit/audit_key.json \
  --allow-partial --json-out data/audit/audit_result.json
```

`human_label` 必须是 `support` / `partial` / `contradict` / `no_evidence` 之一（大小写、连字符、空格会归一化）。

## 输出什么

- `accuracy`：与构造标签的一致率。
- `macro_f1`：四类宏平均 F1。
- `kappa`：Cohen's κ（未加权），衡量“不是靠猜”。
- `per_label`：每类 support / precision / recall / F1。
- `confusion`：行=构造标签、列=人工标签。
- `coverage` / `missing`：填了多少、漏了哪些。
- `confidence`：可选 1–5 自评的均值，以及答对/答错时的均值。

## 严格性

- 空表、没有列、未知标签、重复 `item_id`、置信度不在 1–5：直接报错（退出码 2），不会输出一个好看但无意义的数字。
- 默认要求覆盖 ≥80% 的答案键；低于这个比例必须显式加 `--allow-partial`，结果里 `partial=true`，文档/PPT 里也只能写“部分盲标”。
- `--predictions preds.csv`（列 `item_id,label`）可以额外比较“系统 vs 人工 vs 构造标签”的一致率；这不能替代人工准确率。

## 当前状态（诚实）

- 已生成 **60 条**分层盲标表（`data/audit/audit_sheet.csv`，`human_label` 全空）和答案键（`data/audit/audit_key.json`），`pytest` 覆盖空表/错标/低覆盖/κ 计算。
- **还没有真人填过**，所以任何地方都不能写“人工准确率”。表本身是空的，工具在此处只证明流程可执行、不可伪造。
- 构造标签不是人审标签；本工具算出的数字只对“这批构造标签 + 这位标注者”成立，不自动外推到整个中文文献分布。

## 一条命令验证工具本身

仓库自带测试（用假数据，不冒充真人）：

```bash
PYTHONPATH=src pytest tests/test_audit_score.py -q
```

另外可以直接跑空表，确认它拒绝出分：

```bash
PYTHONPATH=src python scripts/score_audit_sheet.py \
  --sheet data/audit/audit_sheet.csv --key data/audit/audit_key.json
# error: sheet has no filled human_label values  (exit 2)
```
