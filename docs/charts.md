# 图表层

CiteGuard-CN 的图表只有一条原则：**图上每一个数都能回到真实报告或实验 JSON**。没有装饰性曲线，没有合成数据；样本很小或数据缺失时，页面显示说明文字而不是一张看起来热闹的图。

## 图表库与离线部署

- 使用 **Apache ECharts 5.5.1**，仓库内置：`web/static/vendor/echarts.min.js`（约 1.0 MB）。
- 许可证 Apache-2.0，已在 `THIRD_PARTY_NOTICES.md` 登记；不走 CDN，离线模式和 Docker 镜像都能正常出图。
- 统一入口 `web/static/js/charts.js`：深浅色 token、空状态、`ResizeObserver` 自适应、主题切换后重绘。

## 各页图表

| 页面 | 图表 | 数据来源 | 样本 / 口径 |
| --- | --- | --- | --- |
| 批量聚合 `/aggregate` | 等级分布环、五维雷达、逐篇健康分排序 | `aggregate` 接口，逐篇报告的健康画像 | 真实报告；示例 21 篇 / 509 条 |
| 报告历史 `/history` | 最近 30 天平均健康分折线 + Major 条数柱 | `GET /api/history/trend`（`data/jobs/*/report.json`） | 只画有报告的日期；当前仅 2 天有数据 |
| 题录库 `/library` | 年份分布、来源期刊/会议 Top 6 | 本地题录库统计 | 随用户导入变化 |
| 评测 `/benchmark` | 八类扰动检出率、2×2 混淆矩阵、撤稿检出环 | `data/citebench_cn/v2_results.json` | 500 条；Unknown 计漏报 |
| 批量判定 `/batch` | 四档判定分布环 | 当次 `/api/support/batch` 返回 | 需配置 judge；无 judge 时页面提示原因 |
| 报告页 `/report/{id}` | 结论分布、支持度四档、格式问题 Top 字段 | 报告内 `charts` 数据 | 每条均可展开原始表格视图 |

## 实现细节

- **渐进增强**：报告页先渲染原有 CSS 条形图，ECharts 可用时再替换；ECharts 加载失败也不影响阅读。表格视图始终保留。
- **空数据**：图表容器带 `data-empty`，没有数据时显示一句人话，不画空坐标轴。
- **深浅色**：`refresh.js` 切换主题时派发 `citeguard:themechange`，图表层重绘为对应 token，无需刷新页面。
- **交互**：悬停显示数量/占比，图例与色块同时给出文字标签，不单靠颜色区分。

## 截图证据

- `docs/evidence/shots/phase-46-aggregate-1.7.1.png`
- `docs/evidence/shots/phase-46-history-1.7.1.png`
- `docs/evidence/shots/phase-46-library-1.7.1.png`
- `docs/evidence/shots/phase-46-benchmark-1.7.1.png`
- `docs/evidence/shots/phase-46-report-charts-1.7.1.png`

## 复现

```bash
PYTHONPATH=src python -m uvicorn web.app:app --host 127.0.0.1 --port 8013
# 聚合页示例（id 需为真实已完成任务）
# http://127.0.0.1:8013/aggregate?ids=<id1>,<id2>
# 历史趋势
curl 'http://127.0.0.1:8013/api/history/trend?days=30'
```

测试覆盖：`tests/test_web.py` 的 `test_history_trend_endpoint_returns_daily_points`、`test_chart_pages_load_the_chart_layer`、`test_echarts_vendor_is_bundled`。

## 边界

- 历史趋势只是当前 `data/jobs` 里已存报告的按天聚合，不是使用量统计；报告被清理后趋势会变化。
- 聚合图表只统计已完成的报告；同一文件默认按最新一次去重，`/history?all=1` 才显示每次分析。
- 批量判定的图依赖真实 judge；没有配置模型时不给假图。
- 图表不替代报告里的逐条证据与表格；对外引用数字时仍以 `docs/evidence_index.md` 为准。
