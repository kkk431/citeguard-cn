# Wave2 独立验收：A3 / G3 / E3 / D3+D4

> 结论先行：**4/4 pass**，无阻断问题。发现 3 条 low 级问题（报告口径、CSV 行数表述、diff 版本下拉竞态），已列在 §7，不影响四项交付的可用性。
>
> 验收人：authority（独立于实现者）；时间：2026-11-27；仓库 HEAD `3c5a433`。
> 本文所有数字均来自本次独立复算或真实浏览器探针，**未复用各任务自报的数字**。

## 1. 结论表

| 任务 | 交付 | 独立验证 | 结论 |
|---|---|---|---|
| A3 题录库仪表盘 | `library_stats.py` + `/api/library/dashboard` + 库页仪表盘 | CLI 复算与提交 JSON 逐键一致（82 键 0 差异）；8 个单测；真实库 28 条 | **pass** |
| G3 图表与地图交互 | 图表 hover/缩放 + CiteMap 图 hover/图例/缩放 + 合成 105 节点基准 | 真实页面 29 节点/36 边、悬停 8 节点+7 边、图例隐藏 15 边、缩放 122%、双击 100%、图表 dataZoom 4.96→95.87；8 个单测 | **pass** |
| E3 CiteMap 半自动扩展 | `citemap_expand.py` + 9 条候选 + 空白确认清单 | 重跑得到 9 条候选、跳过原因一致；人工层 SHA256 前后不变；promote 未显式写层时不改人工层 | **pass** |
| D3+D4 复检 diff 与导出 | diff 可读化 + 导出范围/批注说明 | 真实页面 15 条 diff、`已解决 0/仍存在 0/新增 15/支持度变化 4`、三种导出范围、CSV 54 行标题全部来自报告；6+13 个单测 | **pass** |

## 2. 独立验收门（全仓）

| 门 | 命令 | 实测 |
|---|---|---|
| 全量测试 | `python -m pytest tests -q` | **1129 passed, 10 skipped in 95.35s**，exit 0（基线 1095 passed；新增用例来自四项交付） |
| 产物核验 | `python scripts/verify_artifacts.py` | **[OK] all 137 checks passed**，exit 0 |
| 证据核验 | `python scripts/audit_evidence.py` | `paths checked: 304 / missing: 0 / shots registered: 163; unregistered: 0` |
| 分项测试 | `pytest tests/test_library_stats.py tests/test_charts_interaction.py tests/test_citemap_expand.py tests/test_exporters.py tests/test_report_diff_ui.py -q` | **43 passed**（8 + 8 + 8 + 13 + 6） |
| 真实页面探针 | Playwright + Edge `158.0.4370.33`，1440×900 / 1280×800 | **54 checks / 54 passed**；console errors 0；failed requests 0 |
| 服务 | `http://127.0.0.1:8013/api/health` | 200 |

探针覆盖：`/report/c674df27a57e`（复检 diff + 导出，54 条引用）、`/citemap?topic=ai_education`（真实证据图）、`/report/05304bf55ea7`（检查明细 → 图表，15 条引用 3 张图）。

## 3. A3 题录库仪表盘（pass）

### 3.1 独立复算

```bash
PYTHONPATH=src python -m citeguard.library_stats \
  --library data/library/library.json \
  --reports-glob "data/jobs/*/report.json" \
  --out "$TEMP/t41_a3.json"
# library=28 complete=9/28 sources=4 years=13 duplicates=0 coverage=43.4%
```

把输出与提交的 `data/experiments/opt_a3_library_dashboard_2026-11-27.json` 展平成 82 个键对比（排除 `generated_at`）：**0 处差异**。

| 指标 | 实测 |
|---|---|
| 条目 | 28；完整 9（32.1%）；缺 DOI 6 / 缺年份 2 / 缺摘要 14 |
| 来源 | local:ris 20（71.4%，完整 6）/ local:endnote 5 / manual-bulk 2 / manual 1 |
| 年份 | 2011–2026，中位 2021，缺失 2；13 个不同年份 |
| 期刊 | 23 个，无缺失 |
| 重复组 | 0 |
| 语言 | zh 17 / en 11（题名启发式） |
| 标签 | 0/28，`note` 明确「标签由用户维护，不是自动语义分类」 |
| 覆盖率 | 6 份报告 / 129 条引用 / 56 命中 = 43.4% |

### 3.2 边界核对

- 标签只做统计、不做语义分类：代码 docstring 与输出 `tags.note` 一致；文档 §3 写明「本库 0 个标签是真实状态，不代表无主题」。
- 覆盖率是历史快照、报告集不是抽样、重复组保守、语言为题名启发式、无入馆趋势（无 `created_at`，不拿 `year` 冒充）、只读不联网——与文档 §3 逐条一致。
- 页面接入（`web/app.py` 的 `GET /api/library/dashboard`、`library.html/js`、`refresh.css`）由队长完成，A3 文档 §6 已标注；A3 自报「未改 web」指的是数据层任务本身（见 §7 F1）。

## 4. G3 图表与地图交互（pass）

真实页面探针（两个视口结果一致）：

| 检查 | 实测 |
|---|---|
| 证据图规模 | **29 节点 / 36 边**（真实 `ai_education`） |
| 节点悬停 | **8 节点 + 7 边** `.is-hot`，状态栏「连接 7 条关系（悬停仅高亮…）」 |
| 图例过滤（摘要级） | `aria-pressed` true→false，隐藏 **15/15** 条摘要边，`visible_levels="fulltext,none"` |
| 缩放按钮 | `122%`（`data-zoom="122"`），范围 55%–250% |
| 双击空白 | 复位 `100%` |
| 合成基准 | `{synthetic:true, nodes:105, edges:116, render_ms:2.2/3.7}`（离屏渲染，JSON 明确标注合成） |
| 图表 | 3 张（`rchart-status/support/compliance`），`dataZoom` 1 个，Ctrl+滚轮 `[0,100] → [4.96,95.87]`，双击复位 `[0,100]`，悬停 tooltip 正常 |

边界核对：缩放只改变视口变换、图例只隐藏连线，均不改数据与判定；1280 下地图舞台保持既有 `min-width:1080px` 的舞台内横向滚动，页面级溢出 0；图表需打开「检查明细 → 图表」才初始化（现有页面结构）。测试：8 个交互单测 + `test_web.py` 92 passed。

## 5. E3 CiteMap 半自动扩展（pass）

独立重跑（输出到临时目录，不写仓库）：

```bash
python scripts/citemap_expand.py --topic ai_education --limit 15 --min-candidates 5 \
  --output-dir "$TEMP/t41_e3" --summary "$TEMP/t41_e3.json"
```

- 候选 **9 条**（9 篇来源论文），跳过 `no_abstract 1 / duplicate 1 / no_sentence 4`；与提交 JSON 一致。
- 全部 `machine=true`、`needs_human=true`、`status=pending`；边界文案写明「候选不是证据、未人审、不能宣称准确率」。
- 人工层（`data/evidence_map/**` 除 `expansion/`）SHA256 前后逐文件一致；`--promote ... --decision accept`（**不加** `--write-human-layer`）只打印 patch，`human_layer_written: false`，人工层哈希不变。
- 空白确认清单 9 行，`decision/note/reviewer` 全空，供人工填写。
- 说明：promote 默认会把 patch 写到 `data/evidence_map/expansion/promotions/`（不写人工层），本次验收产生的一个 patch 文件已清理，未进交付。

## 6. D3+D4 复检 diff 与导出（pass）

| 检查 | 实测（1440/1280 一致） |
|---|---|
| diff 渲染 | **15 条**，对照 `d73ae2dcd2e9`；摘要 `已解决 0 / 仍存在 0 / 新增 15 / 状态变化 0 / 支持度变化 4` |
| 键盘 | 条目聚焦，Enter 展开旧→新（`old_new_tokens:3`） |
| 导出范围 | 3 项：`problems / fixed / all` |
| problems CSV | `citeguard-c674df27a57e-problems.csv`，54 条数据行（文件 55 行=表头+54）；标题集合 ⊆ 报告引用标题（53 个唯一标题，因报告内有同名论文） |
| all CSV | 54 条数据行 |
| fixed 空范围 | 不触发下载，toast「当前范围「仅已修条目」没有可导出的条目…」 |
| 批注说明 | 含「找不到页码的条目不猜页，会计入未映射」 |
| 页面 | 横向溢出 0、console errors 0 |

代码核对：`exporters.py` 有 `EXPORT_SCOPES=("all","problems","fixed")`、`select_report_items()`（未知范围抛 `ValueError`）；导出筛选在浏览器侧完成，不新增后端参数；diff 只比较已保存字段，不重新抓取、不猜页码。测试：`test_exporters.py` 13 + `test_report_diff_ui.py` 6。

## 7. Findings

| ID | 级别 | 问题 | 建议修复 | 责任文件 |
|---|---|---|---|---|
| F1 | low | t37 自报「未改 web/app.py、模板/JS/CSS」，但提交 `4aa9572` 含 `web/app.py` +14、`library.js` +171、`library.html` +11、`refresh.css` +10；A3 文档 §6 把 `web/app.py` 标为「队长接入」，实际是队长把页面接入合进了同一提交，自报与提交口径不一致 | 后续把「数据层」与「队长接入」分 commit，或在自报中写明页面接入由队长在同一提交完成 | `docs/optimization/a3_library_dashboard.md`、`web/app.py` |
| F2 | low | D3/D4 证据 JSON 的 `rows=55` 实为「表头 + 54 条数据行」，容易被读成 55 条引用 | 在 JSON 中区分 `header` 与 `data_rows`（或写 `lines=55`），文档同步 | `data/experiments/opt_d3d4_diff_export.json`、`docs/optimization/d3d4_repair_diff_export.md` |
| F3 | low | 报告页「对比历史报告」的版本下拉异步加载，且无 loading 态/禁用按钮；加载完成前点击会按默认版本对比（本次在 1280 首次读到空 value，摘要为「支持度变化 2」而非 4） | 下拉填充前禁用「对比」或在按钮上显示加载态，避免静默回退到默认版本 | `web/static/js/report.js`、`web/templates/report.html` |

说明：G3 的 105 节点为**合成**离屏基准（`synthetic:true`），不能当作线上 105 节点性能，文档与 JSON 均已明确标注，不计为缺陷。

## 8. 复现命令

```bash
# 全仓门
python -m pytest tests -q
python scripts/verify_artifacts.py
python scripts/audit_evidence.py

# A3 复算（与提交 JSON 逐键对比）
PYTHONPATH=src python -m citeguard.library_stats --library data/library/library.json \
  --reports-glob "data/jobs/*/report.json" --out "$TEMP/t41_a3.json"

# E3 重跑（不写仓库）
python scripts/citemap_expand.py --topic ai_education --limit 15 --min-candidates 5 \
  --output-dir "$TEMP/t41_e3" --summary "$TEMP/t41_e3.json"

# 页面探针（需 8013 服务；Edge + Playwright）
python "$TEMP/t41_pages.py"   # 54 checks，JSON 写到 $TEMP/t41_pages.json
```

## 9. 限制

- 页面探针只覆盖 Edge（Chromium）1440×900 / 1280×800 桌面视口，未覆盖 Firefox/Safari、移动端与触屏手势。
- 探针对接的是 2026-11-27 已运行的 `127.0.0.1:8013` 服务；未在此次验收中重启服务或修改产品代码。
- A3 覆盖率是历史快照（6 份报告，其中 5 份为同一论文），不能外推。
- 本验收只做工程与边界核对，没有外部人工标注或第三方准确性评测。

## 10. 复审修复（2026-11-27，Wave2 发布前）

| ID | 处置 | 证据 |
|---|---|---|
| F1 | 不改历史提交；在 A3 文档与本节写明：`4aa9572` 同时含队长页面接入，自报的“未改 web”仅指数据层交付时刻 | `docs/optimization/a3_library_dashboard.md` §6、本表 |
| F2 | `opt_d3d4_diff_export.json` 改为“54 data rows (55 incl header)”；D3/D4 文档同步 | JSON 两处 evidence、`docs/optimization/d3d4_repair_diff_export.md` |
| F3 | 版本下拉加载期间禁用「对比」按钮，加载成功后再启用；失败/无候选保持禁用 | `web/static/js/report.js`、`tests/test_report_diff_ui.py::test_diff_run_is_disabled_until_versions_finish_loading`（7 passed） |

复审后：`tests/test_report_diff_ui.py` 7 passed；`node --check report.js` 通过。
