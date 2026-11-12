# 证据截图目录

规则（与 `docs/plan_national.md`、`docs/evidence_index.md` 一致）：

- 命名：`phase-序号-名称-版本.png`，例如 `phase1-01-support-dist-0.9.86.png`
- 宽度：1920px（PPT 直接复用）；界面截图保留浏览器原始比例
- 图表：同时提交生成脚本 + 数据快照，图内标注“来源 / n / 口径”
- 每张图在本目录落盘后，立刻在 `docs/evidence_index.md` 的「截图登记」表补一行
- 不要只把图放在 `out/`（临时、不入库）

## 自动截图（1.3.4）

```powershell
$env:PYTHONPATH='src'
python scripts/capture_evidence.py --base http://127.0.0.1:8013 --job <job_id>
```

- 默认截 11 个页面（首页/支持度/题录库/发现/对比/图表/批量/评测/历史/模型/关于），加 `--job` 再截报告页。
- 输出到 `docs/evidence/shots/captured/`（已 gitignore，避免每次提交重复图）；需要入库的证据图仍按 `phase-*` 命名复制到本目录。
- 控制台报错或页面加载失败会以非零退出码结束，可作为轻量视觉回归。
