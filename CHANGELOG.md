# Changelog

All notable changes to CiteGuard-CN. Versions before 0.9.75 are condensed.

## [1.0.0] - 2026-11-11

First stable release. The product is a desktop web app (1280–1920 px) for verifying
Chinese and English academic citations against real metadata sources.

### Verification core
- Citation-anchor extraction: numeric keys (`[12]`, `[3-5]`, `[12,15]`), Chinese
  `文献[12]`, author-year (`(Smith et al., 2020)`, `（张三，2020）`), superscript and
  footnote markers; each hit carries its sentence and character offsets.
- Grounding check: judged evidence quotes must appear in the source text, otherwise
  the confidence is discounted and the reason is surfaced.
- Multi-conclusion decomposition: one citation containing several numeric or
  directional claims is split and judged claim by claim.
- Confidence calibration: bucket statistics, ECE, abstain curve; low-confidence
  results are labelled instead of silently trusted.
- Local feedback queue (`POST /api/feedback`) for mistaken labels.
- Reference-list extraction hardened on real PDFs: numeric/author-year/ACL/APA
  layouts, letter keys, layout fallback via pypdfium2 (PyMuPDF is optional only).

### Repair loop
- Re-check diff between two reports (resolved / new / still present, field level).
- Annotated PDF: problems marked in the page margin and downloadable.
- Batch check page (paste up to 50 claims) and batch report ZIP export.
- Figure checks integrated into the main report, with caption advice.
- Library coverage: external title lookup with one-click add, DOI dedupe.

### Scale and integration
- Model registry and settings page: hosted DeepSeek, local Qwen3-14B (bf16/4-bit),
  local LoRA adapter; switching probes the endpoint first and refuses on failure.
- SQLite history index with JSON export.
- 1000-reference stress test (offline, synthetic) and SSE job progress.
- Python SDK (`citeguard.client`), Chrome/Edge extension, Word task pane preview,
  Docker image, REST API.
- Chinese recall: OpenCC t2s normalization is optional and only used when the
  optional dependency is installed.

### Evaluation (honest boundaries)
- CiteBench-CN 250 items: macro-F1 0.9684 (DeepSeek zero-shot baseline 0.5159).
- ClaimSupport-CN 300 constructed items: macro-F1 0.9841, accuracy 0.9833;
  labels are rule-constructed, not human-annotated.
- Qwen3-1.7B LoRA (r16, 80 training items): test macro-F1 0.9721 (base 0.4935);
  adapter and training script released.
- Real corpus, 22 papers / 529 references: parser clean rate 1.0, 0 Major status.
- Sixth pre-registered blind test (3 unseen PDFs): reference extraction passed the
  pre-registered health-rate threshold; it measures parser health, not semantic
  correctness.

### Known limitations
- Chinese metadata coverage depends on the user's own library imports; open sources
  are weaker for CNKI-only records.
- OCR is optional and evaluated, not required.
- Word task pane has not been verified in a real Word client.
- GROBID comparison is not reported: the local Docker store was corrupted when the
  system disk filled up.
