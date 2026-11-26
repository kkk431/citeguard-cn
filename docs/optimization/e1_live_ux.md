# E1 Live 使用层降噪

## 目标

用户打开 Live，三秒内知道：贴什么、支持哪些页面、失败时下一步做什么；不把“无证据”误读成“造假”。

## 实现

- 三步引导：贴一句 → 补页面（可选）→ 看证据；每步一句人话说明。
- 页面支持矩阵：arXiv 可用、PMC 可用、Wikipedia 有限、Nature/Springer/MDPI 不支持；折叠说明“出版商 Bot 墙、中文页未验证”，并给出替代路径。
- 失败三动作：重试、用内置示例、去支持度速查。
- 修 `errors.js` 历史乱码：中文提示改为正常 UTF-8；`humanHttpError` 支持 `{detail:{code,message}}`，不再把对象 JSON.stringify 到页面。
- Live 错误面板只显示 `detail.message`，不露 raw JSON。

## 验证

- 截图 1440/1280：`opt-E1-live-guide-1.7.45-*.png`、`opt-E1-live-failure-actions-1.7.45-*.png`。
- Playwright 注入 503：页面显示“上游判官暂时不可用”+3 个动作，输入保留。
- 数据：`data/experiments/opt_e1_live_ux_2026-11-26.json`。
- 测试：`test_live_page_has_support_matrix_steps_and_failure_actions`、`test_live_error_helpers_keep_chinese_and_nested_detail`。

## 边界

- 支持矩阵指“能否读取页面 HTML”，不是“能否判断这句话为真”。
- Wikipedia 只做有限读取；出版商页服务端仍不支持，如实写。
