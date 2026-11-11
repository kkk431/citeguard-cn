# 国一冲刺执行清单（项目本身）

> 状态：`[ ]` 未开始 · `[~]` 进行中 · `[x]` 完成且有证据
> 规则：每个 `[x]` 必须能在 `docs/evidence_index.md` 找到“数字 / JSON / 命令 / 截图”；
> 没勾完本 Phase，不进入下一个 Phase。

基线：0.9.84 · 513 tests · 137 checks · 22 篇语料 529 条 clean 1.0
（版本随 Phase 0 提交更新为 0.9.85，基线数字保持可复现）

## Phase 0 · 冻结与合规

- [x] PyMuPDF 从核心依赖移除，改为可选 `requirements-optional-layout.txt`
- [x] Docker 镜像用新 requirements 重建并通过 health（`citeguard-cn:0.9.85`，18080 返回 0.9.85/offline）
- [x] `docs/licenses.md`：全依赖 SPDX + 数据/模型许可证
- [x] `docs/evidence_index.md`：对外数字 → 证据
- [x] `docs/plan_national.md`（本文件）
- [x] `docs/evidence/shots/` 目录 + 命名规则
- [x] `tests/test_licenses.py`：核心依赖不得含 AGPL
- [x] 0.9.85 提交、推送、CI 绿（run 241 success）

## Phase 1 · 可信内核

- [x] 正文引用句抽取 v1：数字键 `[12]`、`[12,15]`、`[3-5]`；中文“文献[12]”；作者年 `(Smith et al., 2020)`；写入报告 `citations.summary/items`（句子 + 偏移；页码/图表标题后续）
- [x] 作者年 `(Smith et al., 2020)` / 中文“文献[12]”（真实语料 22 篇抽到 543 处引注，21 篇有引注）
- [~] 上标 / 脚注 / 跨栏 / 图表标题里的引用：脚注模式已支持；1.0.10 已能抽取正文对图表的提及（图 3/表 2/Fig. 3，185 处/22 篇）；“图表标题内部的文献引用”与跨栏仍未做
- [x] `citation_context` 写入报告：句子、条目号、页码（best-effort 页文本匹配；真实 10 页论文 17/18 处命中，跨页句子会漏）；置信度沿用支持度结果
- [x] 接地校验：judge 证据原句必须可在证据中找到（忽略标点/空白），找不到则置信度 ×0.6 并写 `grounding.quote_found=false`
- [x] 多结论拆解：数字 / 方向 / 比较分开判（`claim_decompose.py`：数字/比较/因果/陈述；整句仍单标签）
- [x] 置信度校准：分桶 + ECE + 弃权曲线已完成（`docs/calibration.md`）；产品默认阈值/弃权交互待接入（`calibration.py` + `SUPPORT_ABSTAIN` 低置信标注进报告/API；不改标签）
- [x] 判错反馈：本地 JSONL 队列 + 导出（匿名、带版本）——`src/citeguard/feedback.py` + `POST /api/feedback`；报告页按钮待接
- [x] 报告三张真图：结论分布、支持度四档、GB/T 问题 Top-N（`src/citeguard/report_charts.py`；截图 `docs/evidence/shots/phase1-01-report-charts-v0.9.85.png`）
- [~] 覆盖率/准确率：22 篇语料论文覆盖 95.5%（21/22）、参考文献被引 60.1%、自洽 89.5%；人工抽 50 条准确率未做
- [x] 截图归档：`docs/evidence/shots/phase1-01-report-charts-v0.9.85.png`（其余截图随功能补）

## Phase 2 · 修复闭环

- [x] 修正建议 → 复检 diff（已解决/新增/仍存，字段级）（`diff.py` + `/api/report/{id}/diff` + 报告页“对比历史报告”面板）
- [x] 批注 PDF：问题标到原文页边，可下载/预览（`/api/report/{id}/annotated`，纯 pypdf，页边贴注）
- [x] 批量核验页：粘贴 ≤50 条 → 表格 → CSV（`/batch`：粘贴 ≤50 条 → 表格 → CSV）
- [x] 报告批处理（多任务 ZIP，含合并 `all.ris`/`all.enw`；`/api/reports/zip`）
- [x] 图表核验独立节 + 图注修改建议：规则版在图注与支持度不一致时给修改方向（E25，`tests/test_figure_advice.py`）；仅 supported 不给建议
- [x] 题录库“缺什么补什么”：候选一键入库、去重、覆盖率仪表盘
- [x] 条目 ↔ 正文双向定位（1.0.11）：报告 JSON 写 `cited_in`，抽屉显示引用句与页码；15/15 条命中，E45
- [~] 端到端：上传 → 报告 → 修正 → 复检 → 导出 → Word：自动化冒烟 14/14（含批注/导出/证据包/diff，E46）；Word 客户端仍需人工插入任务窗格
- [x] 截图：`phase-09-diff-ui-0.9.89.png`、`phase-11-annotated-pdf-0.9.91.png`、`phase-12-batch-reports-0.9.91.png`

## Phase 3 · 深度与规模

- [x] 开源模型一等模式：14B / 4bit / LoRA 在设置页可选、显示来源/许可、切换前测连通；服务离线时 409 拒绝（0.9.95，E27）。边界：验证时本地模型服务未开，只验了注册/切换/拒绝链路
- [~] 历史与题录库迁 SQLite（任务历史已索引 + 自动同步 + JSON 导出；题录库仍 JSON，待与召回一起迁）
- [x] 1000 条长文档压测：冷/热、并发、内存（离线解析/格式/报告链，`scripts/stress_1000.py`，JSON+表；不含联网核验）
- [x] 第六次预注册盲测（3 篇新 PDF，先协议后跑）
- [~] PaddleOCR 与 GROBID 对照：PaddleOCR 已评测（CER 0.1530 vs RapidOCR 0.1825，但慢 10.6×，不接入）；GROBID 因 Docker 存储只读/公共端点不可达**未完成**（E31）
- [x] 中文召回增强 v1：繁简归一（可选 OpenCC；206 条真实题名 0%→100%）；BGE-M3 保留为可选路线，未接入
- [x] 截图：`phase-16-model-registry-0.9.95.png`、`phase-24-keyboard-nav-1.0.0.png`、`phase-25-light-contrast-1.0.1.png`、`phase-33-annotated-citations-1.0.9.png`、`phase-38-a11y-pages-1.0.12.png`

## Phase 4 · 发布

- [x] v1.0.0 + CHANGELOG（1.0.0 已发布，tag `v1.0.0`）
- [x] 文档站（mkdocs 配置 + 本地构建通过）
- [~] HuggingFace 数据集 + adapter；Zenodo DOI（可选）——数据集包与 adapter 包均已备好（`dist/CiteGuard-CN_ClaimSupport-CN-300_v1.0.zip`、`dist/CiteGuard-CN_LoRA-Qwen3-1.7B_v1.0.zip`，含 MANIFEST），上传缺 token
- [x] Docker 镜像发布说明：2026-11-12 重置损坏的 containerd 数据目录后，`citeguard-cn:1.0.12` 构建成功（414 MB），容器 `/api/health` 返回 `1.0.12/offline=true`（E49，日志 `docs/evidence/logs/docker-1.0.12-health.txt`）
- [x] README / 架构 / 评测 / 许可证 / 复现命令同步（README 已更新到 1.0.12 / 611 tests；`reproduce.sh`、`docs/` 同步）
- [x] 截图：`phase4-v1.0-docs-site-1.0.0.png`（文档站首页，E33）

## 前端贯穿（桌面 Web）

- [x] 默认值聪明 / 渐进披露 / 结果先行 / 原地恢复：上传默认、抽屉原地展开、报告分标签；E36/E48 覆盖
- [x] 复制优先：报告条目/证据/规范条目均有复制按钮（`report.js`；1.0.x）
- [x] 键盘优先：`/`、`j/k`、`Enter`、`Esc`、`Ctrl+K`（E36/E48，50 项巡检全过）
- [x] SSE 阶段等待 + 失败人话：0.9.81 `/api/jobs/{id}/events`，前端 SSE 优先/轮询回退
- [x] 浅色/深色对比、焦点环、aria-live、图表表格视图：E35（20 组配色）、E48（50 项巡检）、图表 `<details>` 表格
- [x] 移动端：**暂不做**（产品定位为桌面 Web，用户明确）

## DoD

- 数字：JSON + 命令 + 样本量 + 截图
- 功能：测试或手动验收记录 + 失败态
- 图表：来源 + n + 口径 + 表格视图
- 不伪造用户反馈、不把构造集说成人审、不宣称替代人工/SOTA
- 核心分发不含 AGPL

- [x] 版面回退改用 pypdfium2（去 PyMuPDF；三篇 PDF 条数 73/92/27 一致），见 E30。
