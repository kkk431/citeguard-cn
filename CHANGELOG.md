## [1.7.26] - 2026-11-15

- 新增 CiteMap 证据门禁实验：宽松门禁精确率 63.6%/召回 87.5%，要求完整支持整条复合断言时 0/31；据此放弃“单句摘要支持复合断言”的展示方式。
- 产品语义修正：论文摘要结论句改为「论文自述结论」，不再标成对人工断言的证据；原子证据单独计数；统计拆分为人工示例、原子证据、论文自述、机器候选。
- 新增 `docs/citemap_gate.md` 记录门禁口径、0/31 结论与产品规则；`scripts/gate_citemap_evidence.py` 可复现 105 格门禁。

## [1.7.25] - 2026-11-15

- CiteMap 支持**动态生成**：输入研究主题从 OpenAlex 检索 5–15 篇有摘要/DOI 的论文，或粘贴 5–20 个 DOI；
  生成 `dyn_<hash>` 主题并写入 `data/evidence_map/dynamic/`，机器卡片统一标「机器候选 · 仅摘要 · 未人审」。
- 固定示例的 30 篇论文补**独立机器层**（每主题 10 条、共 20 条），人工 10 条/105 格结果不改；
  机器层存 `extractions_machine/`，仅 API 合并展示，避免污染人审数据。
- 前端新增生成表单、DOI 输入与机器层统计；修复动态主题空断言分组、主题切换不重置滚动。
- 新增 7 个测试（builder、DOI、machine layer、页面文案）；全测 925 项。

## [1.7.24] - 2026-11-15

- CiteMap 增加**原子断言层**：把 8 条复合主题断言拆成 21 条可单句核对的原子命题，逐条抽取+独立复核，共 9 条原子证据、覆盖 7/30 篇；产品优先展示原子层，标签明确“原子证据·仅摘要·未人审”，母断言不再被部分支持冒充整体。
- 105 格三人人工核对结果落库：Fleiss κ 0.6587；v1 证据格多数票正确 8/31（25.8%），无证据格 69/70；strict 层 3/3、原子层 5/7。结果写入 `docs/citemap_audit_result.md`，不隐藏 2 个争议格。
- 新增 `tests/test_citemap_atomic.py`；CiteMap API 的 `auto_meta.layer` 优先 `extractions_atomic`，前端按“有证据分组优先”排序。

## [1.7.23] - 2026-11-15

- 中文查询的英文关键词扩展改为**默认关闭**（`CITEGUARD_LIVE_TRANSLATE=0`）：它每句多一次模型调用、实测只把无页面 hit@3 从 0 拉到 2/30，默认路径不应为边缘场景付出秒级延迟。
- 需要跨语言实验时显式开启；`fast` 只判 top-1 的行为不变。新增 opt-in 回归测试。

## [1.7.22] - 2026-11-15

- Live `fast` 判定收紧：只判排序第一的候选；若 top-1 没有可引用摘要，直接返回「证据不足」，不再用第 2、3 条有摘要候选凑判定。
- 中文查询检索从整句翻译改为 3–8 个英文检索关键词（`support._TRANSLATE_PROMPT`），新增无页面上下文的 30 条真实中文引用句诊断：hit@3 0/30 → 2/30（`live_eval_crosslingual_nopage.json`），只作诊断，不宣称跨语言检索已解决。
- 新增 `scripts/eval_live_crosslingual_nopage.py`、fast top-1 回归测试；`docs/live.md`/`docs/live_eval.md` 记录新口径与边界。

## [1.7.21] - 2026-11-15

- 100 条三人独立盲标完成：Fleiss κ 0.981，2 条 2:1 分歧、无平票；产品对多数票 99/100，macro-F1 0.988，Cohen κ 0.986（Wilson 95% CI 94.55%–99.82%）。
- 唯一错误 HS032（人工 contradict，产品 partial）；产品预测取自既有 release300 运行，未在这 100 条上调参。
- 新增 `docs/human_audit_result.md`、`scripts/score_human_audit_100.py`、`tests/test_human_audit_result.py`、第 15 张证据图 `15-human-audit.png`；报告、README、证据矩阵与证据索引同步。
- 边界：100 条来自构造集分层抽样，不是随机样本；2 条分歧未仲裁；不能外推所有中文论文，也不能替代同行评审。

## [1.7.20] - 2026-11-15

- 新增真实语料问题普遍性分析 `scripts/analyze_corpus_prevalence.py`：按原始文件名取每篇 PDF 最新报告，统计 22 篇 / 524 条引文的字段缺失、GB/T 规则命中、中文未解决与正文未引用；原始 JSON `data/experiments/corpus_prevalence.json`。
- 新增 `docs/problem_evidence.md` 与第 14 张证据图 `14-prevalence.png`：71.2% 缺 DOI、33.8% 缺页码、39.9% 未被正文引用、217 条中文引文未解决 197 条；明确是描述性统计，不是随机抽样/人工审计。
- 技术报告 1.1 节补该统计；README/证据索引/E95 同步。`docs/evidence_charts.md` 更新为 14 张。
- 908 tests。

## [1.7.19] - 2026-11-15

- 新增 MCP stdio 服务 `integration/mcp/citeguard_mcp.py`（零依赖、JSON-RPC 2.0、3 个工具），17 项协议/透传测试；文档写明客户端实际加载未验证。
- 新增 `docs/scenarios.md`：四类真实任务（论文初稿 / 审稿单句 / 领域综述 / 格式修复）的输入、真实数字、截图与复现命令，并映射评分表；明确不是用户调研。
- 新增机制消融矩阵 `data/experiments/ablation_matrix.json` + `docs/research/ablation_matrix.md`（12 行同集对照、6 项评分缺口），第 13 张证据图；修正 Live 评测图的数据集口径。
- 新增 `CITATION.cff`、`CONTRIBUTING.md`；README 加三条产品线与 MCP 接入入口。
- 908 tests。

## [1.7.18] - 2026-11-15

- `/live` 页面在填写「页面标题 / URL」后 900 ms 自动调用 `/api/live/prewarm`，切换输入会取消上一次请求；状态行显示「页面已预热 · 参考文献 N 条」，失败静默为「预热失败（不影响核验）」。扩展仍保持打开侧栏自动预热。
- 新增 `docs/ai_usage.md`（开发期/运行期 AI 工具、模型清单、数据边界、标注边界、可能出错的地方），并在 README、mkdocs 导航和 `tests/test_ai_usage.py` 固化；这是竞赛要求的 AI 使用说明，不把 AI 输出冒充人工结论。
- 冻结 held-out（30 句/5 页）复跑记录：hit@1 0.90 / hit@3 1.00，fast 冷启动 P50 10.12 s、P95 19.63 s，15 句有判定；与 1.7.17 的 10.52 s/15 句同口径，差别在判官波动，不宣称提速。
- 891 tests。

## [1.7.17] - 2026-11-15

- Live 两段返回：`POST /api/live/check` 新增 `phase=retrieve|judge|full`；页面与扩展先显示候选，再显示四档，避免整段空白等待。冷启动实测 retrieve 2.27 s、judge 2.90 s。
- 扩展 v2 打开侧栏时自动调用 `/api/live/prewarm`（12 s 上限、失败静默）。
- 中文 claim 追加一次英文 OpenAlex 检索（判官模型翻译，失败静默）；翻译只用于找候选，不当证据。
- arXiv DOI 回填摘要；OpenAlex 摘要与引文标题相似度 <0.7 时拒绝，修掉张冠李戴。
- `docs/live.md`、`docs/api.md`、README 同步两段契约与边界；889 tests。

## [1.7.16] - 2026-11-15

### Added
- `POST /api/live/prewarm`：在用户选中句子前预取 arXiv HTML 参考文献，减少首句冷启动等待；只做缓存，不判定。
- Live fast 档跳过 Stage-2 覆盖审计，并使用独立的判官缓存键；判官调用加 8 s 上限，超时明确降级为本地规则。
- 页面标记参考文献的摘要补全改为并行（最多 4 路），同一句带多个 `[n]` 时不再串行等待。

### Fixed
- 更正 Live 评测数据集口径：1.7.15 中标注为 held-out 的 `hit@3 0.9333 / P50 14.81 s` 实际来自公开页集（`pub-*`），不是冻结 held-out；冻结 held-out 使用 `hld-*` 数据重新跑。
- 冻结 held-out（30 句/5 页、同一判官）：页面热缓存 + fast `hit@1 0.90 / hit@3 1.00`、P50 **3.13 s**、P95 4.50 s；full 热缓存 P50 **9.68 s**；冷启动 fast P50 10.52 s。命中在三种运行中一致，判官只改变四档标签。
- README / `docs/live_eval.md` §5.5–5.6 / `docs/live.md` 同步修正；old 公开页判官结果保留但明确标注数据集。

## [1.7.15] - 2026-11-15

### Added
- Live 在线接口新增 `mode=fast|full`（默认 `fast`）：fast 最多只判 1 条有摘要候选，
  full 判前 3 条；返回 `judge_mode`/`judge_calls`。公开页集（pub-*）30 句冷缓存复测：
  fast hit@3 0.9333 / P50 11.46 s，full hit@3 0.9333 / P50 14.81 s（该行不是 held-out；1.7.16 已更正）；P95 受网络长尾影响，
  不宣称“更快更稳”（`docs/live_eval.md` §5.6、`data/live_eval/live_eval_holdout_fast_cold.json`）。
- `docs/sbom.json`（CycloneDX 1.5）与 `scripts/make_sbom.py --check`，列出 10 个核心依赖
  的版本/许可证；`tests/test_sbom.py` 防止版本漂移。
- `CITEGUARD_CACHE_DIR` 可指定缓存目录，用于冷/热缓存对照评测。

### Changed
- 881 项 pytest；README/Live API 文档/导航同步。

## [1.7.14] - 2026-11-14

### Evidence
- 新增 `docs/evidence_charts.md`：12 张由实验 JSON 生成的深色证据图（脚本 `scripts/make_evidence_charts.py`）。
- 新增 `docs/evidence_product.md`：19 张真实运行实例的产品截图（脚本 `scripts/capture_final_shots.py`，job `96511af51c97`）。
- 修复证据抽屉深色主题对比度与长字段换行，截图可读；`evidence_index` 增 E88/E89。

### Changed
- 测试 875 项；文档站导航增加实验证据图与产品截图。

## [1.7.13] - 2026-11-14

- CiteMap 详情改为**按断言分组**：每条断言先显示正文/方向/人工与机器证据数量，再渲染全宽证据卡；不再把证据塞进两列窄卡，也不留空列。机器证据是同一组里的虚线条目，人工示例在前。
- 详情高度从 560 提升到 **680–920px**（视口自适应），详情内部滚动、标题吸顶；头部压缩为标题 + 作者/年份/期刊 + 可展开的「论文信息与链接」，减少正文被头部挤占。
- 无人证据的断言分组显示「没有人工或机器证据，也没有抽到核对格」；证据缺口按全部分组断言列出。
- 60 格核对按钮仍挂在抽样卡上；**未点击真人核对，状态保持 0/60**。
- 版本 1.7.13；`pytest` 869 passed；证据 E85、截图 `docs/evidence/shots/phase-55-citemap-layout-1.7.13.png`。
- Live 判定模型补齐两条可选路径：云端 `deepseek-chat` 与本地 Qwen3-14B（4-bit，按需启动）；`/live` 对真实 STIC 72.6% 引用句返回支持 95% 与逐字证据。配判官复跑同一 30 条 held-out：hit@1 0.6667 / hit@3 0.9333、19/30 有判定、P50 14.8 s；仍无人审，不能当 stance 准确率。另修复切换示例时残留旧 `page_url` 的问题，页面命名从「Live 试用」改为「Live 单句核验」。

## [1.7.12] - 2026-11-14

- CiteMap 桌面布局改为固定高度两栏：`.ctm-layout` 560–800px（视口自适应），左侧论文清单与右侧详情**各自滚动**，详情标题吸顶，证据/机器抽取区在宽屏两列排布；切换论文时详情回到顶部。解决“右侧无限拉长、左右不均、要滚到底”的问题。
- 人工示例与机器证据去重：同一断言下，把归一化后逐字包含（≥40 字符）的机器引用合并到人工卡片，机器区只列未重复证据；主题统计新增“已合并重合”。AI 教育合并 7 条、医学影像 1 条，机器证据从 25 条去重为 18 条；被合并的 60 格抽样仍挂在人工卡片上，核对入口不丢失。
- Docker：`citeguard-cn:1.7.12` 构建成功，容器 `-p 18084:8000 -e CITEGUARD_OFFLINE=1` health `{"ok":true,"version":"1.7.12","offline":true}`（日志 `docs/evidence/logs/docker-1.7.12-health.txt`）。
- 版本 1.7.12；`pytest` 869 passed；证据 E85、E86、截图 `docs/evidence/shots/phase-55-citemap-layout-1.7.12.png`。

## [1.7.11] - 2026-11-14

- CiteMap 机器抽取（摘要级）：两主题共 **42 条机器证据、覆盖 25/30 篇**，逐字引用不合格 0；对 10 条人工示例覆盖 6 条、这 6 条 stance 一致 6/6（只在这 10 对示例上计算，不是全量准确率）。新增 60 格人工核对包与产品内「核对模式」，机器结果单独标注 `auto:abstract-only` / `verified=false`，不冒充人工。
- CiteGuard Live 页面引用增强：识别正文 `[n]/[3,5]/[3–5]` 并映射 arXiv HTML 页内参考文献（仅 arxiv.org / ar5iv，5s/2MB/磁盘缓存，失败静默回退）；page-reference 候选按 DOI/题名补 OpenAlex/Crossref 摘要，无摘要不生成证据句；同页解析结果进程缓存 TTL 300s。
- 冻结 held-out 集（5 篇新 arXiv HTML / 30 句英文）：补摘要后 **hit@1 27/30、hit@3 30/30**，P50 2.98 s、P95 16.09 s，有逐字证据 11/30；**判定模型未配置、四档为规则降级**，不能宣称 stance 准确率；公开页集 21/30、跨语言集 0/30，三套不混算。
- 浏览器扩展 v2 真实 Chromium 验收：service worker/manifest 正常，3 个公开页选区→消息→`POST /api/live/check` 200，错误地址有中文提示；7 张真实截图，未自动化的原生右键/side panel 相关操作在文档中列为手工步骤。
- 版本 1.7.11；869 项 pytest；`docs/evidence_index.md` 增 E83（CiteMap 机器抽取/核对）与 E84（Live held-out/扩展验收）；证据矩阵增 2 行、待补仍为 100 条人审与 60 格核对。

## [1.7.10] - 2026-11-14

- 新增 `docs/baselines.md`：SciFact 300 条（本产品 0.8224 / RefChecker 官方两阶段 0.7646）、ChartCheck 400 条（三分类 0.7628、二分类 0.7903）、BGE-M3 recall@1 0.8667、T2Retrieval BM25 R@3 0.79；每条标 n、口径、不可比之处。
- 证据矩阵增至 32 行；无产品代码行为变化；858 passed。

## [1.7.9] - 2026-11-14

- CiteGuard Live 页面候选改为**标题优先**排序（`_page_candidate_score`，0.85 标题覆盖 + 0.15 数字），公开页 30 句 hit@3 **0.60 → 0.70**、hit@1 0.4667 → 0.5667；9 条仍未进 top-3（4 条排 4–5、5 条更后）。
- 该排序规则在同一公开页集上选定，尚未用新集确认；跨语言集 0/30 不变，两套数据不混算；858 passed。

## [1.7.8] - 2026-11-14

- CiteGuard Live 公开页评测：5 篇 arXiv HTML、30 条英文正文句、每页 6 条；hit@3 **0.60**（18/30）、hit@1 0.4667、P50 16.7 ms、P95 3.53 s；句子与页面/参考文献真实对应，正确 DOI 在候选池内，4 条排 4–5、8 条被 top-5 截断。
- 中文跨语言 30 句集保留为基线（hit@3 0/30）并明确与公开页集任务不同、禁止混算；证据矩阵增至 27 行、待补 2 项；857 passed；Docker 镜像 `citeguard-cn:1.7.8` 容器健康检查通过。

## [1.7.7] - 2026-11-14

- CiteGuard Live：新增 `POST /api/live/check`、产品内 `/live` 试用页与 `extension/v2/` MV3 侧边栏；划一句 → 识别当前论文 → 优先从 OpenAlex `referenced_works` 取候选 → 四档 + 逐字证据句；普通网页回退 OpenAlex/Crossref 检索，只读摘要，不读全文。
- 30 句真实中文引用句跨语言评测 hit@3=0/30（P50 5.47 s），诊断与边界见 `docs/live_eval.md`：中文句子检索到中文文献，英文被引文献不在候选；英文 source_title 抽查 3/3 top1，不把该结果说成检索天花板。
- 851 passed；新增 Live 页面/接口/扩展测试；证据 E80。

## [1.7.6] - 2026-11-14

- 新增支持度模型对比矩阵（`scripts/build_support_matrix.py`、`docs/model_matrix.md`）：8 行同口径指标、逐条预测的 bootstrap 95% CI、错误清单与「不能这么说」边界。
- 完成 Qwen3-4B LoRA（600 train / 20 dev / 60 test），test 1.0000 为构造模板饱和；模型卡 `docs/model_card_support_lora_4b.md`。
- 811 passed；证据矩阵扩到 25 行，待补 3 项。

## [1.7.5] - 2026-11-14

- 题录库支持标签（最多 8 个、24 字符）与重复合并：DOI / 题名+年份分组，人工确认后合并；JSON 主存储、SQLite sidecar schema 2 向后兼容迁移。
- 新增 `GET /api/library/duplicates`、`POST /api/library/duplicates/merge`、`POST /api/library/{index}/tags`。
- 新增 `docs/evidence_matrix.md`（脚本生成，24 条对外数字 → 证据 JSON/复现/样本/口径）与 `tests/test_evidence_matrix.py`。
- 808 passed；文档站新增「证据矩阵」「题录库标签」。

# Changelog

All notable changes to CiteGuard-CN. Earlier pre-1.0 history is condensed.

## [1.7.4] - 2026-11-14

### Added
- Repair loop on the report page: “一键修复全部” and per-entry “修复此条” open a preview with `del`/`ins` diffs and fix labels (document type, year placement, trailing period, DOI format). Applying writes `report.fixed.json` + `repair.json`; undo is available for 30 minutes and removes both files, restoring the original entries.
- `GET/POST /api/report/{id}/repair/{state,preview,apply,undo}` with atomic writes, fingerprint/patch-id checks, and structured errors (`invalid_index`, `stale_patch`, `undo_expired`).
- Evidence: `docs/repair_loop.md`, two screenshots in `docs/evidence/shots/phase-48-*.png`.
- CiteMap evidence map (`/citemap`, `/api/citemap/topics`, `/api/citemap/{topic}`): two topics x 15 open papers, 10 human example extractions with quote/locator/stance/method/sample/gap; schema and corpus validated by `src/citeguard/evidence_map.py` and 104 tests.

### Notes
- Repair only reformats already-parsed fields; it never fabricates missing fields or rewrites the paper body. `report.json` stays read-only.

## [1.7.3] - 2026-11-13

### Added
- Shared long-list pager (`web/static/js/pager.js`): page numbers, previous/next, 10/20/50 page sizes, URL state (`?page=&size=`), and “第 a–b 条 / 共 N 条”. Applied to history, library, cohort table and batch results.
- Report “检查明细” now opens as a right-side drawer with six tabs (source health, figure checks, support, in-text citations, charts, diff) instead of an inline expanding block; Esc/backdrop close, focus returns to the trigger, and charts resize when a tab becomes visible.
- Evidence: `docs/ui_patterns.md`, `scripts/capture_ux_1_7_3.py`, four screenshots in `docs/evidence/shots/phase-47-*.png`.

### Fixed
- Pagination in `history.html` now initializes on `DOMContentLoaded`, because its inline script runs before the shared pager loads.
- The report drawer no longer mounts ECharts at zero width while hidden; `CGCharts.resize()` runs when a tab is activated.

## [1.7.1] - 2026-11-13

### Added
- Bundled Apache ECharts 5.5.1 (`web/static/vendor/echarts.min.js`, Apache-2.0) and a shared chart layer (`web/static/js/charts.js`) with dark/light tokens, empty states, resize handling and no CDN dependency.
- Cohort page charts: grade distribution donut, five-dimension radar, per-paper health ranking (real aggregate JSON).
- History trend: `GET /api/history/trend?days=30` plus a daily average-health line and Major-count bars.
- Library charts: publication-year distribution and top venues, computed from the local library.
- Evaluation charts: CiteBench-CN v2 eight-class detection rates, 2×2 confusion matrix, retraction donut (500 cases, Unknown counted as missed).
- Batch page: verdict distribution donut after a run.
- Report page: conclusion/support/format distributions now render as ECharts bars, with the previous CSS bars kept as a fallback and the table view retained.

### Notes
- Charts show sample size or source; no synthetic series are drawn. The history chart only plots days that actually have reports.
- Batch charts need a configured judge; without one the page still explains why it cannot judge.

## [1.6.0] - 2026-11-13

### Changed
- The rail now has five task areas instead of a dozen flat entries:
  workspace, reports, library, tools, and about. Pages that serve the same job
  are grouped behind one entry, with a tab strip inside the group
  (`论文体检 / 快速判定 / 批量判定`, `全部报告 / 批量聚合`,
  `图表核验 / 多篇对比 / 文献发现`, `关于 / 评测 / 模型`).
- Functional pages lost their English kickers, marketing-sized headings and
  four-stat strips; the task and the form come first. The local library header
  keeps only the numbers that matter (entries, abstracts, source formats).
- The command palette lists the five areas plus their direct sub-pages, and
  every workspace action now points at `/workspace` rather than the landing
  page.
- Reports now default to one row per file (the newest analysis), with a
  `· N 次` count; `/history?all=1` still shows every run.
- The report page folds its diagnostic detail (source health, figure checks,
  support, citations, trends) into a collapsed "检查明细" panel, and the quick
  support page explains the four verdicts before the first submission.

## [1.5.1] - 2026-11-13

### Changed
- The workspace at `/workspace` is now purely functional: the marketing hero,
  product-number strip, tool cross-links and three-step explainer were removed.
  It opens with a compact title, the upload form, and a side column for the
  checks being run, recent reports and the local library.
- Recent reports on the workspace are filtered by `has_report`, so queued or
  failed jobs no longer appear as links to a missing report.

## [1.5.0] - 2026-11-13

### Added
- A standalone landing page at `/`: aurora hero with a real report screenshot,
  the three questions the product answers, measured numbers with sample sizes,
  a three-step workflow, and an explicit open-source / boundary section. This
  gives the product a real front door instead of dropping visitors into a form.
- `capture_evidence.py` captures the landing page and the workspace separately
  (12 scenes plus the optional report page).

### Changed
- The functional workspace moved to `/workspace` and keeps the app shell,
  upload composer and report entry. Navigation, the command palette, the report
  back link, the history empty state and the brand link all point there.

## [1.4.0] - 2026-11-13

### Changed
- Information architecture: the left navigation is now three groups
  (核验 / 工具 / 更多) with labeled entries on desktop. Batch, cohort,
  benchmark, model settings and about moved under 更多 instead of competing
  with the daily workflow.
- Home is task-first: the upload card now sits in the hero's right column, so
  choosing a file is the first action on the page. Secondary numbers moved
  below it; the capability grid, preview mock and recent-task block were
  removed from the landing view.
- Report page leads with the conclusion and the five-dimension health panel;
  the review issue list, source health, chart spot-check, citation consistency
  and charts are collapsed under 检查明细. The old "体检结论" duplicate was
  folded into the review summary.
- Page names now match navigation: 报告 (全部报告), 批量聚合, 模型设置.
- History table uses one checkbox for compare/zip/cohort actions instead of a
  second per-row "打包" checkbox; dates render as `YYYY-MM-DD HH:MM`.

### Fixed
- Details elements no longer leak their content when closed (export menu,
  evidence drawer, page viewer, advanced checks).
- Report pages scroll naturally instead of clipping content inside a fixed
  viewport; the health radar scales with its column.
- Wide-screen sidebar labels were invisible until hover; from 1180px the rail
  is expanded and readable.

### Tests
- `pytest tests -q` -> 664 passed.

### Fixed (test isolation)
- Tests no longer write into the real `data/history.db`: the autouse fixture
  points `CITEGUARD_HISTORY_DB` at `tmp_path`, and `HistoryDB.sync_dir()` now
  prunes index rows whose backing job JSON disappeared. Full suite leaves the
  developer's history index untouched.

## [1.3.4] - 2026-11-12

### Added
- OpenAPI contract tests for the public integration surface. `/api/support/check`
  and `/api/support/batch` now publish their JSON request bodies in the schema
  (behavior and 400 errors unchanged).
- `scripts/capture_evidence.py`: capture 11 pages plus an optional report page
  at 1920x1080, fail on console errors, and write PNGs under
  `docs/evidence/shots/captured/` (gitignored).
- `docs/status_v1.3.4.md`: capability matrix, current verified numbers and the
  remaining external blockers in one page.

### Tests
- `pytest tests -q` -> 661 passed.

## [1.3.3] - 2026-11-12

### Added
- Offline end-to-end smoke in CI. `scripts/e2e_smoke.py` accepts a plain-text
  paper (no PDF/annotation) and a new `smoke` GitHub Actions job starts the app
  with `CITEGUARD_OFFLINE=1`, uploads a small text paper and checks report,
  exports, evidence bundle and diff (13 checks). Local run: 13/13.

### Tests
- `pytest tests -q` -> 658 passed.

## [1.3.2] - 2026-11-12

### Added
- SQLite sidecar for the local reference library. JSON remains authoritative;
  every save also refreshes `library.json.sqlite3`, `Library.load` falls back
  to the sidecar when JSON is missing/corrupt, and migration/rollback are
  explicit (`scripts/migrate_library_sqlite.py`). Rollback refuses to overwrite
  JSON with an empty sidecar. DOI de-duplication is preserved in the index.

### Tests
- `pytest tests -q` -> 658 passed.

## [1.3.1] - 2026-11-12

### Added
- Blind human-audit scorer: reads the filled 60-item sheet plus the separate
  answer key, rejects empty/malformed/low-coverage sheets, and reports
  accuracy, macro-F1, Cohen's kappa, per-label metrics and a confusion matrix.
  Optional prediction CSV compares system vs human vs constructed labels.
  No human labels exist yet; the docs say so and the tool refuses to score an
  empty sheet.

### Tests
- `pytest tests -q` -> 653 passed.

## [1.3.0] - 2026-11-12

### Added
- CiteBench-CN v2: 500 Chinese references across 11 constructed categories
  (v1 Exact/Minor/Major + author_swap, year_shift, venue_swap, doi_swap,
  paraphrase, fabricated, retracted, predatory). Unique source works; dataset
  card and build/eval scripts included.
- Product baseline on 453 metadata items: precision 1.0000 (0 false positives
  on 100 real Exact), recall 0.6487 / F1 0.7869 when Unknown counts as a miss;
  after excluding Unknown, recall 0.8707 / accuracy 0.9063. Retracted: 17/17.
  No predatory detector: reported as a gap, not a score.
- Public leaderboard page with separate tables for Chinese metadata checking,
  ClaimSupport-CN model comparison, retraction and external references.

### Tests
- `pytest tests -q` -> 648 passed.

## [1.2.0] - 2026-11-12

### Added
- Cohort view for a batch of finished reports: `/aggregate?ids=...` shows average
  citation-health score, grade distribution, five-dimension averages, the five
  most common problems and a per-paper ranking; CSV export. Entry point is the
  "聚合健康画像" button on the history page (up to 50 reports).
- API `GET /api/aggregate` and `GET /api/aggregate.csv`; reports of the same
  filename are merged (first kept, rest listed under `duplicates`), unfinished
  jobs are skipped and listed under `missing`.
- Real run over 21 distinct papers / 509 references: mean health 76.1, A1 B2 C13
  D1 E4; top issues are missing DOI/volume fields and unverified references. The
  9 Major labels in this cohort were manually traced to two PDFs whose two-column
  reference lines were merged by the parser (broken DOIs), not to faked citations;
  documented in docs/aggregate.md.

### Tests
- `pytest tests -q` -> 645 passed.

## [1.1.5] - 2026-11-12

### Added
- Replacement suggestions: from a reference's citation context, search OpenAlex
  and show up to three candidates with a ready-to-paste GB/T 7714 entry, DOI
  link and an explicit "verify before replacing" note. Drawer button in the
  report; `GET /api/report/{id}/replacement?index=N`.
- Retrieval benchmark over 21 real papers: 438 citation-context queries, 477
  candidate references; BGE-M3 beats BM25 and title overlap (Recall@1 0.1986,
  Recall@3 0.3219, MRR 0.2948). Absolute numbers are low because ground truth is
  the cited reference, not a claim-support label; documented in docs/replacement.md.

### Tests
- `pytest tests -q` -> 642 passed.

## [1.1.4] - 2026-11-12

### Added
- Retraction and correction check for every matched reference that carries a DOI:
  OpenAlex `is_retracted`, Crossref `relation.updated-by/update-to`, capped at 40
  references with 4 workers. Red banner on the report overview and per-entry
  pills; `references[i].retraction` plus top-level `retractions` summary.
  `src/citeguard/retraction.py`; docs/retraction.md.

### Fixed
- English author-year citations wrapped in full-width parentheses
  （Livingston et al., 2020）are now recognised, so Chinese papers that cite
  English authors in Chinese punctuation no longer lose citation coverage.

### Tests
- `pytest tests -q` -> 640 passed.

## [1.1.3] - 2026-11-12

### Added
- Fix preview: every parsed reference is re-typeset as a GB/T 7714-style entry
  without any online lookup, with before/after text and tags for what changed
  (type code, author separators, bracketed year, DOI form, trailing period).
  Missing fields are flagged instead of invented; entries without title/authors/
  year are marked "待核对". Export the revised list as TXT.
  `src/citeguard/fix.py`; `GET /api/report/{id}/fixed` and `.../fixed.txt`.

### Fixed
- Volume/pages/article numbers left inside the venue string are moved back into
  their fields, so re-typesetting no longer duplicates "12, 138-150, 2025: 138-150"
  or "238, Article ID: 121801, 2024: 238".

## [1.1.2] - 2026-11-12

### Added
- In-page evidence viewer: clicking a "第 N 页" citation chip opens the cited
  page rendered at analysis time (left) next to the page text (right), with the
  quoted claim highlighted. Cited pages are rendered once per job (≤20 pages,
  140 dpi) and stored under the job directory; APIs:
  `GET /api/report/{job_id}/page/{page}.json` and `.../{page}.png`.
  `src/citeguard/pipeline.py::_save_citation_pages`.

### Fixed
- Extracted page text kept one line per PDF line (ragged column) and inserted
  spaces between Chinese characters; text is now collapsed and CJK gaps removed.
- Page-viewer modal was nested in the shell stacking context, so the left rail
  covered its title; it now renders from a page-level `modals` block.

## [1.1.1] - 2026-11-12

### Added
- Triage state on every report entry: 待修 / 已修 / 忽略, persisted per job under
  `data/triage/`, filterable from the review toolbar and editable in the drawer.
  Re-check diffs auto-close resolved entries as 已修 (ignored entries are kept).
  APIs: `GET|POST /api/report/{job_id}/triage`. `src/citeguard/triage.py`.

### Fixed
- Active filter chip rendered white-on-white in the dark theme (app.css used
  `var(--ink)` as a background while the refreshed theme treats it as text).

## [1.1.0] - 2026-11-12

### Added
- Citation health profile: every report now carries a 0–100 score and A–E grade
  across five weighted dimensions — authenticity 25, support 25, relevance 20,
  coverage 15, compliance 15. Support is skipped (and confidence drops) when no
  claim had a judgeable abstract; Unknown is never counted as Major. The report
  overview renders a score ring, five-axis radar, per-dimension bars and up to
  three "fix first" suggestions. `src/citeguard/health.py`, `docs/health.md`.
  Real 15-reference paper: 95.9 / A with confidence 0.75 (support not checked).
  Evidence: `docs/evidence/shots/phase-F1-health-v1.1.0.png`,
  `tests/test_health.py`.

## [1.0.14] - 2026-11-12

### Changed
- Layout-vs-text reference selection no longer requires a +0.02 title-health
  margin. The layout candidate now wins when it keeps at least as many entries
  and has better titles (or equal titles and more entries). Phi-3 blind PDF:
  71 refs / 0.972 → 72 / 0.986; Mixtral stays on the text path (35 / 1.000 vs
  27 / 0.926), so its product result is unchanged. Evidence:
  `data/experiments/refs_layout_selection.json`,
  `scripts/eval_layout_selection.py`.

## [1.0.13] - 2026-11-12

### Added
- HuggingFace public release: dataset `dfdafs/claimsupport-cn-300` and LoRA adapter
  `dfdafs/citeguard-support-lora-qwen3-1.7b` (Apache-2.0, with training scripts).
- Real BGE-M3 embedding endpoint evaluated: recall@1 0.8667 / MRR 0.9042 on 300
  ClaimSupport-CN items with 5 distractors (`docs/embeddings.md`). Constructed
  labels, link-only validation; endpoint is not wired into the product path.
- GROBID reference-extraction comparison on the three blind-test PDFs: 74/73,
  90/92, 35/27 (counts only; no field-level quality claim).

### Changed
- Docker data disk moved from C: to `D:\Docker\wsl` behind a junction; C: free
  space 3.1 GB → 18.7 GB. The 1.0.12 image and hello-world survived the move.

## [1.0.12] - 2026-11-12

### Added
- Full-site accessibility audit: 11 pages × 4 checks plus 6 keyboard checks
  (`scripts/audit_frontend.py`, 50/50 passing) and a real favicon.

### Fixed
- `/favicon.ico` 404 in the console (served as SVG from `web/static/img/`).

## [1.0.11] - 2026-11-11

### Added
- Reference → body back-links: each entry gets `cited_in` (key, page, sentence),
  shown in the evidence drawer as “正文引用 N 处”.

## [1.0.10] - 2026-11-11

### Added
- Figure/table mentions in the body (`图 3`, `表 2`, `Fig. 3`, `Table 2`) are
  extracted into `citations.captions` and summarized on the report page.

## [1.0.9] - 2026-11-11

### Added
- Annotated PDFs now also pin in-text citations to the page they occur on
  (left margin, up to 4 per page / 40 total), using the page numbers from 1.0.8.
  Citations without a located page are reported as `citations_unmapped`, never
  placed on a guessed page.

## [1.0.8] - 2026-11-11

### Added
- Best-effort page numbers for in-text citations: sentences are matched against
  normalized page text and the report shows `第 N 页` next to the citation key.
  On the 10-page real sample, 17/18 citations were located; one sentence split
  across a page boundary is not recovered (documented limit).

## [1.0.7] - 2026-11-11

### Changed
- Report citation coverage now resolves author-year keys (`Smith et al., 2020`,
  Chinese author-year) to reference entries instead of counting numeric keys only.
- Added a real-corpus citation extraction evaluation: 22 papers / 529 references,
  21 papers with citations (95.5%), 318 cited entries (60.1%), 89.5% key
  self-consistency. This is an automated check, not human-annotated accuracy.

### Docs
- `docs/citation_eval.md` documents method, numbers and limits.

## [1.0.6] - 2026-11-11

### Added
- Optional embedding backend (`citeguard.embeddings`) for an OpenAI-compatible
  `/embeddings` endpoint (BGE-M3, TEI, vLLM). Off by default; unconfigured calls
  raise a human-readable error instead of silently degrading.
- `cosine()` and `rerank()` helpers; 6 tests against a local stub server.
- `docs/embeddings.md` documents the environment contract and the honest boundary:
  no real BGE-M3 endpoint is deployed in this environment, so no recall claim.

## [1.0.5] - 2026-11-11

### Added
- Report overview shows citation coverage: how many reference entries are actually
  cited in the body, and which numbers never appear. Real run: 15/15 cited.
- `citation_anchor.coverage()` with unit test; coverage stored under
  `report.citations.coverage`.
- Evidence screenshot `docs/evidence/shots/phase-29-citation-coverage-1.0.5.png`.

## [1.0.4] - 2026-11-11

### Added
- Report citations are now actionable: clicking “第 N 条” switches to the
  “审稿条目” tab, pages to the right slice and opens that entry’s evidence
  drawer, so a citation and its reference take one click to compare.
- Evidence screenshot `docs/evidence/shots/phase-28-citation-jump-1.0.4.png`.

## [1.0.3] - 2026-11-11

### Added
- Report “总览” now lists the article’s in-text citations (key, sentence, matched
  reference numbers); the full list remains in the report JSON. Verified on a real
  run: 18 citations / 18 sentences, first 6 rendered.
- Evidence screenshot `docs/evidence/shots/phase-27-citation-list-1.0.3.png`.

### Changed
- Version bump to 1.0.3.

## [1.0.2] - 2026-11-11

### Fixed
- Keyboard shortcuts now work from any report tab: `j`/`k` and `/` switch to the
  "审稿条目" tab before moving focus, so they no longer target a hidden list.
- Rail navigation links had no accessible name when the sidebar text was hidden;
  added `aria-label` to every rail link.

### Added
- Frontend keyboard/accessibility audit (`data/experiments/frontend_audit.json`):
  8 checks at 1280 px — Ctrl+K palette, j/k row focus, Enter drawer, Esc close,
  `/` search, no horizontal overflow, aria-live present, all controls named.
- Evidence screenshot `docs/evidence/shots/phase-26-keyboard-a11y-1.0.2.png`.

## [1.0.1] - 2026-11-11

### Fixed
- Light theme failed WCAG AA: muted text was 2.96:1 and white-on-accent was 3.34:1.
  Tokens changed to `--muted #5f726d` and `--accent #08785f`; all audited pairs now pass.
- `CHANGELOG.md` contained mojibake from an earlier Windows encoding mix; rewritten.

### Added
- `src/citeguard/contrast.py` + `scripts/check_contrast.py`: WCAG 2.1 contrast audit,
  evidence in `data/experiments/contrast_report.json`, documented in `docs/accessibility.md`.
- Regression test that fails if light-theme tokens drop below AA.

## [1.0.0] - 2026-11-11

First stable release. Desktop web app (1280-1920 px) for verifying Chinese and English
academic citations against real metadata sources.

### Verification core
- Citation-anchor extraction: numeric keys (`[12]`, `[3-5]`, `[12,15]`), Chinese
  `文献[12]`, author-year (`(Smith et al., 2020)`), superscript and footnote variants.
- Grounding check: quoted evidence must appear in the source text, otherwise confidence
  is reduced and the reason says why.
- Multi-conclusion decomposition, confidence calibration (ECE 0.040, 300 constructed items),
  low-confidence marking, and a local feedback queue.

### Repair loop
- Field-level re-check diff (resolved / new / still open), annotated PDF in the page margin,
  batch verification page, batch report ZIP, figure-caption suggestions, and a missing-library
  lookup with one-click import.

### Depth and scale
- Open-model registry (hosted DeepSeek, Qwen3-14B bf16/4-bit, LoRA) selectable in the UI.
- History index in SQLite with JSON export; 1000-item stress test (cold 0.718 s, warm 0.159 s).
- Sixth pre-registered blind test on 3 new PDFs: 187/71/79 references, title-health 99.47/97.18/100%.
- Chinese traditional-to-simplified normalization (hit rate 0.0% -> 100% on 206 titles).
- Layout fallback moved from PyMuPDF to pypdfium2 (identical entry counts on 3 PDFs).

### Packaging
- Dockerfile/compose, Python SDK, REST + SSE endpoints, Chrome/Edge extension, Word task pane
  preview, mkdocs site, dataset and adapter bundles.

### Known limits
- GROBID comparison was blocked by a corrupted Docker data directory on the dev machine; the directory was reset on 2026-11-12 and `citeguard-cn:1.0.12` now builds and passes `/api/health` (see E49).
- BGE-M3 semantic recall is not wired.
- Word task pane was not validated inside a real Word client.
