# Batch 1.1 断言—证据对齐（词面基线审计）

- 样本：`ai_education` 机器抽取证据 10 对（非人工金标）。
- 最大词面覆盖率：**0.0497**；均值 **0.0170**；中位数 **0.0125**。
- 无 judge 时返回 insufficient：**10/10**。

## 结论

跨语言 claim/evidence 的字面重合极低；词面检索只能召回候选句，不能当作支持度。
Batch 1.1 若要有可测增益，必须接入语义 judge 或 embedding；本文件只记录负基线，不把 lexical 包装成对齐能力。

## 复现

```bash
PYTHONPATH=src python scripts/eval_b1_1_alignment.py
```