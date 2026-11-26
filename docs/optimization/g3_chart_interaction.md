# G3 图表与地图交互（hover / 图例 / 缩放 / 105 节点）

G3 只补交互层：报告图表支持悬停高亮、图例筛选、Ctrl/⌘+滚轮缩放与双击重置；CiteMap 证据地图支持节点/连线悬停高亮、点击图例过滤证据等级、缩放/拖拽平移/双击重置。不改数据语义、不引入 CDN 或新依赖，也不改 `web/app.py`、模板与 `report.js`。

## 1. 操作方式

| 位置 | 操作 | 反馈 |
| --- | --- | --- |
| 报告图表 | 鼠标悬停柱子/扇区 | 当前系列高亮，图例与数值提示同步 |
| 报告图表 | 点击图例项 | 多选筛选，可逐项关闭/恢复 |
| 报告图表 | `Ctrl` / `⌘` + 滚轮 | 类目轴缩放（`dataZoom`，不改变原数据） |
| 报告图表 | 双击图表 | 缩放恢复 100% |
| CiteMap 地图 | 悬停断言/论文节点 | 高亮节点、相连连线与对端节点，其余淡出 |
| CiteMap 地图 | 悬停连线 | 高亮该连线及两端节点 |
| CiteMap 地图 | 点击图例（全文/摘要/未发现） | 隐藏或恢复该证据等级的连线，`aria-pressed` 同步 |
| CiteMap 地图 | 工具栏 `−` / `+` / `重置` | 以画布中心缩放 55%–250%，标签显示当前比例 |
| CiteMap 地图 | `Ctrl` / `⌘` + 滚轮、拖拽画布、双击 | 以光标为中心缩放、平移、重置 |
| CiteMap 地图 | 点击节点/连线 | 打开原有详情抽屉（证据原文/定位），行为未变 |

图例、工具按钮都有可见文字或 `aria-label`，图例可 Tab 聚焦、`Enter`/`Space` 切换；焦点态使用 `:focus-visible` 描边，未改变原有键盘路径。

## 2. 实现位置

| 文件 | 变更 |
| --- | --- |
| `web/static/js/charts.js` | `interactions(option)` 统一注入 emphasis/blur、图例多选、`dataZoom`；`ensureHint()` 渲染操作提示；`bindInteractions()` 绑定双击重置；`hasZoom()`/`resetZoom()` 保持幂等（`chart.__cgBound`） |
| `web/static/js/citemap_graph.js` | 重写渲染为 `viewport` 变换 + 邻接表；新增 `ensureTools()`、`wireLegend()`、`toggleFilter()`、`applyFilters()`、`applyView()`、`zoomAt()`/`zoomBy()`/`resetView()`、`hoverNode()`/`hoverEdge()`、`benchmark()`；`stats()` 报告节点/边/渲染耗时 |
| `web/static/css/citemap_graph.css` | 新增工具栏、缩放标签、操作提示、图例过滤态、`.is-hot`/`.is-hovering` 高亮、`.is-filtered` 隐藏、抓手光标与 `prefers-reduced-motion` 兜底 |
| `tests/test_charts_interaction.py` | 8 个静态契约测试：缩放/筛选/提示/双击/渲染耗时/105 节点基准/原有详情入口/reduced-motion CSS |
| `docs/evidence/shots/opt-G3-*.png` | 1440×900、1280×800 真实页面截图（含 hover 态） |
| `data/experiments/opt_g3_chart_interaction_2026-11-27.json` | 本次真实页面数字、控制台/请求结果与截图索引 |

## 3. 真实页面数字

环境：`python -m uvicorn web.app:app --host 127.0.0.1 --port 8017`，应用版本 `1.7.48`；浏览器为 Playwright 1.64 驱动的 Edge（Chromium）无头模式，非模拟串。

| 指标 | 1440×900 | 1280×800 |
| --- | --- | --- |
| 报告图表 | 3 个，`dataZoom=1`，提示含「Ctrl+滚轮缩放」 | 同左 |
| Ctrl+滚轮后 `dataZoom.start/end` | 4.96 / 95.87 | 4.96 / 95.87 |
| 双击后 `dataZoom.start/end` | 0 / 100 | 0 / 100 |
| CiteMap 真实图节点/边 | 29 / 36 | 29 / 36 |
| 真实图渲染耗时 | 3.3 ms | 2.5 ms |
| 悬停高亮 | 8 个节点、7 条连线 | 同左 |
| 摘要级连线过滤 | 15/15 隐藏，`aria-pressed=false` | 同左 |
| 按钮 `+` 缩放 | 1.22（122%） | 1.22（122%） |
| 双击重置 | 1.00（100%） | 1.00（100%） |
| 页面横向溢出 | 0 px | 0 px |
| 脚本错误 / 失败请求 | 0 / 0 | 0 / 0 |

截图：

- `docs/evidence/shots/opt-G3-report-charts-1.7.48-1440.png`
- `docs/evidence/shots/opt-G3-report-charts-1.7.48-1280.png`
- `docs/evidence/shots/opt-G3-citemap-graph-1.7.48-1440.png`
- `docs/evidence/shots/opt-G3-citemap-graph-1.7.48-1280.png`
- `docs/evidence/shots/opt-G3-citemap-hover-1.7.48-1440.png`
- `docs/evidence/shots/opt-G3-citemap-hover-1.7.48-1280.png`

报告图表位于「检查明细 → 图表」抽屉内，截图前已点开该标签页；CiteMap 截图来自 `/citemap?topic=ai_education` 的真实主题图。

## 4. 105 节点基准（合成，如实标注）

仓库当前最大的真实主题图是 `ai_education` 的 **29 节点 / 36 条边**，没有 105 节点的线上 payload。因此 `CGMapGraph.benchmark(105)` 在同一套 `paint()` 与布局上生成 **显式合成图**（55% 断言、45% 论文、每条断言 2 条边，共 105 节点 / 116 条边），在离屏 SVG 中构建并绘制，只计 DOM 构建与绘制时间，不含网络：

| 宽度 | 节点 | 边 | 渲染耗时 |
| --- | --- | --- | --- |
| 1440 | 105 | 116 | 3.2 ms |
| 1280 | 105 | 116 | 3.9 ms |

这是「该布局在 105 节点规模下的渲染成本」，**不是**「线上已有 105 节点图」；JSON 中 `synthetic: true` 一并落盘，禁止把它写成产品真实数据。

## 5. 测试与复现

```powershell
python -m pytest tests/test_charts_interaction.py -q
python -m pytest tests/test_web.py -q
python -m pytest tests -q
```

本次结果：`test_charts_interaction.py` 8 passed（1.84s）；`test_web.py` 92 passed（10.67s）；全套 1127 passed、10 skipped，另有 1 个与 G3 无关的失败 `tests/test_evidence_map.py::test_data_directory_contains_no_pdf_files`（队友在 `data/evidence_map/expansion/` 新增了 `ai_education_review.csv`，该测试只允许 `.json/.md`）。

复现真实页面（PowerShell）：

```powershell
python -m uvicorn web.app:app --host 127.0.0.1 --port 8017
# 另开一个终端，用任意 Chromium/Edge 打开
# http://127.0.0.1:8017/report/05304bf55ea7 → 检查明细 → 图表
# http://127.0.0.1:8017/citemap?topic=ai_education → 打开证据图
```

控制台检查：`console.error` 0 条、失败请求 0 条。页面唯一 404 是 `report.html` 第 5 行引用的 `/static/css/report_diff.css?v=1.7.48`，该文件在仓库中不存在，属报告模板既有问题，G3 改动前后一致，未在本次范围内修改。

## 6. 边界

- 只验证了 Edge（Chromium）1440/1280 桌面视口；Firefox/Safari 与触屏手势未单独验证。
- 1280 下地图舞台保留既有 `min-width: 1080px`，超宽图在舞台内横向滚动；页面级横向溢出为 0，未改变这一历史行为。
- 缩放只改变视口变换，不改变布局计算与数据；图例过滤只隐藏连线，不删除数据、不改变判定。
- 图表缩放按类目轴启用；饼图不提供 `dataZoom`。
- 报告图表需要先打开「检查明细」抽屉的「图表」标签，图表在此之前不初始化，这是现有页面结构。
- 未改动 `web/app.py`、`web/templates/*`、`web/static/js/report.js`；队友并行修改的文件（`report.js`、`report.html`、`library.*` 等）不在本任务变更清单内。
