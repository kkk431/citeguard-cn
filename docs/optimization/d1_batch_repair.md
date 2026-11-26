# D1 修复闭环的批量与复检

## 目标

修复不是“点一下全修”：要能选几条、看清将改什么、应用后复检，且不把“已修”当成“正确”。

## 实现

- 报告列表每条加 `ref-select`；勾选后工具栏「修复所选 N 条」打开批量预览。
- 预览复用 `/repair/preview?indexes=1,2`；显示总/可修/已修，逐条 diff、fixes、missing。
- 应用复用 `/repair/apply`；仍保留 30 分钟撤销。
- 新增 `GET /api/report/{job_id}/repair/verify`：
  - 取当前 active report（含 fixed）；
  - 逐条重新解析修复文本，检查仍缺的作者/题名/年/刊/卷/期/页；
  - 返回 `fixed/unfixed/missing_total/entries_with_missing/message`。
- 页面「复检修复结果」显示已修/未修/缺字段数；仍有缺字段时逐条列出，不显示“通过”。

## 验证

- 真实报告 `d73ae2dcd2e9`：选第 1、2 条 → 批量预览可修 2 → 应用 → 复检“已修 2/15，未修 13，复检缺字段 0 项” → 撤销回 0。
- 截图：`opt-D1-batch-select-1.7.44-1440/1280.png`、`opt-D1-batch-preview...`、`opt-D1-verify...`。
- 数据：`data/experiments/opt_d1_batch_repair_2026-11-26.json`。
- 测试：`test_verify_reports_remaining_missing_after_batch_repair`、`test_report_has_batch_repair_and_verify_controls`。

## 边界

- 复检只检查“修复文本的字段是否仍缺”，不保证语义正确、不替代人工核对。
- 修复仍只对已解析字段重排，不补缺失字段；缺字段必须回到数据源或人工。
