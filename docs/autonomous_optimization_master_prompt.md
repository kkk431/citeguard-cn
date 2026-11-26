# CiteGuard-CN 全自动优化 + 比赛材料同步主提示词

> 用途：交给一个新的执行代理，从 v1.7.36 基线开始，自主完成产品优化，并在每次改动后自动判断、更新受影响的比赛材料。允许开子代理。除破坏性操作、外部付费、凭据外，不要停下来问“要不要做”。

---

你是 CiteGuard-CN 的全自动优化总负责人。工作区：`D:\ai+ky\citeguard`。

你的目标不是只改代码，而是同时完成两条闭环：

1. **产品优化闭环**：在不更换基础模型、不购买数据、不新增外部资源、不伪造效果的前提下，把产品做到覆盖更全、任务不中断、结论可复核、操作不迷路、界面有冲击。
2. **材料同步闭环**：每次产品能力、数字、版本、依赖、限制发生变化，自动判断哪些比赛材料需要更新，并完成更新、重建、校验、打包、推送。

## 0. 当前基线

- 版本：v1.7.36（以 `web/app.py` 为准）。
- 测试：`pytest tests -q` 约 1055 passed；`scripts/verify_artifacts.py` 137/137；`scripts/audit_frontend.py` 58/58；`scripts/e2e_smoke.py` 14/14。
- 现有材料：技术报告 15 页、资源清单 2 页、佐证材料 18 页、答辩 PPT、4:27 演示视频、提交目录 `dist/submission/`、提交 zip、GitHub 仓库与 HF 成果。
- 已知材料问题：提交说明写“佐证 17 页”实际 18 页；资源清单目前独立成目录，报告附录 A 写“随报告提交的 PDF”；PPT/视频存在版本/页数差异（用户明确不改内容）；远程旧部署目录不存在，无公网在线演示。
- 已知产品现状：核心链路可用；Live/CiteMap/引用链有条件；LongCite/AlignScore 未接入；这是真实边界，不许包装成“通用准确率”。

## 1. 硬约束

- 不训练/更换基础大模型，不买知网/万方/商业引文库，不承诺出版商全支持。
- 不做移动端、不做全领域 CiteMap、不做全网 Live。
- 不改 PPT/视频内容；只允许替换为已存在的最终文件、更新材料里的版本/页数引用；拿不到最终文件就记录风险，不重做。
- 不伪造数据、不伪造人审、不伪造截图、不伪造用户反馈、不伪造公网链接。
- 不修改测试来“通过”；不把热缓存/构造集/机器候选包装成真实效果。
- 比赛材料不得出现学校名称、校徽、指导教师、内网 IP、真实 API key/密码。

## 2. 自主执行原则

1. 先读：`README.md`、`CHANGELOG.md`、`docs/optimization_master_prompt.md`、`docs/plan_national.md`、`docs/evidence_index.md`、`docs/deployment.md`、当前测试与页面。
2. 先跑基线：pytest、verify_artifacts、audit_frontend、e2e_smoke；记录版本与 worktree 状态。
3. 建 `docs/optimization/plan.md`：把 A–H 清单拆成可验收条目、负责人、写作用域、证据路径。
4. 一个改动一个验证：每项必须有测试 + 真实截图/数据 + 复现命令；没有验证不算完成。
5. 每完成一项，立即执行“材料影响判断”（见 §4），不要等到最后一次性补材料。
6. 每波独立 commit + push，确认 CI；不要一次提交几十个文件。
7. 遇到外部阻塞：写清“未完成 + 原因 + 解锁条件”，继续下一项，不停摆。
8. 不修改用户已有未跟踪文件；不删除用户资料；不确定时先备份。

## 3. 产品优化清单

### A. 覆盖与数据
A1 中文题录库导入向导（CNKI/万方/RIS/EndNote，字段映射/去重/失败行提示）
A2 候选补录 + 人工确认（缺 DOI/卷期页码，不自动写入不确定字段）
A3 题录库仪表盘（来源/年份/期刊/重复/覆盖率/标签）
A4 判错反馈队列（不自动训练）

### B. 稳定与性能
B1 长文档/批量异步队列（SSE、断点续跑、单条重试、关页不丢）
B2 结果缓存与只补失败
B3 模型不可用降级（不出现假结论；重试/换模型/继续；恢复后补缺口）
B4 服务健康/熔断/预热（本地与云端切换不阻塞）

### C. 判定可信
C1 图表确定性预检（先数字/单位/趋势规则，再视觉模型；多面板裁切）
C2 低置信度复核队列
C3 多源冲突展示
C4 状态语义统一（Exact/Minor/Unverified/Unknown/Major；Unknown≠未收录）

### D. 修复与复核
D1 可控修复（逐字段接受/拒绝、diff、撤销不受 30 分钟限制、导出保留修改记录）
D2 分诊批量操作
D3 复检 diff 可视化
D4 导出与批注增强

### E. Live 与 CiteMap
E1 Live 站点支持矩阵/三步引导/人话结果/内置示例/失败三动作
E2 CiteMap 三步引导/固定图例/仅全文筛选/焦点模式/机器候选标识/空态
E3 CiteMap 半自动扩展（机器抽取 + 人工确认）
E4 demo 模式（`/live?demo=1`、`/citemap?demo=1`）

### F. 解析与格式
F1 真实版式继续收（双栏/表格/脚注/扫描；字段级修复）
F2 GB/T 规则补全（学位论文/标准/专利/电子资源）
F3 中文归一增强（繁简/全半角/标点/期刊别名/DOI/arXiv）

### G. 前端与舒适度
G1 入口与任务路径（三模式、最近任务、深链接、刷新不丢）
G2 报告阅读器（小地图、严重度筛选、j/k、页码/条目跳转、页内证据缩放）
G3 图表/地图交互（hover/图例/缩放；CiteMap 焦点模式；105 节点不卡）
G4 微交互（过渡/骨架/抽屉/toast/命令面板；支持减少动效）
G5 状态与错误（loading/empty/unsupported/error；不露 HTTP；给下一步）
G6 可访问性/分辨率（深浅对比、焦点、aria、1280/1440/1920）

### H. 工程质量
H1 测试与 E2E
H2 可观测性/错误码/任务日志
H3 安全默认值（公网才加 token/限流/SSRF）
H4 许可与依赖（核心不引入 AGPL）

## 4. 材料影响判断（每项完成必做）

| 变化 | 必须更新 |
|---|---|
| 新功能/行为变化 | 技术报告相应章节、佐证材料、提交说明、README、平台简介（若价值主张变） |
| 新数字/指标/测试数 | 技术报告、佐证材料、证据矩阵、README/CHANGELOG、平台简介（若影响卖点） |
| 新依赖/模型/数据/API | 资源清单、THIRD_PARTY_NOTICES、报告附录、许可文档、SBOM |
| 版本号 | 报告封面/页脚、资源清单、佐证、SBOM、README/CHANGELOG、Docker 文档、提交目录、GitHub tag/release |
| 新截图/证据 | `docs/evidence/shots/`、`docs/evidence_index.md`、佐证 PDF、提交包 |
| 匿名/安全变化 | 全材料扫描校名/校徽/指导教师/内网 IP/key/密码 |
| 无影响 | 在材料审计表写“无材料影响”，不要硬改 |

材料文件与工具：
- 技术报告：`report/build_report.py` + Word/LibreOffice，目标 PDF ≤15 页正文、≤10MB。
- 资源清单：作为技术报告附件。默认最严口径：并入报告 PDF 附件页（正文仍 15 页，总页数说明写清）；若平台只允许单独附件，则放 `01_技术报告/附件A_资源清单.pdf`。全材料口径统一。
- 佐证材料：`scripts/build_evidence_pdf.py`；页数、数字、版本必须与报告一致。
- 提交目录：`dist/submission/`，只放必要文件；不放 DOCX/SRT/2x/素材包。
- 平台字段：`作品名称.txt`、`作品简介.txt`、`提交说明.md`。
- GitHub：README、THIRD_PARTY_NOTICES、release/tag、HF 链接。
- 提交 zip：重建后记录文件数、大小、SHA-256。

## 5. 数据与截图留档

- `data/experiments/opt_<item>_<date>.json`：命令、样本量、日期、commit、原始指标。
- `data/experiments/opt_tests_<date>.txt`：pytest/verify/frontend/e2e 摘要。
- `docs/evidence/shots/opt-<wave>-<item>-<version>-<viewport>.png`：真实页面，1920 为主，布局项补 1280/1440，视觉项补深浅主题。
- `docs/optimization/`：设计、边界、复现命令。
- 材料审计：`data/experiments/material_audit_<date>.json` + `docs/materials_audit.md`。
- 全部登记 `docs/evidence_index.md`；旧证据不覆盖，加版本/日期后缀。

## 6. 子代理

按文件写作用域拆，禁止两个代理改同一文件：

- `backend-data`：`src/citeguard/jobs.py`、`library_db.py`、`local_library.py`、`support.py`。
- `frontend-shell`：`web/templates/base.html`、`web/static/css/refresh.css`、`web/static/js/app.js`。
- `report-ux`：`web/templates/report.html`、`web/static/js/report.js`、报告 CSS。
- `live-map`：`live.html`、`citemap.html`、对应 JS/CSS。
- `materials`：`report/`、`scripts/build_evidence_pdf.py`、`dist/submission/`、材料文档；不改产品代码。
- `verify`：测试、证据登记、视觉回归；不改产品代码。
- 主代理：`web/app.py`、跨模块契约、集成、最终验收、提交/CI。

子代理必须拿到：任务、写作用域、验收标准、证据路径；交付必须带测试/截图。

## 7. 执行顺序

**第一波（P0）**：A1 → B1 → B3 → G1 → G5；随后 B2、A2、A3。
**第二波（P1）**：C1 → D1 → E1 → E2 → G2 → G3。
**第三波（P2）**：F1 → E3 → D3/D4 → G4 → H1/H2。
**贯穿**：G6、H3、H4 每波结束检查；每波结束更新材料。

## 8. 验收底线

产品：
- 100 条题录 2 分钟内入库；
- 关页任务继续，失败可单条重跑；
- 模型挂掉不出现假结论；
- 报告 3 次点击内找到证据；
- Live 点之前知道支不支持；
- CiteMap 能只看全文证据、能聚焦一条断言；
- 全站无 HTTP 状态码直出；
- 1280/1440/1920 无横向溢出；
- 1055+ tests、前端审计、e2e 不破。

材料：
- 作品名称≤20 字、简介≤300 字；
- 技术报告正文≤15 页、≤10MB、无校名校徽/指导教师；
- 资源清单作为报告附件，口径一致；
- 佐证页数/数字/版本与报告一致；
- 提交目录无旧版本/重复/多余文件；
- GitHub/HF 链接 200，release latest 指向当前版本；
- 无公网演示时明确写本地/Docker，不编造链接；
- 最终 zip 有大小/SHA-256。

## 9. 最终交付

- 产品：commit 已 push、CI 绿；`docs/optimization_report.md` 写每项改动、验收数字、截图路径、残留风险。
- 材料：`docs/materials_audit.md` 写“要求→材料→状态→修复→hash”；最终提交目录与 zip；平台字段文本；GitHub release/tag。
- 明确已知例外：PPT/视频不改、视频无开放成果镜头、无公网演示、资源型项未做。
- 不写“已完成”除非验收命令通过；不写“效果提升”除非有真实对照。

现在开始。先跑基线、建 `docs/optimization/plan.md` 和 `docs/materials_audit.md` 初稿，然后从第一波开始；每完成一项立即判断材料影响，不要停。
