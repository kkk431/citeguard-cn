# CiteGuard-CN v1.0.0

**Release date:** 2026-11-11

## What it is

A desktop web app that checks every citation in a paper: does the work exist,
does the cited evidence support the claim, and does the entry follow
GB/T 7714-2025. It runs against real metadata sources, with an offline mode.

## Highlights

- **Evidence chain**: each citation keeps its sentence, the matched record, the
  checked sources, and a grounding flag when the quoted evidence is not found.
- **Repair loop**: field-level re-check diff, margin-annotated PDF, batch check,
  and report ZIP export.
- **Open models as first-class options**: hosted DeepSeek or a local Qwen3-14B
  (bf16 / 4-bit), with a settings page that probes the endpoint before switching.
- **Open results**: source code (Apache-2.0), a 300-item constructed Chinese claim
  support set, a LoRA adapter for Qwen3-1.7B, and reproducible evaluation scripts.

## Numbers (with boundaries)

| Metric | Value | Boundary |
|---|---|---|
| CiteBench-CN 250 | macro-F1 0.9684 | constructed benchmark, not human labels |
| ClaimSupport-CN 300 | macro-F1 0.9841 / acc 0.9833 | rule-constructed labels |
| Qwen3-1.7B LoRA test | macro-F1 0.9721 (base 0.4935) | 80 training items |
| Real corpus 22 papers | 529 refs, clean 1.0, 0 Major | parser clean rate is heuristic |

## Upgrade notes

No migration needed from 0.9.x. The model registry lives in
`data/judge_models.json`; API keys are never stored there.

## Known limitations

- Chinese coverage relies on the user importing CNKI/Wanfang RIS files.
- The Word task pane is a preview and has not been tested inside Word.
- GROBID comparison was not obtained; the local Docker store was damaged by a
  full system disk.
