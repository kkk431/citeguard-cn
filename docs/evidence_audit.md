# 证据索引自检

`docs/evidence_index.md` 是对外数字的唯一台账。脚本逐行抽取反引号里的仓库路径，检查文件是否存在，并列出 `docs/evidence/shots/` 里未登记的截图。

```powershell
python scripts/audit_evidence.py
```

当前结果（2026-11-12，1.0.12）：**60 个路径、0 缺失、25 张截图全部登记**（`data/experiments/evidence_audit.json`）。

本轮修掉的问题：

1. 4 个“待补”占位截图换成真实文件——规划页、报告三张真图、模型对比图（同一 100 条构造集）、1000 条压测图、复检 diff 界面；
2. 2 个裸文件名（`blind_test5_protocol.json`、`citation_anchor_sample.csv`）补成 `data/experiments/` 全路径；
3. 7 张已存在但未登记的截图补进「截图登记」表；
4. 自检脚本只校验含 `/` 的仓库路径，避免把证据包内的 `report.json` 之类样本名误判为缺失。

边界：脚本只查“文件在不在”，不校验文件内容与数字是否一致；数字口径仍由 `docs/experiments.md` 与各 JSON 负责。
