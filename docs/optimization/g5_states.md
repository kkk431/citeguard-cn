# G5 状态与错误

## 目标

用户看到的不是 `HTTP 502`、`[object Object]` 或只有一句“失败”，而是：
1. 发生了什么（人话）；
2. 下一步做什么；
3. 输入还在，不用重填。

## 实现

- 新增 `web/static/js/errors.js`，全局 `window.humanHttpError(status, detail, fallback)`：
  - 去掉 `HTTP 503` 之类原始状态码；
  - 兼容 `{detail:{message}}`；
  - 400/401/403/404/409/413/422/429/5xx 给默认中文提示；
  - 无 detail 时用调用方 fallback。
- `web/templates/base.html` 在所有页面脚本前加载 `errors.js`。
- 所有页面脚本不再拼 `"HTTP " + status`：
  - 工作台、报告、对比、批量、题录库、支持度、图表、CiteMap、Live、Word 任务窗格。
- 现有 loading / empty / unsupported 状态保留：
  - 按钮/结果区 `aria-live`；加载中不重复提交；
  - CiteMap 空主题/校验失败、Live 不支持的页面仍显式说明原因。

## 验证

- `tests/test_web.py::test_js_never_exposes_raw_http_status`：扫描 `web/static/js/*.js`，不允许出现 `HTTP `。
- `tests/test_web.py::test_base_loads_human_error_helper`：页面必须加载 `errors.js`。
- Playwright 注入 503（`HTTP 503 上游判官暂时不可用`），页面显示“核验失败：上游判官暂时不可用，请稍后重试”，输入保留。
- 证据：`data/experiments/opt_g5_states_2026-11-26.json`；
  `docs/evidence/shots/opt-G5-human-error-1.7.42-1440.png`、`...1280.png`、`opt-G5-human-error-panel-1.7.42-1440.png`。

## 边界

- 这是前端展示层，不改变后端真实状态码；API 仍按规范返回 4xx/5xx。
- 503 时不会伪造结果，只说明“没有完成”。
