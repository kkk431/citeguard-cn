# 产品优化执行计划（A–H）

基线：v1.7.36 / 1055 tests（2026-11-26）。当前执行版本见 `web/app.py`。

| 波次 | 项 | 内容 | 状态 |
| --- | --- | --- | --- |
| P0 | A1 | 题录库导入前预览（干跑、重复、缺字段） | ✅ 1.7.37 |
| P0 | A2 | 覆盖缺口看板（按语言、缺字段、下载待补 CSV） | ✅ 1.7.38 |
| P1 | A3 | 题录库仪表盘（来源/年份/期刊/完整度/命中率） | ✅ 数据层 + UI（1.7.48，待 Wave2 发布） |
| P1 | G3 | 图表/证据图交互（hover/图例/缩放/105 节点） | ✅ 1.7.48（待 Wave2 发布） |
| P0 | B1 | 长任务进度/断点恢复体验 | ✅ 1.7.39 |
| P0 | C1 | 图表预检的错误/降级状态 | ✅ 1.7.43 |
| P1 | D1 | 修复闭环的批量与复检 | ✅ 1.7.44 |
| P1 | E1 | Live/CiteMap 使用层降噪 | ✅ 1.7.45 |
| P1 | F1 | 解析与 GB/T 修复建议 | ✅ 1.7.46 |
| P1 | G1 | 前端入口/阅读器/键盘/状态 | ✅ 1.7.41 |
| P1 | G5 | 状态与错误：不露 HTTP，给下一步 | ✅ 1.7.42 |
| P2 | H1 | 可观测性/许可/回归 | ✅ 1.7.47 |
| P1 | F1 | 解析与 GB/T 修复建议（缺值不猜、给动作） | ✅ 1.7.46 |
| P2 | B2 | 内容寻址结果缓存 + 失败只补跑（CLI/BatchRunner） | ✅ 1.7.48 |
| P1 | E2 | CiteMap 使用层：引导/图例/仅全文/焦点 | ✅ 1.7.48 |
| P1 | G2 | 报告阅读器：小地图/严重度/跳转/缩放 | ✅ 1.7.48 |
| P1 | G4 | 微交互：骨架屏/过渡/toast/命令面板/reduced-motion | ✅ 1.7.48 |

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

- [x] G1 入口与任务路径：工作台显示运行中任务横幅；粘贴文本/支持度/图表勾选写入 localStorage，刷新恢复，提交后清空。证据 `data/experiments/opt_g1_entry_state_2026-11-26.json`、截图 `opt-G1-*.png`。


## G5 验收

- [x] 前端统一 `humanHttpError`，不出现 `HTTP 5xx`；注入 503 显示“核验失败：上游判官暂时不可用，请稍后重试”，输入保留。
- [x] loading/empty/unsupported 状态保留说明；不为错误编造结果。
- 证据：`data/experiments/opt_g5_states_2026-11-26.json`、`docs/evidence/shots/opt-G5-human-error-1.7.42-1440.png`、`...1280.png`、`opt-G5-human-error-panel-1.7.42-1440.png`；E116。
- 测试：1065 passed；`tests/test_web.py` 两项静态检查 + Playwright 真实 503。


## C1 验收

- [x] `/api/figure/status` 返回 `available/model/timeout_seconds/fallback`，不暴露 endpoint/API key。
- [x] 图表页始终显示服务状态：就绪时说明模型与“只判一致性”；未配置时禁用提交并给配置路径。
- [x] 视觉服务失败时显示人话原因 + “重新核验”，保留结论与文件；不伪造结论。
- 证据：`data/experiments/opt_c1_figure_states_2026-11-26.json`、`docs/evidence/shots/opt-C1-figure-ready-1.7.43-1440.png`、`opt-C1-figure-retry-1.7.43-1440.png`、1280 版本；E117。
- 测试：1067 passed。


## D1 验收

- [x] 报告列表每条前可勾选；工具栏「修复所选 N 条」按选择打开批量预览。
- [x] 批量预览显示总条数/可修/已修；应用后显示「复检修复结果」。
- [x] `GET /api/report/{id}/repair/verify` 逐条复检已修文本，缺字段明示；不把“修过”写成“正确”。
- 证据：`data/experiments/opt_d1_batch_repair_2026-11-26.json`、`opt-D1-batch-select/preview/verify-1.7.44-1440/1280.png`；E118。
- 测试：1069 passed（含 verify endpoint/UI 契约）。


## E1 验收

- [x] Live 页有 3 步引导：贴一句 → 补页面（可选）→ 看证据。
- [x] 页面支持矩阵可见：arXiv/PMC 可用、Wikipedia 有限、Nature/Springer/MDPI 不支持；点开解释原因。
- [x] 失败三动作：重试、用内置示例、去支持度速查；错误为中文人话，不露 raw JSON/HTTP。
- 证据：`data/experiments/opt_e1_live_ux_2026-11-26.json`、`opt-E1-live-guide-1.7.45-1440/1280.png`、`opt-E1-live-failure-actions-1.7.45-1440/1280.png`；E119。
- 测试：1071 passed（页面支持矩阵/失败动作/中文错误助手）。


## H1 验收

- [x] 请求 ID/延迟头；`/api/metrics`；health uptime/requests_total；不记录请求体/URL/凭据。
- [x] `scripts/regression_check.py` 跑 pytest/verify/audit/licenses/可选 e2e，5 步全 0。
- [x] 许可无新增依赖；无新第三方组件。
- 证据：`data/experiments/opt_h1_regression_2026-11-26T14-58-03Z.json`、`opt_tests_2026-11-26T14-58-03Z.txt`、`opt_h1_observability_2026-11-26.json`；E121。
