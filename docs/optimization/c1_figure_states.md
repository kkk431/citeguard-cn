# C1 图表预检状态与降级

## 目标

图表核验必须先说明“视觉服务现在能不能用”，失败时保留输入并给下一步，不能只抛错误。

## 实现

- `GET /api/figure/status`：`available`、`model`、`timeout_seconds`、`fallback`；不返回服务地址/Key。
- `/figure` 始终显示 `#figure-service-status`：
  - 就绪：显示实际模型（如 Qwen3-VL-8B）与边界“只判一致性，不判原始数据真假”；
  - 未配置：提交按钮禁用，说明 PDF 自动定位仍可用，并给文档链接。
- 视觉服务失败：
  - 后端 502 + 人话 error；
  - 前端显示“核验失败：视觉模型暂时不可用，请稍后重试”，提供「重新核验」；
  - 结论文本与已选文件保留，不重选。
- 不伪造 supported/contradicted；失败即未判定。

## 验证

- Playwright：页面显示“视觉模型已就绪”，注入 502 后出现「重新核验」，输入保留，页面无 `HTTP`。
- 数据：`data/experiments/opt_c1_figure_states_2026-11-26.json`。
- 截图：`opt-C1-figure-ready-1.7.43-1440/1280.png`、`opt-C1-figure-retry-1.7.43-1440/1280.png`。
- 测试：`test_figure_status_and_degrade_ui`、`test_figure_js_offers_retry_without_raw_status`。
