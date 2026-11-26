# B1 长任务进度与断点恢复

目标：用户离开页面、服务重启或任务失败后，仍能判断任务状态，并在有保留原文时重跑，而不是只看到“已中断”。

## 实现
- `GET /api/jobs/{id}` 在原始 job 字段上增加 `report_ready`、`retryable`、`next_action`。
- `next_action`：queued/running → wait；有 report.json → view_report；有 input.txt 且未完成 → retry；否则 reupload。
- `/api/jobs` 返回 `progress/stage/filename`，历史页据此做 3 秒轮询，更新状态 pill 与百分比。
- 历史页顶部显示后台运行提示；进入终态后 700 ms 自动刷新，出现报告/重跑入口。

## 验收
- 真实任务 `c674df27a57e` 在 20% 时截图；离开页面后任务仍在后台继续。
- `tests/test_web.py` 两条用例覆盖 retry/view_report 分支与历史页轮询数据。
- `pytest tests -q` 1060 passed, 10 skipped；`verify_artifacts` 137/137。

## 边界
- 这不是进程级断点续跑：服务重启后线程不会自动复活；只要 `input.txt` 还在，用户可一键重跑。
- 成功任务会清理 `input.txt`，所以“重跑成功任务”不属于 B1。
