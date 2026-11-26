# A2 覆盖缺口看板

入口：题录库「覆盖构成」→ 右上「待补清单」。

## 功能

- 显示库内总条目、字段完整数与占比、待补条数。
- 按语言（题名含 CJK / 拉丁字母 / 未识别）拆分条目、完整数、缺 DOI、缺年份、缺摘要。
- 优先样例按缺失字段数排序，显示题名、作者、年份、来源、DOI 与缺项标签。
- 「下载 CSV」导出全部条目：序号、题名、作者、年份、期刊/会议、DOI、语言、缺失字段。

## API

- `GET /api/library/gaps`
  - `total`、`complete`、`complete_pct`、`missing`、`by_language`、`samples`（最多 12 条）、`sample_total`、`csv_url`。
- `GET /api/library/gaps.csv`
  - UTF-8 BOM，`text/csv`；每行一条库记录，`缺失字段` 为逗号分隔或「完整」。

## 实测（2026-11-26）

- 库内 28 条；完整 9 条（32.1%），待补 19 条。
- 中文 17 条（完整 9，缺 DOI 4、缺年份 2、缺摘要 4）；英文 11 条（完整 0，缺 DOI 2、缺摘要 10）。
- 1440/1280 无横向溢出、无 console error；CSV 200、`text/csv`、BOM 正确。
- 证据：`data/experiments/opt_a2_library_gaps_2026-11-26.json`、`data/experiments/opt_a2_library_gaps_ui_2026-11-26.json`、`docs/evidence/shots/opt-A2-library-gaps-1.7.38-1440/1280.png`。

## 边界

- 语言判断只看题名是否含 CJK/拉丁字母，不调用语言识别模型。
- 缺字段统计是启发式（去空白后为空即缺），不代表引用错误或元数据一定错误。
- CSV 全量导出，不写回题录库；补字段仍由用户导入/手工编辑完成。
