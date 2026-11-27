# Batch-0 评测基线

生成：2026-11-27T10:30:03.505547+00:00

| 数据 | n | 关键指标 | 来源 |
| --- | ---: | --- | --- |
| support_human_100 | 100 | acc=0.99 macro-F1=0.9877072612921669 κ=0.98116 | `data/experiments/human_audit_100.json` |
| support_constructed_300 | 300 | 见 JSON | `data/experiments/release300.json` |
| real_references_409 | 409 | Exact 125 / Minor 87 / Unverified 197 / Unknown 0 / Major 0 | `data/experiments/verify_real.json` |
| local_library_409 | 409 | 见 JSON | `data/experiments/library_real.json` |
| parse_529 |  | clean=1.0 | `data/experiments/parse_real.json` |
| citemap_105 | 105 | κ=0.6587 evidence P=0.2581 | `data/experiments/citemap_audit_105/agreement.json` |
| fulltext_25_of_30 | 258 | 25/30 papers, 258 pairs | `data/experiments/citemap_atomic_fulltext_v3_summary.json` |
| mutation_200 |  | 见 JSON | `data/experiments/real_mutation_eval.json` |
| calibration |  | 见 JSON | `data/experiments/support_calibration.json` |
| retrieval_baselines |  | 见 JSON | `data/experiments/replacement_eval.json` |

## 门禁

- ✅ real_false_major_zero
- ✅ human_n_100
- ✅ parse_clean_1_0
- ✅ citemap_105_cells
- ✅ fulltext_25_of_30
