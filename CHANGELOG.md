## [1.7.8] - 2026-11-14

- CiteGuard Live 公开页评测：5 篇 arXiv HTML、30 条英文正文句、每页 6 条；hit@3 **0.60**（18/30）、hit@1 0.4667、P50 16.7 ms、P95 3.53 s；句子与页面/参考文献真实对应，正确 DOI 在候选池内，4 条排 4–5、8 条被 top-5 截断。
- 中文跨语言 30 句集保留为基线（hit@3 0/30）并明确与公开页集任务不同、禁止混算；证据矩阵增至 27 行、待补 2 项；857 passed。

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
