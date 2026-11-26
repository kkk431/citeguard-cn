# F1：修复预览的字段级建议（1.7.46）

## 目标

修复预览不能只显示“将重排成什么”，还要告诉用户每一条**为什么不能直接修、下一步去哪里补**。
F1 的原则：**只给动作，不猜缺失值**。

## 实现

- `src/citeguard/fix.py`
  - `_SUGGESTION_TEXT`：缺作者/题名/来源/年份/DOI 的问题与动作。
  - `_FIX_TEXT`：类型码、年份格式、作者分隔符、DOI 格式、标点等可自动修复项的动作。
  - `_suggestions(parsed, missing, fixes)`：返回 `{field, problem, action}`，最多 5 条；缺 DOI 只建议去 Crossref/期刊页补，不生成 DOI。
  - `fix_entry()` 返回 `suggestions`；`build_patch()` 的 entries 透传。
- `web/static/js/report.js`：修复预览每项显示“修复建议”列表（最多 4 条）。
- `web/static/css/refresh.css`：`.repair-suggestions*`，深浅色可读。

## 验收

- `tests/test_fix.py::test_fix_entry_returns_actionable_non_fabricated_suggestions`：缺来源/年份/DOI 均有建议，action/problem 非空。
- `tests/test_repair_api.py`：preview entries 带 suggestions。
- 真实任务 `d73ae2dcd2e9`：选 [1][2] 打开修复预览，1440/1280 均出现「修复建议」；[1] 显示 DOI/类型码/年份/标点，[2] 显示类型码/年份/DOI/标点。
- 截图：`docs/evidence/shots/opt-F1-repair-suggestions-1.7.46-1440.png`、`...-1280.png`。
- 数据：`data/experiments/opt_f1_repair_suggestions_2026-11-26.json`。

## 边界

- 建议不是自动补全；缺 DOI 不生成、缺作者不猜。
- 应用后仍需人工确认；已修不等于正确。
- 只覆盖修复预览，不改报告正文/原条目。
