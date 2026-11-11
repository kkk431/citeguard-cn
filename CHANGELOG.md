# Changelog

All notable changes to CiteGuard-CN. Earlier pre-1.0 history is condensed.

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
- GROBID comparison is blocked by a corrupted Docker data directory on the dev machine.
- BGE-M3 semantic recall is not wired.
- Word task pane was not validated inside a real Word client.
