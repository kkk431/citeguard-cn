# CiteMap 105 格人工核对结果

> 三位标注者独立核对，标注者匿名。核对对象是 **机器候选**，不是模型最终裁决；
> 人工只回答“这条引文是否真的支持这条断言”。

## 数据与流程

- 回收包：`CiteGuard-CN_CiteMap核对_105格_ABC已回收.zip`，含 `reviewer_A/B/C.csv` 各 105 行。
- 105 格 = 2 主题 × 15 篇 × 每主题 4/3 条主断言；60 格版是 57% 分层抽样。
- 每格三个人独立选 `✓ 正确 / ✗ 有问题 / 跳过`；跳过只允许在“机器未发现证据”的格使用。
- 评分：`scripts/score_citemap_csv.py`，产物 `data/experiments/citemap_audit_105/`。

## 标注者一致性

| 指标 | 数值 |
| --- | --- |
| 有效评分格 | 101 / 105（4 格三人全跳过） |
| 一致（unanimous） | 82.2% |
| 分歧格 | 18 |
| Fleiss κ | **0.6587** |
| A\|B / A\|C / B\|C Cohen κ | 0.6172 / 0.4956 / 0.8490 |
| 多数票 | 77 正确 / 24 有问题 |

κ 0.66 说明“这条引文算不算支持”存在真实的判定分歧，不能把单个人工标签当绝对真值；下文一律用三人多数票。

## 机器候选质量（v1，42 条抽 31 条证据格）

| 指标 | 数值 | 95% CI |
| --- | --- | --- |
| 机器证据格正确率（多数票） | **8 / 31 = 25.8%** | 13.7%–43.2%（Wilson） |
| 无证据格报“无证据”的正确率 | **69 / 70 = 98.6%** | — |
| 错误类型 | 59 次“断言错配” + 2 次“立场错” | — |

结论：v1 的主要问题不是“漏”，而是**把相关句凑成支持**。这与 105 格中“无证据格几乎全对、证据格大量有问题”的分布一致。

## 三层对照

| 层 | 产出 | 有人工核对的格 | 多数票正确 | 说明 |
| --- | --- | --- | --- | --- |
| v1 全量候选 | 42 条 / 25 篇 | 31 | 8（25.8%） | 每篇一次给所有主断言配证据，倾向凑 |
| strict 复核 | 8 条 / — | 3 | 3（100%，n=3） | 只保留复核通过，召回低 |
| **原子断言（当前产品）** | **9 条 / 7 篇** | **7** | **5（71.4%）** | 母断言拆成 21 条原子命题，逐条抽取+复核 |

原子层仍有 2 个争议格（AI 教育 `edu-007`、`edu-012`），不隐藏；也不能把“原子证据存在”写成“母断言成立”。

## 复现

```bash
PYTHONPATH=src python scripts/score_citemap_csv.py \
  --key data/evidence_map/verification_packet.json \
  --sheets out/citemap_full_review \
  --out data/experiments/citemap_audit_105

PYTHONPATH=src python scripts/build_citemap_atomic_claims.py
PYTHONPATH=src python scripts/extract_citemap_atomic.py --workers 6
```

## 边界

- 标注者只看到摘要与候选句，不能代替全文/图表核查。
- 三人多数票不是“金标准”，κ 0.66 的分歧本身是结果的一部分。
- 原子拆分由模型完成，未做人工确认；它改善的是“部分支持”的表达，不保证母断言为真。
- 本页数字与 `data/experiments/citemap_audit_105/`、`data/evidence_map/extractions_atomic/` 对应；不要外推为“CiteMap 准确率”。
