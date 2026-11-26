# D3/D4：复检 diff 与导出闭环

## 结论

本项把“复检”从一次性的结果列表，补成可读、可键盘操作、可解释空状态的差异视图；把导出从没有范围概念的固定 CSV，补成“全部 / 仅问题条目 / 仅已修条目”三档范围，并在没有可导出条目、或浏览器拒绝下载时给出下一步。所有导出都在浏览器内完成，不上传报告，也没有为了截图而伪造导出内容。

- 真实报告页验证：**16/16 项通过**，无 console error。
- 相关测试：`19 passed`（`tests/test_report_diff_ui.py` + `tests/test_exporters.py`）；`tests/test_web.py` **92 passed**。
- 全量测试：**1129 passed, 10 skipped**；未修改 `web/app.py`、`web/static/css/refresh.css`、`web/templates/base.html`。

## D3：复检 diff 可读化

### 数据契约

沿用后端 `src/citeguard/diff.py` 的只读结果，不在前端重新抓取或推断：

- `summary`：`old_total / new_total / resolved / still / new / status_changed / support_changed / changed`
- `items[i]`：`index / title / kind / status{old,new} / support{old,new} / compliance{old,new} / fixed[] / new[] / still[]`
- `kind`：`resolved / new / still / status / unchanged`
- 每条问题保留 `level / field / message`
- `note`：明确“差异只比较两份报告已保存的字段，不重新联网核验”。

### 页面表现

1. **汇总计数**：显示“已解决 / 仍存在 / 新增 / 状态变化 / 支持度变化”。已解决数读取 `summary.resolved`，同时兼容旧响应的 `summary.fixed`（避免旧接口把已解决显示成 0）。
2. **条目级差异**：每条差异用原生 `<details><summary>`，标题栏显示 kind 标签、标题、`旧状态 → 新状态`；展开后：
   - 字段级 `旧值 → 新值` 行：状态、支持度、合规分；
   - 问题分组：已解决的旧问题、新增问题、仍存在的问题，逐条显示字段、级别、说明；
   - 如果该条只有 kind 变化而没有字段差异，显示“这条没有字段级差异”。
3. **空差异**：明确说明“两份报告没有可见差异”，并给出两个原因和下一步：差异只比较已保存字段；如果刚修改过引文，需要在工作台重新分析生成新报告后再对比。空态不是一张空白卡片。
4. **失败**：显示“对比失败”、HTTP detail 或状态码，并提供下一步“确认旧报告仍存在且可读取；如果刚重新分析，请刷新页面后重试”。
5. **键盘**：打开差异后焦点落到第一条 `summary`；用 Tab 在差异条目间移动，Enter/Space 展开，Esc 关闭检查明细抽屉。原有 `/`、`f`、`t`、`j/k` 等快捷键不受影响。
6. **响应式**：在 1440 和 1280 宽度下，检查抽屉和条目都无横向溢出；`overflow-wrap:anywhere` 与 `min-width:0` 处理长标题、长 DOI/URL。

### 空态的真实性

当前 6 个报告任务中不存在两份内容完全相同的报告，因此没有用真实报告对生成“空差异”截图。空态由静态测试覆盖（文案、原因、下一步），并在文档中明确这一限制；没有用伪造 API 响应截图充数。

## D4：导出范围与批注说明

### 导出范围

导出菜单新增 `CSV 范围` 选择，默认“仅问题条目”：

| 值 | UI 文案 | 规则 |
| --- | --- | --- |
| `problems` | 仅问题条目 | 状态非 `Exact`，或支持度为 `contradict/partial/no_evidence`，或存在 error/warning 合规问题 |
| `fixed` | 仅已修条目 | 条目带 `repair.state === "fixed"`，或 triage 状态为 `fixed` |
| `all` | 全部条目 | 导出全部可解析条目，用于完整备份/人工复核 |

`pending`、`ignored` 不属于“已修”，不会混进 `fixed` 范围。范围在浏览器端过滤，不新增后端参数，因此不需要改 `web/app.py`。

### CSV 内容

`导出所选范围 CSV` 生成带 UTF-8 BOM 的 CSV，文件名带任务与范围：

`citeguard-<job>-<scope>.csv`

列：序号、状态、支持度、题名、作者、年份、期刊/来源、问题字段、核验说明、修复状态、引文原文、人工检索。人工检索列给 CNKI、万方、维普、百度学术的检索链接；不编造文献、不填入不存在的 DOI。所有值来自当前报告 JSON 或修复记录。

空范围不生成空文件：例如没有任何已修条目时选择“仅已修条目”，页面提示“当前范围……没有可导出的条目。请切换范围；若选择‘仅已修’，请先在条目详情里应用修复。”并阻止下载。下载抛错或浏览器拒绝下载时提示“CSV 导出失败……请检查浏览器是否允许下载，或改用‘复制参考文献表’/‘打印 / 存 PDF’”。

### 批注 PDF

导出菜单里的“下载批注 PDF”既有后端路由保持不变（`/api/report/{job}/annotated`），本次只补前端说明和 `annotate.py` 的可复用计划函数：

- 在原文页边标出问题条目的状态、字段问题与引文位置；
- 只使用报告已有字段，不重新联网；
- 找不到页码的条目不猜页，计入“未映射”；
- 已是 `Exact`、支持度不是 `contradict/partial`、且没有 error 的条目不加页边批注。

`annotate.annotation_plan(report)` 返回 `references / indexes / citations / note`，让 UI、测试和 PDF 写入共享同一条判定规则，但不承诺每个批注都能定位到页码。现有响应头/下载逻辑不变。

## 实现与测试

- `src/citeguard/diff.py`：只读复检契约，未改。
- `src/citeguard/exporters.py`：`EXPORT_SCOPES`、`is_problem_reference`、`is_fixed_reference`、`select_report_items`、`refs_from_parsed(scope=...)`；未知范围抛 `ValueError`。
- `src/citeguard/annotate.py`：`needs_annotation`、`annotation_candidates`、`annotation_plan`；`annotate_pdf` 复用同一谓词。
- `web/templates/report.html`：`report_diff.css`、`#export-scope`、导出/批注说明、`#diff-help`、`#diff-result` 的 `aria-live` 与 `role=region`。
- `web/static/js/report.js`：diff 汇总/字段行/问题分组/空态/错误/键盘；导出范围、CSV 列、空态和下载失败提示；修复 `triageState` 在导出 IIFE 中不可见的错误。
- `web/static/css/report_diff.css`：diff 与导出说明的布局、焦点、响应式、打印隐藏。
- `tests/test_report_diff_ui.py`：6 个 D3/D4 契约测试。
- `tests/test_exporters.py`：新增 3 个范围/未知范围测试。
- `data/experiments/opt_d3d4_diff_export.json`：真实浏览器 16 项检查、截图、console error 记录。
- 真实报告：`c674df27a57e`（当前 54 条）对比 `d73ae2dcd2e9`（15 条）；结果为已解决 0、仍存在 0、新增 15、状态变化 0、支持度变化 4。

## 真实浏览器证据

环境：Windows 11，Chromium **156.0.8078.4**（Playwright 1.64.0，headless），服务 `http://127.0.0.1:8013`，任务 `c674df27a57e`。

复现：

```powershell
# 服务已在 8013 运行；如未运行：
$env:PYTHONPATH="src"; python -m uvicorn web.app:app --host 127.0.0.1 --port 8013
# 真实浏览器检查（脚本在临时目录，不属于仓库交付物）
python "$env:TEMP\cg_t40_check.py"
```

| 截图 | 尺寸/字节 | 内容 |
| --- | --- | --- |
| `docs/evidence/shots/opt-D3D4-diff-1440.png` | 1440×1000 / 251,328 | 检查明细 → 复检；汇总 chips；首条展开显示支持度 `not_checked → no_evidence`、合规分 `87 → 80`、已解决/新增/仍存在问题分组 |
| `docs/evidence/shots/opt-D3D4-diff-1280.png` | 1280×800 / 171,119 | 1280 宽度下差异列表完整、无横向溢出 |
| `docs/evidence/shots/opt-D3D4-export-1440.png` | 1440×1000 / 699,906 | 导出菜单展开：CSV 范围、问题条目规则说明、所选范围 CSV、批注 PDF 说明 |

检查还确认：diff CSS 已加载；`#diff-result` 为 `aria-live` region；15 条差异均渲染；第一条 summary 获得焦点；Enter 展开 2+ 字段行；CSV 能真实下载（`citeguard-c674df27a57e-problems.csv`）；文件名带 job/scope；已修范围为空时只提示下一步、不生成假文件；全部范围可导出；无 console error。

## 边界

- 本次只改报告页前端与两个 Python 纯函数模块，不新增后端导出范围参数；CSV 范围完全在浏览器内过滤。
- 复检只比较已保存字段；不会为了“看起来变了”而重新抓取元数据，也不会把未映射页码猜成某一页。
- 没有真实空差异报告对，因此空态只用静态测试与文案验证，没有空态截图。
