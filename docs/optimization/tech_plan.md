# 技术优化总计划（Batch 0–2）

基线：v1.7.50；1131 tests / 10 skipped；verify 137/137；evidence audit 310 路径 / 167 截图。
契约：`docs/autonomous_optimization_master_prompt.md`。

## Batch 0：基线、级联、版本

| 项 | 验收 | 证据 | 状态 |
| --- | --- | --- | --- |
| 0.1 评测/基线 harness | 固定 100 盲标、409 真实、529 解析、105 格、25/30 全文；输出一页 scorecard | `data/experiments/opt_b0_harness_2026-11-27.json` | ✅ |
| 0.2 成本感知模型级联 | 1.7B 先判、低置信/长证据升级 14B；记录 stage/latency；测试覆盖 | `data/experiments/opt_b0_cascade_replay_2026-11-27.json` | ✅（回放无收益，不设默认） |
| 0.3 版本感知实体消解 | DOI/arXiv 别名、预印本/正式版、年份/作者/venue 冲突、provenance；409 false Major 0 | `data/experiments/opt_b0_version_cases_2026-11-27.json` | ✅ |

## Batch 1：断言级证据

状态：1.1 已有词面基线审计，跨语言 10/10 insufficient（最高词面覆盖 0.0497）；
`/api/support/check` 当前 503，语义 judge 不可用；无外部资源/embedding，按负结果记录，待 judge 恢复后再评。
1.4 置信门禁已评估：全量机器证据 8/31（25.8%）；阈值 0.9 时展示 7 条、正确 5 条，
precision 0.7143 / recall 0.625 / F1 0.6667；只能作为“高置信候选”筛选，不能当作全面机器证据精度。
CiteMap 证据图已接「只看高置信机器候选（≥0.9）」，真实关系 36→35；E132。
1.2 保守共识：101 个已解析格中，机器证据 31 格只有 **5** 格 3/3 接受、12 格拒绝、14 格 2:1 争议；可接受边 5 条，不把机器置信当人工接受。
1.1 语义回放：31 条机器证据，直接 judge F1 .6667；断言拆解 .6364，负结果，不接产品。
1.3 Live 抽取前移已验证：6 页夹具 451/451 映射、30/30 来源定位；产品入口 `/api/live/page`，只做定位、不判真伪。

| 项 | 验收 | 证据 |
| --- | --- | --- |
| 1.1 断言拆解 + 全文证据对齐 | 子断言、证据跨度、full/partial/contradict/insufficient；span P/R | `data/experiments/opt_b1_1_alignment_lexical_2026-11-27.json`、`opt_b1_1_alignment_semantic_2026-11-27.json`（✅ 负结果：语义 F1 .6364 < 直接 .6667，不接产品） |
| 1.2 人机证据图共识 | 3/3 才 accepted；2:1 contested；机器候选不能自升 | `data/experiments/opt_b1_2_consensus_2026-11-27.json` ✅（机器证据接受 5/31） |
| 1.3 Live 页面抽取前移 | 6 页夹具 451/451 映射、30/30 来源定位；产品 `/api/live/page` | `data/experiments/opt_b1_3_live_extraction_2026-11-27.json` ✅（已有能力，边界已写） |
| 1.4 CiteMap 机器精度 | 105 格机器完整支持 precision | `data/experiments/opt_b1_4_citemap_gate_2026-11-27.json` ✅（阈值 0.9：P .7143/R .625） |

## Batch 2：引用链、解析、工程、安全

| 项 | 验收 | 证据 |
| --- | --- | --- |
| 2.1 引用链 2 跳 | 实现 + 单测；真实 2 跳覆盖 blocked（OpenAlex 引用批次失败） | `data/experiments/opt_b2_1_chain_2hop_2026-11-27.json`（🟡 默认仍 1 跳） |
| 2.2 版式感知解析 | 529 clean 1.0 不回退；新盲测 | `data/experiments/opt_b2_parse_*.json` |
| 2.3 工程可靠性 | 队列/DB、幂等、断点、并发 | `data/experiments/opt_b2_ops_*.json` |
| 2.4 安全/隐私 | token/限流/SSRF/日志脱敏 | `data/experiments/opt_b2_security_*.json` |

## 统一门禁

- 1131 tests 不下降；verify 137/137；证据索引 0 missing / 0 unregistered。
- 409 条真实引用 false Major 仍为 0。
- 每项有基线对比；没有基线/消融不叫“新算法”。
- 不新增外部资源、不买库、不训练新基础模型、不做公网演示。
- 材料只同步报告/资源清单/佐证/提交包；PPT/视频不改。
