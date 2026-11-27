# B1.2 人机证据图共识（保守门）

## 结论

在 105 格 CiteMap 人工核对中，有 101 格被三位审稿人解析出多数票。按“**3/3 一致才通过，2:1 只进复核**”的保守规则：

- 机器证据 31 格：3/3 接受 **5** 格（16.1%），3/3 拒绝 **12** 格，2:1 争议 **14** 格；
- 无机器证据 70 格：接受 65、争议 5、拒绝 1（“无证据”本身不等于错误，但也不能自升为证据）。

也就是说，**机器候选的置信度不能自升为证据边**；只有人工 3/3 接受时才允许写入 `accepted_edges`。当前可接受边为 **5 条**。

## 实现

`src/citeguard/evidence_consensus.py`

- `consensus(row)`：3/3 correct → `accepted`；3/3 issue → `rejected`；其余 2:1 → `contested`；无投票 → `pending`。
- `accepted_edges(rows)`：只返回 `cell_kind == 机器证据` 且 `accepted` 的格，字段为 cell/claim/paper。
- `summarize(rows)`：统计机器/无证据两类的接受、拒绝、争议数量。

机器层原有的 `auto_evidence` 仍是候选层；本模块不改变产品图层的默认显示，只定义“什么条件下人工接受可以升级为证据边”。

## 与 B1.4 的关系

- B1.4 的 0.9 阈值门禁：7/31 展示，5/31 正确，precision .714、recall .625。
- 本共识门更保守：只接受 5/31。两者都说明**当前机器证据的绝对质量不足以直接当证据边**。
- 这不是“新准确率”，是人工核对的一个切面；101/105 已解析，4 格未解析。

## 复现

```bash
PYTHONPATH=src python scripts/eval_b1_2_consensus.py
```

数据：`data/experiments/opt_b1_2_consensus_2026-11-27.json`

## 未做

- 未把这 5 条 accepted 边写回 CiteMap 图数据（当前图仍以人工层 + 机器候选层分开显示）。
- 未把 2:1 争议样本用于模型训练；它们只用于复核队列。
- 4 个未解析格未强行给多数票。
