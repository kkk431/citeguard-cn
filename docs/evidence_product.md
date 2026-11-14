# 产品最终截图（19 张，1920×1080）

> 由 `scripts/capture_final_shots.py --job 96511af51c97` 对真实运行实例（截图时为 1.7.13；1.7.14 只改证据抽屉对比度，页面版本号随发布更新）逐页截取；深色主题、无 CDN、无伪造状态。截图目录 `docs/evidence/shots/final/product/`，清单 `manifest.json`。

复现：先启动本地服务，再运行上述命令；`--only` 可只重拍单页。

| # | 截图 | 页面 | 路径 |
|---|---|---|---|
| 01 | ![01](evidence/shots/final/product/01-landing.png) | 独立首页：价值主张与真实报告预览 | `/` |
| 02 | ![02](evidence/shots/final/product/02-workspace.png) | 工作台：上传、最近报告与本次会检查 | `/workspace` |
| 03 | ![03](evidence/shots/final/product/03-support.png) | 单句判定：四档含义与证据输入 | `/support` |
| 04 | ![04](evidence/shots/final/product/04-library.png) | 题录库：标签、分页与覆盖构成 | `/library` |
| 05 | ![05](evidence/shots/final/product/05-discover.png) | 文献发现：真实 OpenAlex 检索结果 | `/discover` |
| 06 | ![06](evidence/shots/final/product/06-citemap.png) | CiteMap：断言分组与人工/机器证据 | `/citemap?topic=ai_education` |
| 07 | ![07](evidence/shots/final/product/07-live.png) | Live 单句核验：判官给出支持与逐字证据 | `/live` |
| 08 | ![08](evidence/shots/final/product/08-report-overview.png) | 报告总览：结论、健康画像与先修项 | `/report/96511af51c97` |
| 09 | ![09](evidence/shots/final/product/09-report-refs.png) | 逐条结果与条目详情 | `/report/96511af51c97` |
| 10 | ![10](evidence/shots/final/product/09b-report-evidence.png) | 证据抽屉：字段、支持度与正文引用 | `/report/96511af51c97` |
| 11 | ![11](evidence/shots/final/product/10-report-checks.png) | 检查明细抽屉：来源/图表/支持度/引注 | `/report/96511af51c97` |
| 12 | ![12](evidence/shots/final/product/11-repair.png) | 一键修复：逐条 before/after 与字段提示 | `/report/96511af51c97` |
| 13 | ![13](evidence/shots/final/product/12-history.png) | 全部报告：按文件合并与分页 | `/history` |
| 14 | ![14](evidence/shots/final/product/13-benchmark.png) | 评测：CiteBench-CN v2 与真实基线 | `/benchmark` |
| 15 | ![15](evidence/shots/final/product/14-models.png) | 模型设置：云端与本地两套判官 | `/settings/models` |
| 16 | ![16](evidence/shots/final/product/15-about.png) | 关于：能力边界与开源资产 | `/about` |
| 17 | ![17](evidence/shots/final/product/16-figure.png) | 图表核验：上传截图或按引用句定位 | `/figure` |
| 18 | ![18](evidence/shots/final/product/17-compare.png) | 多篇对比：六字段对照 | `/compare` |
| 19 | ![19](evidence/shots/final/product/18-batch.png) | 批量判定：一次粘贴多条引用句 | `/batch` |

## 看图时的事实边界

- `03-support` 只填了引用句，未提交；四档图例是说明，不是判定结果。
- `07-live` 的「支持 95%」来自当前配置的 DeepSeek judge，证据句是检索到摘要中的逐字片段；judge 输出不是人工金标。
- `09b-report-evidence` 展示的是真实报告 `96511af51c97` 的字段与支持度；该任务 `support_max=0`，所以支持度显示未检测，不冒充已判定。
- `10-report-checks` 同样来自该任务，切到「正文引注」标签；来源健康/图表抽检因本次未跑而隐藏，属于真实状态。
- `11-repair` 是预览弹窗，没有点击应用（截图时未写入 `report.fixed.json`）。
- `12-history` 只显示真实任务，不含测试数据；`14-models` 显示云端与本地两个判官，但本地服务是否在线取决于部署。
- `06-citemap`/`13-benchmark` 的完整指标与边界见 `docs/evidence_map.md`、`docs/live_eval.md`、`docs/baselines.md`。
