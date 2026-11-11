# 文档站（mkdocs）

来源即本仓库 `docs/`，不另写一套。

```powershell
pip install -r requirements-docs.txt
python -m mkdocs build
python -m mkdocs serve   # http://127.0.0.1:8000
```

构建结果 `site/index.html`（`site/` 不进仓库）。导航 12 项：首页 / 部署 / API 与 SDK / 生态 / 存储 / 评测 / 证据索引 / 性能 / 数据集 / 模型 / 许可证 / 路线图。

截图：`docs/evidence/shots/phase-37-docs-site-1.0.11.png`（E47）。
