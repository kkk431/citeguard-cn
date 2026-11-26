# B3 模型不可用降级

## 目标
模型未配置、挂掉、超时或返回非 JSON 时，页面不伪造结论、不把失败说成未收录，用户能看懂下一步。

## 行为
- `/api/support/check`：判官不可用返回 `503 judge_unavailable`，错误文案明确提示检查 `CITEGUARD_JUDGE_BASE_URL / API key`。
- `/support`、`/batch`：`judge_ok=false` 时按钮禁用，并在页面顶部显示原因条；提示配置 DeepSeek key 或本地 judge 端点。
- 整篇分析：`support_meta.judge_available=false`，支持度全部 `not_checked`，不生成 `support/contradict` 假结论；报告仍可查看题录与格式结果。
- `/history`：失败/中断任务保留输入时给出重跑；已完成任务给出查看报告。

## 验证
- 无 key 实例 `http://127.0.0.1:8014`：`/api/support/check` → 503 `judge_unavailable`；`/api/analyze` job `a0028b409a97` 完成，`judge_available=false`、`judged=0`、`not_checked=15`。
- 页面截图：`docs/evidence/shots/opt-B3-judge-unavailable-1.7.40-1440.png`、`opt-B3-batch-judge-unavailable-1.7.40-1440.png`。
- 测试：`tests/test_web.py::test_support_page_explains_unavailable_judge`、`::test_batch_page_explains_unavailable_judge`；全套 1062 passed。
- 数据：`data/experiments/opt_b3_judge_down_2026-11-26.json`。

## 边界
- 未配置判官时不能做支持度判断，这是能力边界，不是“全部不支持”。
- 模型超时与未配置在报告中都归为“未检测”，不区分为“无证据”。
