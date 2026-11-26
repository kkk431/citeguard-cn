# 产品优化执行计划（A–H）

基线：v1.7.36 / 1055 tests（2026-11-26）。当前执行版本见 `web/app.py`。

| 波次 | 项 | 内容 | 状态 |
| --- | --- | --- | --- |
| P0 | A1 | 题录库导入前预览（干跑、重复、缺字段） | ✅ 1.7.37 |
| P0 | A2 | 覆盖缺口看板（按语言、缺字段、下载待补 CSV） | ✅ 1.7.38 |
| P0 | B1 | 长任务进度/断点恢复体验 | ✅ 1.7.39 |
| P0 | C1 | 图表预检的错误/降级状态 | 待做 |
| P1 | D1 | 修复闭环的批量与复检 | 待做 |
| P1 | E1 | Live/CiteMap 使用层降噪 | 待做 |
| P1 | F1 | 解析与 GB/T 修复建议 | 待做 |
| P1 | G1 | 前端入口/阅读器/键盘/状态 | 待做 |
| P2 | H1 | 可观测性/许可/回归 | 待做 |

## A2 验收

- 后端：`GET /api/library/gaps` 返回总条目、完整数、分语言缺字段统计、优先样例；`GET /api/library/gaps.csv` 下载全部条目及缺失字段（UTF-8 BOM）。
- 前端：题录库「覆盖构成」右上「待补清单」打开模态；按语言显示条目/完整/缺 DOI/缺年份/缺摘要；样例标缺项；CSV 下载。
- 证据：`data/experiments/opt_a2_library_gaps_2026-11-26.json`、`opt-A2-library-gaps-1.7.37-1440/1280.png`。
- 边界：语言按题名 CJK 判断；缺字段为启发式；不把缺失等同于引用错误。

## 留档约定

- 数据：`data/experiments/opt_<item>_<date>.json`
- 测试日志：`data/experiments/opt_tests_<date>_*.txt`
- 截图：`docs/evidence/shots/opt-<wave>-<item>-<version>-<viewport>.png`
- 每项同步 `docs/evidence_index.md`、报告、资源清单、提交目录；不改 PPT/视频内容。

## B1 验收
- API：`GET /api/jobs/{id}` 返回 `report_ready/retryable/next_action`；中断且有 `input.txt` → `retry`，完成有报告 → `view_report`，无原文 → `reupload`。
- 历史页：queued/running 时每 3 秒刷新状态与百分比，显示后台继续提示；终态自动刷新出报告/重跑入口。
- 证据：`docs/evidence/shots/opt-B1-history-live-1.7.39-1440.png`、`...-1280.png`、`data/experiments/opt_b1_resume_2026-11-26.json`。
- 边界：服务重启后运行线程不会自动续跑，仍需要点击“重新运行”；B1 保证“可判断/可重跑/退出页面不丢”，不是进程级续跑。

- [x] B3 模型不可用降级：`/support` 与 `/batch` 显示未配置判官的原因条、按钮禁用；无判官时报告保留 `not_checked`，不伪造结论。证据 `data/experiments/opt_b3_judge_down_2026-11-26.json`、截图 `opt-B3-*.png`。
