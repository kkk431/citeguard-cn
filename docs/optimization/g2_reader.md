# G2 报告阅读器：小地图、严重度、跳转与页内缩放

日期：2026-11-26
范围：t34 / G2（报告阅读层）。只改报告页模板、报告 JS、新增阅读器 CSS 与相关测试；不改 `web/app.py`，不改 `refresh.css`，不改核验数据或判定逻辑。

## 1. 为什么改

报告页的真实样本有 54 条参考文献、14 页卡片。原来的阅读路径有三个断点：

- 右侧工作台只显示当前页的 4 张卡片，用户不知道第 30 条在前面还是后面；
- 想找“中等严重度”的条目，只能在“元数据偏差 / 未找到匹配”等状态间来回点，无法按阅读优先级聚合；
- j / k 只在当前页的 DOM 卡片之间移动，翻到第二页后要重新找焦点；页内证据图也只能适应宽度，看不清小字。

G2 把“先看哪里、怎么跨页、页内怎么放大”变成常驻的阅读控件，同时保留原有证据抽屉、分页、导出、修复与 triage 流程。

## 2. 页面与交互

### 2.1 条目小地图

在逐条结果工具栏与列表之间新增 `.reader-nav`：

- `#ref-minimap-track` 为每个“当前筛选结果”渲染一个色块，颜色按阅读严重度分三档；
- 色块带 `aria-label`，点击后定位到该条：切到卡片视图、跳到对应页、滚动并聚焦卡片，同时打开详情抽屉；
- 当前页的 4 个条目用 `.on` 轮廓标出；
- `#ref-progress-text` 显示“第 X / Y 页 · 当前条范围 / 总条数”，`#reader-progress-bar` 显示页进度；
- 图例同时给出三档计数，计数随筛选变化，不是全量统计。

**边界：** 小地图绘制的是当前筛选结果的位置，不是全部 54 条；清空筛选后恢复全量。这样筛选后色块仍与列表一一对应，不会出现“点了色块却打开被筛掉条目”的歧义。

### 2.2 严重度筛选

工具栏新增 `#severity-filter`，选项为“全部 / 严重 / 中等 / 轻微”：

| 档位 | 判定 | 用途 |
| --- | --- | --- |
| 严重 | `verify.status == Major` 或 `support.label == contradict` | 最需要人工先看 |
| 中等 | `Minor` / `Unverified` 或 `support.label == partial` | 元数据、格式、支持度需要复核 |
| 轻微 | 其余（含 `Exact`、`Unknown`） | 通常只需快速扫读 |

**这是阅读优先级，不是“论文学术质量”或“证据真假”的判决。** `Exact` 只是元数据一致，不等于正文支持；`Unverified` 只是没找到可靠匹配，不等于造假。当前截图样本没有 `Major` 与 `contradict`，所以“严重”计数为 0，筛选后显示空态是预期行为，不是控件失效。

### 2.3 页与条目跳转

`#page-jump` + `#page-jump-go`：输入页码，Enter 或点“跳页”，页码范围自动夹到 `1..pages`，并清空列表滚动位置。

`#item-jump` + `#item-jump-go`：输入参考文献序号（不是列表位置），Enter 或点“定位”，在**当前筛选结果**中查找 `item.index`。如果该条被筛选隐藏，会先清空筛选再定位，并提示“已清除筛选以定位条目”。找不到时用 toast 提示，不静默失败。

### 2.4 j / k 跨页浏览

- j / k 不再只遍历当前页：按当前筛选结果跨页移动，到页边界时自动翻页；
- 当前卡片加 `.kb-active` 并聚焦，滚动到可见位置；
- 如果详情抽屉原本打开，移动后保持打开并加载新条目；抽屉关闭时只移动焦点，不强行打开；
- `/` 聚焦搜索，Escape 关闭抽屉/页图/清空搜索，Enter 打开当前卡片详情，f / t / p / 1–5 保留原行为；
- 输入框、select、textarea 获得焦点时，单字母快捷键不触发。

### 2.5 页内证据缩放

页内证据弹窗标题栏新增 `#page-viewer-zoom-controls`：

- `−` / `+` 每次 25%，范围 **50%–250%**；
- `#page-viewer-zoom` 显示当前百分比；
- “适应”恢复 100%（图片宽度 100%，由外层 `.page-viewer-image` 滚动查看放大后的图）；
- 键盘 `+` / `-` / `0` 与按钮等价；每次打开新页图重置为 100%。

## 3. 实现

### 3.1 文件

| 文件 | 改动 |
| --- | --- |
| `web/templates/report.html` | 引入 `report_reader.css`；严重度 select；阅读导航；页图缩放按钮 |
| `web/static/js/report.js` | 严重度模型、小地图、跨页 j/k、页/条目跳转、缩放状态与绑定 |
| `web/static/css/report_reader.css` | 新增文件，所有新样式；不改 `refresh.css` |
| `tests/test_web.py` | 2 个静态契约测试，新增于 G2 段 |
| `docs/evidence/shots/opt-G2-*.png` | 6 张真实页面截图 |
| `data/experiments/opt_g2_reader.json` | 浏览器检查、截图、控制台记录 |
| `docs/optimization/g2_reader.md` | 本文 |

### 3.2 JS 关键点

- `SEVERITY` 定义三档及提示；`severityOf(item)` 只做阅读优先级映射；
- `visibleItems(data)` 统一“筛选 + 排序”，列表、小地图、j/k、跳转共用同一结果集，避免各自维护一套过滤；
- `apply(data)` 把 `severity` 并入 `state._sig`，筛选变化自动回到第 1 页，并重绘小地图与分页；
- `renderReaderNav(items,page,pages,start)` 用文档片段一次性重建色块，避免逐条 DOM 操作；
- `bindReportKeys()` 在初始化时绑定一次键盘，移出 `render()`，避免每次重绘重复叠加监听器；
- `bindReaderNav()` / `bindPageViewerZoom()` 同样只绑定一次；按钮用 `__bound` 标记兜底；
- 页图缩放只改 `img.style.width`，不替换外层滚动容器，保留原 `.page-viewer-image` 的横向/纵向滚动。

### 3.3 兼容性

- 证据抽屉 `openEvidence`、条目抽屉 `openRefDrawer`、分页 `renderPager`、导出菜单、修复预览/应用/撤销、triage 计数与筛选均保留；
- 表格视图仍走原 `renderTable`，小地图按同一筛选结果绘制，切换视图不丢筛选；
- 新增 CSS 独立文件，不改 `refresh.css` 的既有选择器；`html,body` 已有的 `overflow-x:hidden` 继续兜底；
- 模板中两个跳转输入使用 `reader-jump-input` 自定义宽度，避免被 `refresh.css` 的全局 `input[type=number]{width:100%}` 撑开。

## 4. 真实页面验证

环境：

| 项 | 值 |
| --- | --- |
| 服务 | `http://127.0.0.1:8013`（本地 uvicorn，真实报告页） |
| 页面 | `/report/c674df27a57e`（54 条参考文献，14 页） |
| 浏览器 | Playwright 1.64.0 驱动的 Chromium 156.0.8078.4（headless，真实 Chromium） |
| 视口 | 1440×900；1280×800 |
| 数据 | `data/jobs/c674df27a57e/report.json`（Exact 16 / Minor 30 / Unverified 8；无 Major） |

机器可读记录：`data/experiments/opt_g2_reader.json`。

| 检查 | 实际结果 |
| --- | --- |
| 逐条结果首屏 | 4 张卡片 |
| 小地图色块 | 54 |
| 初始进度 | `第 1 / 14 页 · 1–4 / 54 条` |
| 中等筛选 | `第 1 / 10 页 · 1–4 / 38 条`，色块 38 |
| 跳页 2 | `第 2 / 14 页 · 5–8 / 54 条` |
| 跳到条目 7 | 抽屉打开、卡片标记 `.kb-active` |
| j 键 | 当前卡片标记 `.kb-active` |
| 页内证据 | 从正文引注打开第 1 页，缩放 150%，图片 `width:150%` |
| 横向溢出 1440 | `documentElement.scrollWidth=1440`，`body=1440`，`innerWidth=1440` |
| 横向溢出 1280 | `documentElement.scrollWidth=1280`，`body=1280`，`innerWidth=1280` |
| 小地图 1280 | 54 色块 |
| 控制台 | 0 error / 0 warning（记录数组为空） |

截图（均为真实页面，不是设计稿）：

| 截图 | 尺寸 | 内容 |
| --- | --- | --- |
| `docs/evidence/shots/opt-G2-report-1440.png` | 1440×900 | 报告总览首屏，左侧评分、右侧总览/逐条结果 |
| `docs/evidence/shots/opt-G2-refs-1440.png` | 1440×900 | 逐条结果：小地图 54 色块、进度、页/条目跳转、卡片列表 |
| `docs/evidence/shots/opt-G2-filter-1440.png` | 1440×900 | 严重度“中等”：38 条、10 页、图例计数同步 |
| `docs/evidence/shots/opt-G2-jump-1440.png` | 1440×900 | 跳页 2 后跳到条目 7，详情抽屉打开、卡片高亮 |
| `docs/evidence/shots/opt-G2-zoom-1440.png` | 1440×900 | 页内证据第 1 页，缩放 150%，读者可用滚动查看细节 |
| `docs/evidence/shots/opt-G2-report-1280.png` | 1280×800 | 1280 宽度下逐条结果与小地图，无横向溢出 |

> 1280 截图中跳页输入显示 2、条目输入显示 7，是脚本先做跳转再改视口留下的真实状态；初始页面两者为空。

## 5. 测试

```text
python -m pytest tests/test_web.py -q
→ 91 passed

python -m pytest -q
→ 1094 passed, 10 skipped
```

- `tests/test_web.py` 原 89 个测试保留；G2 新增 2 个：
  - `test_report_reader_ships_minimap_and_severity_filter`：模板 ID、CSS 类、JS 函数/状态/`e.key === "j" || e.key === "k"`；
  - `test_report_reader_zoom_and_existing_controls_are_preserved`：缩放控件、既有证据/分页/导出/triage/修复控件仍在。
- `node --check web/static/js/report.js` 通过。
- 全量 1094 高于任务基线 1074；增加的测试包含并行任务新增的用例，未削弱任何旧测试。

## 6. 边界与未做

- 未改 `web/app.py`、`refresh.css`、核验/修复/triage 数据与判定逻辑；
- “严重”档在三类元数据状态下只覆盖 `Major` / `contradict`；样本没有这类条目，因此计数为 0。没有为了截图好看而把 `Unverified` 包装成“严重”；
- 小地图反映当前筛选结果，不显示被筛掉的条目；清空筛选可恢复全量；
- 页图缩放只做显示宽度缩放，不生成新图片、不做 OCR、不改变证据坐标；原图仍受隐私删除策略约束；
- j/k 在输入控件聚焦时刻意不触发，避免边输入边翻页；
- 未做移动端专属截图（本轮验收为 1440/1280）；窄屏 <900px 已加网格回退与跳转输入隐藏策略。
