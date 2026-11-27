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


## 语义 judge 回放（2026-11-27）

31 条机器证据，人工多数票 8 条 correct / 23 条 issue。把“判定为 support/partial”映射为“证据可接受”，与人工多数票比较：

| 方案 | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 直接 claim→quote judge | 7 | 6 | 1 | .5385 | .875 | **.6667** |
| 断言拆解 + 逐子句 judge | 7 | 7 | 1 | .5000 | .875 | **.6364** |

**结论：断言拆解在当前 31 条上比直接 judge 低 3.03 个 F1 点，不接入产品默认路径。** 这不是“新算法有效”，而是一个负结果；保留模块和评测脚本，便于以后在更大样本/更好检索上重测。

边界：人工多数票判断的是“机器证据是否可接受”，不是“复合断言是否被全文完整支持”；这里把 support/partial 映射为可接受，只是代理指标。31 条来自 CiteMap 两个主题，样本小。

复现：

```bash
python scripts/eval_b1_1_alignment_semantic.py
```

数据：`data/experiments/opt_b1_1_alignment_semantic_2026-11-27.json`
