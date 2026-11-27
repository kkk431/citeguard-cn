# CiteGuard-CN 产品优化总报告（A–H，v1.7.36 → v1.7.50）

日期：2026-11-27  
基线：v1.7.36 / 1055 tests  
结束：v1.7.50 / 1131 tests（10 skipped）  
约束：不改 PPT/视频内容；不伪造数据/人审/用户反馈；不出现校名校徽/指导教师/内网 IP/key；不为通过测试而改测试。

## 1. 总体验收

| 项 | 结果 |
| --- | --- |
| pytest | **1131 passed, 10 skipped**（90.44 s） |
| verify_artifacts | **137/137** |
| audit_evidence | **304 路径 / 0 missing / 163 登记 / 0 unregistered** |
| 前端审计 | **58/58**（11 页 × 溢出/标题/可访问名/console） |
| e2e smoke | **14/14**（真实报告、批注、5 种导出、证据包、diff） |
| 回归脚本 | `scripts/regression_check.py` 5 步全 0（pytest/verify/audit/licenses/e2e） |
| 版本 | 1.7.37–1.7.50，逐项独立提交；v1.7.49 tag/release latest |

## 2. 逐项交付

### A. 覆盖与题录库

**A1 导入前预览（1.7.37）**  
`POST /api/library/import/preview` 只解析不写库；返回可新增/重复/缺 DOI/缺年份/缺摘要/样例。前端选择文件即预览，确认后才导入。证据 E111、`opt_a1_import_preview_2026-11-26.json`。

**A2 覆盖缺口看板（1.7.38）**  
`GET /api/library/gaps` 按语言统计条目/完整/缺字段，`GET /api/library/gaps.csv` 导出待补清单（UTF-8 BOM）；前端弹窗与样例 chips。真实库 28 条：完整 9（32.1%），中文 17、英文 11。证据 E112。

**A3 题录库仪表盘（1.7.49）**  
`src/citeguard/library_stats.py` + `GET /api/library/dashboard` + 只读弹窗：来源/年份/期刊/重复/完整度/报告命中率/标签。真实库 28 条、6 份报告 129 条引用 56 命中（43.4%）；重复 0、标签 0。证据 E126、`opt_a3_library_dashboard_2026-11-27.json`。  
边界：覆盖率是历史快照（6 份报告，5 份同论文），不外推。

### B. 稳定与降级

**B1 长任务进度/断点恢复（1.7.39）**  
`_job_resume_state` 给每个任务 `report_ready/retryable/next_action`；历史页运行中每 3 秒刷新进度，终态自动 reload 出报告或重跑入口。真实任务 `c674df27a57e` 20%→done 100%，离开页面不中断。证据 E113。

**B2 结果缓存与只补失败（1.7.48，CLI）**  
`ResultCache` 按文件 SHA-256 + canonical options + prompt/audit/judge/schema 版本寻址；本地题录库指纹并入键；`BatchRunner` 复用 done、只补 error、单条重试；失败不缓存。独立复测冷 6614 ms / 热 98 ms（67×，热缓存不是冷启动）。**尚未接 Web 分析入口**，只在脚本/批跑层可用。证据 E125。

**B3 模型不可用降级（1.7.40）**  
`/support`、`/batch` 在判官不可用时显示原因条；`/api/support/check` 返回 503 `judge_unavailable`；无判官分析仍完成，明确 `judge_available=false`、`judged=0`、`not_checked=15`。证据 E114。

### C. 图表预检

**C1 服务状态与重试（1.7.43）**  
`GET /api/figure/status` 返回 available/model/timeout/fallback，不暴露 endpoint/key；页面常驻“视觉模型已就绪/未配置”；502 时人话错误 + 重试，保留输入与结果。证据 E117。

### D. 修复与复检

**D1 批量修复/复检（1.7.44）**  
报告列表勾选，批量 preview/apply，`/repair/verify` 复检；真实 15 条选 2 修 2，复检缺字段 0，撤销回 0。边界：已修不等于正确。证据 E118。

**D3/D4 diff 与导出（1.7.49）**  
diff 显示 resolved/still/new 计数、字段级旧→新、已解决/新增/仍存在问题分组、键盘 details；CSV 范围 problems/fixed/all，空范围不生成假文件；批注说明含字段/页边/未映射且不重新联网。真实页面 16/16 检查、1440/1280 无溢出。证据 E129。

### E. Live / CiteMap

**E1 Live 使用层（1.7.45）**  
三步引导、页面支持矩阵（arXiv/PMC 可用、Wikipedia 有限、出版商不支持）、失败三动作（重试/内置示例/支持度速查）、中文人话错误。证据 E119。

**E2 CiteMap 使用层（1.7.48）**  
三步引导、常驻图例、仅全文筛选、单断言焦点、机器候选独立标识、空态解释；真实 ai_education 4 人工断言/15 篇/4 焦点。证据 E122。

**E3 CiteMap 半自动扩展（1.7.49）**  
离线候选 + 空白人工确认 CSV + promote 门禁（需人工 accept 且显式 `--write-human-layer`）。真实 9 条候选全部 pending，人工层 SHA 未变；**没有人工接受的候选，因此不新增人工证据**。证据 E128。

### F. 解析与 GB/T

**F1 字段级修复建议（1.7.46）**  
修复预览给 `{field, problem, action}`；缺 DOI 只建议 Crossref/期刊页，不猜值；只给动作，不补造缺失字段。证据 E120。

### G. 前端体验

- **G1（1.7.41）**：工作台运行中任务横幅 + 草稿恢复（`citeguard.workspace.draft.v1`）。E115。
- **G2（1.7.48）**：报告阅读器 54 色小地图、严重度筛选、跨页 j/k、页码/条目跳转、页内证据 50–250% 缩放。E123。
- **G3（1.7.49）**：图表 hover/图例/缩放；CiteMap 节点/边 hover、图例过滤、55–250% 缩放/拖拽；105 节点离屏基准 3.2/3.9 ms（`synthetic:true`，不是线上数据）。E127。
- **G4（1.7.48）**：页面过渡/骨架屏/抽屉/toast 队列/命令面板分组/reduced-motion。E124。
- **G5（1.7.42）**：全站 `humanHttpError` 去掉原始 HTTP 状态，统一中文错误与下一步；注入 503 验证输入保留。E116。

### H. 工程质量与收口

**H1 可观测性与回归（1.7.47）**  
`X-Request-ID`、`X-Response-Time-ms`、`/api/metrics`、health uptime/requests_total；不记录请求体/URL/凭据。`regression_check.py` 5 步全 0。证据 E121。

**H2 总报告**  
本文件；材料状态见 `docs/materials_audit.md`；计划见 `docs/optimization/plan.md`（A1–H1 全部 ✅）。

## 3. 真实效果与边界（只列可复核）

- 真实中文论文 22 篇 / 524 条：71.2% 缺 DOI、33.8% 缺页码、39.9% 未被正文引用；217 条中文引文 90.8% 无法只靠免费源核验。
- 20 篇 / 409 条：Exact 125 / Minor 87 / Unverified 197 / Major 0；接本地库后 405 Exact / 4 Minor，确定判定率 1.0。
- 200 次真实字段篡改检出 197（98.5%）；40 条原样基线 28 Exact / 12 Minor / 0 Major；13 条无锚点伪造全部 Unverified，不指控。
- 300 条构造集 macro-F1 0.9841 / acc 0.9833；100 条三人盲标 Fleiss κ 0.98116、产品 99/100、macro-F1 0.987707、κ 0.985894。
- 外部：SciFact 300 条 0.8224；ChartCheck 400 条 0.7628；RefChecker 同集 0.7646。
- 以上是工程/构造/公开集口径，不是“中文论文通用准确率”；人工子集只有 100 条。

## 4. 已知例外与残留风险

1. **PPT 仍 v1.7.35、视频 v1.7.36**：用户明确不改内容；报告/材料数字的版本差异已注明。
2. **佐证 PDF 仍 v1.7.36/18 页**：未追加 A1–H1 优化证据；属于可选材料，未重做。
3. **无公网在线演示**：远程旧部署目录 `/data/xyjiang/aic_mental` 已不存在；报告/提交说明如实写本地/Docker 运行。
4. **B2 未接 Web**：结果缓存只在 CLI/BatchRunner 层；页面分析仍每次重跑。
5. **G3 105 节点为合成基准**：不是线上数据；真实图 29 节点/36 边。
6. **E3 无人工接受候选**：9 条全部 pending；不把机器候选包装成人工证据。
7. **Docker 镜像最近验证 1.7.36**：1.7.37–49 未重建镜像；README/报告未写“已验证 1.7.49”。
8. **Release latest 已到 v1.7.49**，但 release 页面指向 `396c8af`；CI #415/#416 success（`396c8af`、`f1087ee`）；#414 旧提交因 SBOM 未刷新失败，已修。


## 6. G6 / H3 / H4 收尾检查

- **G6**：1280/1440/1920 三视口、6 页面（workspace/library/figure/live/citemap/benchmark）18/18 通过：无横向溢出、控件有可访问名、无 console error；1280 键盘流 58/58；深浅色 20 组对比全过（最紧 light muted/paper 4.63）。
- **H3**：`CITEGUARD_ACCESS_TOKEN` 默认空（本地模式）；`CITEGUARD_RATE_LIMIT_PER_MIN` 默认 120，仅 POST `/api/*`；页面预检 host allowlist + 逐跳重定向校验防 SSRF；3/3 定向测试通过。边界：当前无公网实例，默认值需在公网部署时显式开启。
- **H4**：核心 `requirements.txt` 不含 PyMuPDF/fitz，Docker 只装核心依赖；可选 PyMuPDF 标 AGPL、opt-in；`tests/test_licenses.py` 4/4 通过。
- 证据：`data/experiments/opt_g6_h3_h4_2026-11-27.json`、`docs/optimization/g6_h3_h4.md`、E130。无产品功能/版本变化，不改 PPT/视频/佐证 PDF。

## 5. 复现命令

```bash
python -m pytest tests -q
python scripts/verify_artifacts.py
python scripts/audit_evidence.py
python scripts/regression_check.py --base http://127.0.0.1:8013
python scripts/e2e_smoke.py --base http://127.0.0.1:8013 --pdf data/real_corpus/hanspub_152575.pdf
```

材料：`dist/CiteGuard-CN_技术报告_v1.7.49_2026-11-27.pdf`（15 页）、`dist/submission/`（8 文件）、`dist/CiteGuard-CN_AIC-2026-67377639_v1.7.49.zip`。

---

结论：这一轮把“能跑”补到了“可复核、可恢复、可解释、可复用”，但没有把构造集/热缓存/机器候选包装成通用准确率；未完成的例外在上表逐条列出。


## 2026-11-27 收尾

- B2 缓存接入 Web 分析入口：冷 4.638 s / 热 2.063 s，同 key，库指纹入键。
- Docker `citeguard-cn:1.7.50` 构建成功，容器 `/api/health` 返回 1.7.50；镜像 943,589,044 B。
- 佐证 PDF 追加 A1–H1 优化增量：18 → 20 页，含验收表与 4 张真实截图。
- 报告 v1.7.50 / 15 页；提交目录 8 文件；PPT v1.7.35、视频 v1.7.36 不改。
