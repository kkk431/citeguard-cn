# A3 题录库仪表盘（数据层）

把题录库从「列表 + 覆盖缺口」升级为可解释的仪表盘数据：来源构成、年份分布、期刊/会议 Top、重复组、字段完整度、报告覆盖率、标签分布。本任务只做**数据层**，页面与 API 由队长接；不修改 `web/app.py`、模板、JS、CSS。

> 口径说明（t41 F1）：雷达自报“未改 web”指数据层交付时点；随后队长把 API/UI 接入并入同一提交 `4aa9572`，所以该提交实际含 `web/app.py`、`library.js`、`library.html`、`refresh.css`。不是数据层越界。

## 1. 字段契约

入口：`citeguard.library_stats.summarize(library, reports=None, *, top_venues=8, generated_at=None)`，返回可 `json.dumps` 的 dict。`reports` 可传已解析的报告 dict 列表，也可传 `report.json` 路径列表。

| 顶层键 | 内容 |
| --- | --- |
| `schema` | 快照结构版本，当前 `1` |
| `generated_at` | 生成时间（ISO 8601，本地时区偏移由调用方决定） |
| `library` | `total`、`path`、`with_doi`、`with_year`、`with_venue`、`with_abstract` |
| `sources` | `total`；`rows[]`：`source`、`total`、`pct`、`complete`、`missing_fields` |
| `years` | `total`、`with_year`、`missing`、`min`、`max`、`median`（一位小数）、`by_year[]`（`year`/`count`/`pct`，升序） |
| `venues` | `unique`、`missing`、`top[]`（`venue`/`count`/`pct`，按条数降序，默认前 8） |
| `duplicates` | `group_count`、`entries_in_groups`、`groups[]`：`reason`（`doi` / `title_year` / `doi+title_year`）、`ids`（0 基下标）、`count`、`titles`、`dois`、`years` |
| `completeness.overall` | `total`、`complete`、`pct`、`missing_fields`（按必填字段） |
| `completeness.fields` | 每个字段的 `present` / `pct`：title、authors、venue、year、volume、issue、pages、doi、url、abstract、doc_type、source、tags |
| `completeness.by_source` / `by_language` / `by_tag` | 与 `sources.rows` 同构：`key`、`total`、`complete`、`missing_fields` |
| `tags` | `unique`、`tagged`、`untagged`、`total`、`rows[]`（`tag`/`count`/`pct`）、`note` |
| `coverage` | `reports_provided`、`reports`、`skipped`、`references`、`library_hits`、`pct`、`by_report[]`、`trend[]`、`time_axis`、`entries`、`note` |
| `notes` | 三条固定口径：缺失字段不是错误、标签是用户维护、语言由题名推断 |

**完整度规则（与 A2 缺口看板一致）**：`complete = doi / year / venue / pages / abstract 均非空`。真实库因此是 `9/28 = 32.1%`，与 A2 的 `opt_a2_library_gaps_2026-11-26.json` 对齐；缺失只降完整度，不报错、不丢条目。

**语言**：`language_of(title)`，题名含 CJK → `zh`，否则含拉丁字母 → `en`，否则 `unknown`。这是展示用启发式，不做语言识别。

**重复组**：复用 `Library.find_duplicates()`：DOI 相同（忽略 `https://doi.org/` 前缀与大小写）或 `norm_title + year` 相同；组内条目只报告不合并，`ids` 是 0 基下标。

**覆盖率**：对传入的报告逐条统计参考文献，命中条件为 `references[].verify.doi_status == "local"` 或 `verify.sources` 含 `local` 或 `verify.best.source == "local"`；`pct = library_hits / references`。报告不可读时进入 `skipped`，不影响其余统计。

**覆盖趋势**：`coverage.trend[]` 按报告的 `generated_at` 月份聚合（报告数量/参考文献/命中/百分比）。这是「报告按月的库覆盖率」，不是「条目入馆趋势」；`coverage.entries` 单独统计 `LibraryEntry.created_at`，当前存储格式没有该字段，所以 `entries_with_created_at=0` 且带说明，不猜测。

## 2. 真实库数字

生成：2026-11-27T00:44:09，输入 `data/library/library.json`（28 条）+ `data/jobs/*/report.json`（6 份报告）。落盘 `data/experiments/opt_a3_library_dashboard_2026-11-27.json`（约 5.4 KB）。

| 指标 | 值 |
| --- | --- |
| 条目 | 28（有 DOI 22 / 有年份 26 / 有期刊 28 / 有摘要 14） |
| 来源 | `local:ris` 20（71.4%）、`local:endnote` 5（17.9%）、`manual-bulk` 2（7.1%）、`manual` 1（3.6%） |
| 年份 | 2011–2026，中位数 2021；缺失 2 条；共 13 个不同年份 |
| 期刊/会议 | 23 个不同值，无缺失；Top：Chinese Science Bulletin (Chinese Version)、International Forum of Allergy & Rhinology、亚洲临床医学杂志各 2 条 |
| 重复组 | 0 组（DOI 与 norm_title+year 均未发现重复） |
| 完整度 | 9/28（32.1%）；缺 DOI 6、年份 2、期刊 0、页码 6、摘要 14 |
| 语言 | zh 17（完整 9）、en 11（完整 0）、unknown 0 |
| 标签 | 标签 0 个；已打标签 0 条、未打标签 28 条 |
| 覆盖率 | 6 份报告、129 条参考文献、命中 56 条 → **43.4%** |
| 趋势 | 2026-11：6 份报告、129 条、命中 56、43.4%（报告均在本月生成，只有一个月度点） |

各报告的覆盖：5 份 15 条的论文报告各命中 11 条（73.3%），1 份 54 条的报告命中 1 条（1.9%，主题不同）。`skipped=[]`。

## 3. 边界

- **覆盖率是历史快照**：命中来自报告生成时写入的 `verify` 字段；之后题录库新增条目**不会**回填旧报告，覆盖率只对当时那次核验负责。
- **报告集不是抽样**：本次直接用了 `data/jobs/` 下全部 6 份可用报告，其中 5 份是同一篇论文的重复分析、1 份是不同主题；43.4% 只描述这批报告，不能外推为「库覆盖了 43.4% 的中文文献」。
- **重复组保守**：只按共享 DOI 或 `norm_title+year` 判重；同题名但年份不同、或题名差异较大（作者拼接、缩写）不会进组；也不自动合并。
- **标签是用户维护的**：本库 0 个标签，`tags.rows` 为空是真实状态，不代表「无主题」；统计不做语义分类。
- **语言是题名启发式**：中英混排题名会归 `zh`；`unknown` 只在题名没有 CJK 也没有拉丁字母时出现。
- **无入馆趋势**：当前 `LibraryEntry` 没有 `created_at`，`coverage.entries.months` 为空并附说明；不拿 `year` 冒充入馆月份。
- **只读**：模块不写回题录库、不联网、不做合并；页面接入由队长完成。
- **完整度口径与 A2 一致**：若 A2 的必填字段集变化，两处需同步，否则两个页面会对同一条目给出不同完整度。

## 4. 复现

```powershell
cd D:\ai+ky\citeguard
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='src'
python -m citeguard.library_stats `
  --library data/library/library.json `
  --reports-glob "data/jobs/*/report.json" `
  --out data/experiments/opt_a3_library_dashboard_2026-11-27.json
python -m pytest tests/test_library_stats.py -q
```

CLI 输出一行摘要（`library=28 complete=9/28 sources=4 years=13 duplicates=0 coverage=43.4%`）；不传 `--reports`/`--reports-glob` 时 `coverage.reports_provided=false`，覆盖率部分为 0 并带说明。

## 5. 测试

`tests/test_library_stats.py` 共 8 例：空库、DOI/题名+年份重复组、年份与来源分布、标签（用户维护 + 大小写归并）、完整度/语言/缺字段不报错、报告覆盖率与月度趋势、坏报告跳过、JSON 可序列化与字段齐全。

## 6. 文件

- `src/citeguard/library_stats.py`（新增）：`summarize`、`duplicate_summary`、`coverage_summary`、`language_of`、CLI。
- `tests/test_library_stats.py`（新增）：8 例。
- `data/experiments/opt_a3_library_dashboard_2026-11-27.json`（新增）：真实库快照。
- 本文件 `docs/optimization/a3_library_dashboard.md`（新增）。
- `web/app.py`（队长接入）：`GET /api/library/dashboard`，把 `data/jobs/*/report.json` 作为只读报告路径传给 `summarize`。
- `web/templates/library.html` + `web/static/js/library.js`：工具栏「库仪表盘」与只读弹窗（来源/年份/期刊/按语言/报告命中率/说明），不写入任何数据。
- `tests/test_web.py::test_library_dashboard_api_returns_snapshot`：端到端验证返回的 total/完整度/来源/年份/覆盖率字段。
- 证据：`docs/evidence/shots/opt-A3-library-dashboard-1.7.48-1440.png`、`...-1280.png`；`data/experiments/opt_a3_library_dashboard_ui_2026-11-27.json`。

未改：`local_library.py`；仪表盘只读。
