# Batch 1.4 CiteMap 机器证据置信门禁

- 机器证据 31 格；全部展示时 precision **8/31 = 0.2581**。

| 阈值 | 展示 | 正确 | precision | recall | F1 |
| --- | --- | --- | --- | --- | --- |
| 0.7 | 24 | 8 | 0.3333 | 1.0000 | 0.5000 |
| 0.8 | 23 | 8 | 0.3478 | 1.0000 | 0.5161 |
| 0.9 | 7 | 5 | 0.7143 | 0.6250 | 0.6667 |
| 0.95 | 0 | 0 | 0.0000 | 0.0000 | 0.0000 |

按 F1 选阈值 **0.9**：precision 0.7143，recall 0.6250。
结论：高置信子集精度提升明显但召回下降；只能作为“高置信候选”展示/筛选，不能把门禁后的子集说成全面机器证据精度。

复现：`PYTHONPATH=src python scripts/eval_citemap_gate.py`
## 产品接入

- CiteMap 证据图工具栏新增「只看高置信机器候选（≥0.9）」筛选；勾选后只保留 auto evidence 中 confidence≥0.9 的边。
- 真实页面：关系 36→35，全文 8→2、摘要 15→18（弱边回填）；说明筛选改变的是候选构成，不是把机器层升级为人工证据。
- 截图：`docs/evidence/shots/opt-B1.4-citemap-gate-1.7.51-1440.png`、`...-1280.png`；测试 `tests/test_citemap_gate.py`、`tests/test_citemap_page.py`。
