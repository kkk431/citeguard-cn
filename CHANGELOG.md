# Changelog

All notable changes to CiteGuard-CN. Earlier pre-1.0 history is condensed.

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
