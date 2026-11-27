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

| 项 | 验收 | 证据 |
| --- | --- | --- |
| 1.1 断言拆解 + 全文证据对齐 | 子断言、证据跨度、full/partial/contradict/insufficient；span P/R | `data/experiments/opt_b1_evidence_*.json` |
| 1.2 人机证据图共识 | claim–paper–evidence 三分图；人工 accept 才升级 | `data/experiments/opt_b1_graph_*.json` |
| 1.3 Live 页面抽取前移 | 扩展侧/服务端兜底；中文页；页面→[n] 映射 | `data/experiments/opt_b1_live_*.json` |
| 1.4 CiteMap 机器精度 | 105 格机器完整支持 precision | `data/experiments/opt_b1_citemap_*.json` |

## Batch 2：引用链、解析、工程、安全

| 项 | 验收 | 证据 |
| --- | --- | --- |
| 2.1 引用链 2 跳 | 覆盖、误报、时间前后 | `data/experiments/opt_b2_chain_*.json` |
| 2.2 版式感知解析 | 529 clean 1.0 不回退；新盲测 | `data/experiments/opt_b2_parse_*.json` |
| 2.3 工程可靠性 | 队列/DB、幂等、断点、并发 | `data/experiments/opt_b2_ops_*.json` |
| 2.4 安全/隐私 | token/限流/SSRF/日志脱敏 | `data/experiments/opt_b2_security_*.json` |

## 统一门禁

- 1131 tests 不下降；verify 137/137；证据索引 0 missing / 0 unregistered。
- 409 条真实引用 false Major 仍为 0。
- 每项有基线对比；没有基线/消融不叫“新算法”。
- 不新增外部资源、不买库、不训练新基础模型、不做公网演示。
- 材料只同步报告/资源清单/佐证/提交包；PPT/视频不改。
