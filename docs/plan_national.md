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
- [ ] 作者年 `(Smith et al., 2020)` / 中文“文献[12]”
- [ ] 上标 / 脚注 / 跨栏 / 图表标题里的引用
- [ ] `citation_context` 写入报告（句子、页码、条目号、置信度）
- [x] 接地校验：judge 证据原句必须可在证据中找到（忽略标点/空白），找不到则置信度 ×0.6 并写 `grounding.quote_found=false`
- [x] 多结论拆解：数字 / 方向 / 比较分开判（`claim_decompose.py`：数字/比较/因果/陈述；整句仍单标签）
- [x] 置信度校准：分桶 + ECE + 弃权曲线已完成（`docs/calibration.md`）；产品默认阈值/弃权交互待接入（`calibration.py` + `SUPPORT_ABSTAIN` 低置信标注进报告/API；不改标签）
- [x] 判错反馈：本地 JSONL 队列 + 导出（匿名、带版本）——`src/citeguard/feedback.py` + `POST /api/feedback`；报告页按钮待接
- [x] 报告三张真图：结论分布、支持度四档、GB/T 问题 Top-N（`src/citeguard/report_charts.py`；截图 `docs/evidence/shots/phase1-01-report-charts-v0.9.85.png`）
- [ ] 覆盖率/准确率：30 篇语料抽取覆盖 ≥70%，人工抽 50 条准确 ≥85%
- [x] 截图归档：`docs/evidence/shots/phase1-01-report-charts-v0.9.85.png`（其余截图随功能补）

## Phase 2 · 修复闭环

- [x] 修正建议 → 复检 diff（已解决/新增/仍存，字段级）（`diff.py` + `/api/report/{id}/diff` + 报告页“对比历史报告”面板）
- [x] 批注 PDF：问题标到原文页边，可下载/预览（`/api/report/{id}/annotated`，纯 pypdf，页边贴注）
- [x] 批量核验页：粘贴 ≤50 条 → 表格 → CSV（`/batch`：粘贴 ≤50 条 → 表格 → CSV）
- [x] 报告批处理（多任务 ZIP，含合并 `all.ris`/`all.enw`；`/api/reports/zip`）
- [ ] 图表核验独立节 + 图注修改建议
- [ ] 题录库“缺什么补什么”：候选一键入库、去重、覆盖率仪表盘
- [ ] 端到端：上传 → 报告 → 修正 → 复检 → 导出 → Word
- [ ] 截图：`phase2-*.png`

## Phase 3 · 深度与规模

- [~] 开源模型一等模式：14B / 4bit / LoRA 在 UI 可选并显示来源（注册表 + 设置页 + 报告 run_config.judge 已做；切换前测连通，服务不在线时拒绝切换）
- [~] 历史与题录库迁 SQLite（任务历史已索引 + 自动同步 + JSON 导出；题录库仍 JSON，待与召回一起迁）
- [x] 1000 条长文档压测：冷/热、并发、内存（离线解析/格式/报告链，`scripts/stress_1000.py`，JSON+表；不含联网核验）
- [x] 第六次预注册盲测（3 篇新 PDF，先协议后跑）
- [~] PaddleOCR 与 GROBID 对照：PaddleOCR 已评测（CER 0.1530 vs RapidOCR 0.1825，但慢 10.6×，不接入）；GROBID 因 Docker 存储只读/公共端点不可达**未完成**（E31）
- [x] 中文召回增强 v1：繁简归一（可选 OpenCC；206 条真实题名 0%→100%）；BGE-M3 保留为可选路线，未接入
- [ ] 截图：`phase3-*.png`

## Phase 4 · 发布

- [x] v1.0.0 + CHANGELOG（1.0.0 已发布，tag `v1.0.0`）
- [x] 文档站（mkdocs 配置 + 本地构建通过）
- [~] HuggingFace 数据集 + adapter；Zenodo DOI（可选）——数据集包已备好（`dist/CiteGuard-CN_ClaimSupport-CN-300_v1.0.zip`），上传缺 token
- [~] Docker 镜像发布说明——镜像 0.9.85 曾验证；1.0.0 构建被本机 containerd 元数据损坏阻塞（磁盘写满后 `blob ... input/output error`），需重建 Docker 数据目录
- [ ] README / 架构 / 评测 / 许可证 / 复现命令同步
- [~] 截图：`phase4-release-checklist.png`（README/证据索引，见 E32）

## 前端贯穿（桌面 Web）

- [ ] 默认值聪明 / 渐进披露 / 结果先行 / 原地恢复
- [ ] 复制优先（引用句、证据原句、规范条目、理由）
- [ ] 键盘优先：`/`、`j/k`、`Enter`、`Esc`、`Ctrl+K`
- [ ] SSE 阶段等待 + 失败人话
- [ ] 浅色/深色对比、焦点环、aria-live、图表表格视图
- [ ] 移动端：**暂不做**（产品定位为桌面 Web）

## DoD

- 数字：JSON + 命令 + 样本量 + 截图
- 功能：测试或手动验收记录 + 失败态
- 图表：来源 + n + 口径 + 表格视图
- 不伪造用户反馈、不把构造集说成人审、不宣称替代人工/SOTA
- 核心分发不含 AGPL

- [x] 版面回退改用 pypdfium2（去 PyMuPDF；三篇 PDF 条数 73/92/27 一致），见 E30。
