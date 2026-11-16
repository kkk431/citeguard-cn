# CiteMap 48h spike：论文-断言-证据图数据契约

状态：可演示数据层已落地（2 个静态主题，30 篇论文，21 条原子断言，105 格审计数据）。  
范围：只生成前端可消费的 JSON 与校验测试，不改 `web/`，不下载模型、不跑 GPU。  
产出：`data/evidence_map/graph/ai_education.json`、`data/evidence_map/graph/medical_imaging.json`。

## 1. 结论

- “论文 → 断言 → 证据”三层关系可以落地，且不需要重跑抽取：图数据直接由现有 corpus、`claims_atomic.json`、`extractions_fulltext/`、`extractions_atomic/` 与 `data/experiments/citemap_audit_105/merged.csv` 组装。
- 两个主题合计 **93 个节点、138 条边**；其中 **40 条 fulltext 边、11 条 abstract 边、87 条 none 边**。
- 105 个父级 cell 全部有边：16 个 fulltext、2 个 abstract_only、87 个 none。没有把摘要/机器候选伪装成 fulltext。
- 前端可以用一份完全静态的 JSON 渲染：实线 = fulltext，虚线/点线 = abstract_only，无证据 = 不画证据块（edges 中 kind=none 可用于显示 “无机器证据” 计数）。
- 当前产物是 **spike 数据契约**，不是完整产品；没有网页改动，也没有新增人工标注。

## 2. JSON 契约

```json
{
  "schema_version": "1.0",
  "topic": {"topic_id": "ai_education", "name_zh": "人工智能教育", "...": "..."},
  "topic_id": "ai_education",
  "generated_at": "2026-11-14",
  "nodes": [
    {"id": "edu-001", "type": "paper", "label": "...", "meta": {"paper_id": "edu-001", "year": 2024, "doi": "...", "license": "cc-by", "fulltext_available": true}},
    {"id": "edu-c1", "type": "claim", "label": "...", "meta": {"claim_level": "parent", "parent_claim_id": "edu-c1"}},
    {"id": "edu-c1-a1", "type": "claim", "label": "...", "meta": {"claim_level": "atomic", "parent_claim_id": "edu-c1"}},
    {"id": "ft-ai-education-edu-001-edu-c1-a1", "type": "evidence", "label": "...", "meta": {"level": "fulltext", "quote": "...", "locator": "Full text · 逐句检索"}}
  ],
  "edges": [
    {
      "id": "e0001",
      "source": "edu-001",
      "target": "edu-c1-a1",
      "kind": "supports",
      "level": "fulltext",
      "evidence_id": "ft-ai-education-edu-001-edu-c1-a1",
      "quote": "exact substring...",
      "locator": "Full text · 逐句检索",
      "page": "",
      "meta": {"edge_scope": "evidence", "stance": "support", "atomic_id": "edu-c1-a1", "parent_claim_id": "edu-c1"}
    }
  ],
  "summary": {
    "papers": 15, "claims": 16, "parent_claims": 4, "atomic_claims": 12,
    "evidence": 20, "edges": 78,
    "fulltext_edges": 21, "abstract_edges": 7, "machine_edges": 50, "none_edges": 50,
    "cells": 60, "cells_fulltext": 8, "cells_abstract_only": 2, "cells_none": 50
  },
  "provenance": {"corpus": "corpus/ai_education.json", "...": "..."}
}
```

### 2.1 节点

| type | id 示例 | 必需字段 | 说明 |
|---|---|---|---|
| paper | `edu-001` | id, type, label, meta | 15 篇/主题；meta 含 title/year/venue/doi/url/license/is_oa/fulltext_available |
| claim | `edu-c1`, `edu-c1-a1` | id, type, label, meta.claim_level | 7 个父断言 + 21 个原子断言；父/原子都保留，避免 105 格与 21 条断言二选一 |
| evidence | `ft-...`, `atom-...`, `machine-cell-...` | id, type, label, meta.level | 35 个证据节点；meta 含 paper_id/claim_id/atomic_id/stance/quote/locator/confidence/source |

### 2.2 边

| 字段 | 取值 | 规则 |
|---|---|---|
| `source` | paper id | 必须是 paper 节点 |
| `target` | claim id | parent 或 atomic claim 节点 |
| `kind` | `supports` / `contradicts` / `none` / `abstract_only` | 方向性只给 fulltext；摘要证据统一 `abstract_only` 并在 meta.stance 保留 support/contradict |
| `level` | `fulltext` / `abstract` / `machine` | 缺失全文的边禁止标 fulltext；`none` 固定 `machine` |
| `evidence_id` | evidence id 或空 | `none` 必须为空；其他 kind 必须指向 evidence 节点 |
| `quote` | 原文片段或空 | `none` 必须为空；其他 kind 必须有 `evidence_id` 和 quote |
| `locator` / `page` | 字符串 | 有则带；当前 fulltext 为 “Full text · 逐句检索”，摘要为 “Abstract”/“摘要候选片段” |

## 3. 统计（生成结果）

| 指标 | ai_education | medical_imaging | 合计 |
|---|---:|---:|---:|
| 论文节点 | 15 | 15 | 30 |
| 断言节点 | 16（4 父 + 12 原子） | 12（3 父 + 9 原子） | 28（7 + 21） |
| 证据节点 | 20（13 fulltext + 5 atomic + 2 machine） | 15（11 fulltext + 4 atomic） | 35 |
| 边 | 78 | 60 | 138 |
| fulltext 边 | 21（8 父 + 13 原子） | 19（8 父 + 11 原子） | 40 |
| abstract 边 | 7（5 原子 + 2 machine 摘要） | 4（4 原子） | 11 |
| none 边 | 50 | 37 | 87 |
| 105 格 cell | 60 | 45 | 105 |
| cell fulltext | 8 | 8 | 16 |
| cell abstract_only | 2 | 0 | 2 |
| cell none | 50 | 37 | 87 |
| JSON 大小（缩进 2 空格） | ~104 KB | ~84 KB | — |

说明：

- **fulltext 边 40 = 16 条父级 cell 汇总 + 24 条原子级证据。** 同一 `evidence_id` 可以同时出现在父级汇总边和原子证据边上；边 id 唯一，前端按 `evidence_id` 去重即可。父级边用于 105 格总览，原子边用于精确引用。
- **abstract 边 11 = 9 条原子摘要证据 + 2 条 105 格中“机器证据经人工多数认定为 correct、但无全文”的摘要边。** 2 条合成证据的 id 为 `machine-cell-*`，quote 来自 105 格 organizer key 的摘要候选片段，不伪造全文。
- **none 边 87 = 18 条“机器证据被人工判 issue 且无全文” + 69 条“无机器证据且无全文”。** 其中 67 条无机器证据 cell 的人工多数是 correct（即“无证据”是审计结论，不是“假”）。
- 16 个 fulltext cell 覆盖 13 篇论文（ai 6 篇、medical 7 篇）；其余 17 篇没有 fulltext 证据。fulltext 记录共 24 条（13 + 11），没有 contradict 的 fulltext 记录；唯一的方向性 contradict 来自 2 条机器 correct 摘要 cell 中的 `edu-007`，在图中是 `abstract_only` + `meta.stance=contradict`。
- 105 格审计分布（父级 cell）：16 fulltext（8 correct / 6 issue / 2 missing）、2 machine-correct 无全文、18 machine-issue 无全文、69 无机器无全文（67 correct / 2 missing）。机器证据总 31 格：8 correct、23 issue；11 格与全文重叠，20 格无全文。这里只复述审计数据，不修改人工标签。

## 4. 105 格映射

| 105 格类型 | 数量 | 图中的边 |
|---|---:|---|
| 有 fulltext 证据 | 16 | 父 claim 一条 fulltext 汇总边；每条 fulltext 记录再给原子 claim 一条 fulltext 边 |
| 机器证据人工多数 correct、无 fulltext | 2 | 父 claim 一条 abstract_only 边；合成 evidence 节点，quote 来自摘要片段 |
| 机器证据人工多数 issue、无 fulltext | 18 | 父 claim 一条 none 边；不带 evidence_id/quote，不把错误候选放进证据层 |
| 无机器证据、无 fulltext | 69 | 父 claim 一条 none 边；其中 67 条人工多数 correct，2 条 missing（缺失审计） |
| **合计** | **105** | 每个 cell 恰好一条父级边 |

原子级另有 24 条 fulltext 边、9 条 abstract 边；它们与父级边是“总览/明细”关系，不是重复计数错误。

## 5. 前端最小字段

最小渲染只需要：

```text
node:  id, type, label, meta.paper_id/meta.claim_level/meta.level
edge:  source, target, kind, level, evidence_id, quote, meta.stance
summary: papers, claims, atomic_claims, evidence, edges, fulltext_edges, abstract_edges, none_edges, cells
```

建议交互：

- paper 节点点击后，按 target claim 聚合边；`level=fulltext` 显示实线和可展开 quote；`level=abstract` 显示虚线和 “仅摘要” 徽标；`kind=none` 不显示引用块，只显示 “无机器证据/无全文证据”。
- 父 claim 与原子 claim 是父子层级；默认先展示父级 105 格，点击父 claim 再展开原子证据。若要单层图，可按 `evidence_id` 去重后只保留原子边。
- `summary.cells_*` 可直接做图例计数；`summary.none_edges` 不要解释成“断言为假”。

## 6. 生成与验证

```bash
# 生成全部 topic（静态 2 个 + 既有 dynamic topic）到 data/evidence_map/graph/
PYTHONPATH=src python -m citeguard.evidence_map --graph

# 只生成静态主题（在代码中）：
python -c "from citeguard.evidence_map import write_graph; print(write_graph('ai_education')); print(write_graph('medical_imaging'))"

pytest tests/test_evidence_graph.py -q
```

测试覆盖：

- 节点/边无悬空，source 为 paper、target 为 claim；
- kind/level 合法；
- 每主题至少 1 条 fulltext 边、存在 none 边；
- fulltext 边有 evidence_id/quote，abstract 边不标 fulltext；
- none 边不带 evidence_id/quote；
- 105 格每个 cell 恰好一条父级边；
- 人工多数 issue 的机器 cell 不被提升为证据；
- 2 条 machine-correct 摘要 cell 在 organizer key 存在时为 abstract_only；
- `write_graph` 写盘后可反序列化。

## 7. 风险与边界

1. **105 格 key 是构建期文件，未纳入 git。** `dist/citemap_audit_full/_organizer_only_key.csv` 当前存在，但未跟踪；如果换机器/清理 `dist`，2 条 machine-correct 摘要 cell 会退化为 none，`abstract_edges` 从 11 变为 9。建议把 key 的紧凑版本（cell_id + machine_stance + evidence_quote）落到 `data/evidence_map/` 或由构建脚本重新生成，否则图统计不可复现。  
2. **父级/原子级重复。** 同一证据会出现两次边（父级汇总 + 原子明细），这是刻意的层级投影；前端必须按 `evidence_id` 或 `(source,target,evidence_id)` 去重再画线，否则视觉上会加粗。  
3. **没有 fulltext contradict。** 24 条 fulltext 全是 support；唯一 contradict 是摘要级机器 correct cell（`edu-007`）。不要把这个图当作“支持/矛盾均衡”的证据。  
4. **none ≠ 假。** 87 条 none 中 67 条是人工多数 correct 的“无机器证据”，2 条缺失审计；UI 必须写“无证据/未覆盖”，不能写“被否定”。  
5. **2 条摘要边是机器候选 + 人工审计 correct，不是 fulltext。** quote 来自摘要候选片段；不要把它标成全文证据，也不要把 18 条 issue 候选的 quote 暴露到证据层。  
6. **未做网页集成。** 本 spike 只产出 JSON 和测试；页面渲染、SVG/Canvas 布局、交互与截图由队长/前端任务接。`web/` 未改动。  
7. **未做真实用户验证。** 图的可读性、父子层级默认展开策略、105 格在窄屏上的聚合方式都未测试；JSON 大小约 84–104 KB（缩进 2 空格），浏览器端可接受，但全量 5 个 topic 同时加载需要懒加载。  
8. **许可证/引用边界不变。** 图只引用 manifest 中的元数据、摘要 quote 和已缓存的全文 quote；没有提交 PDF，也没有新增全文分发。

## 8. 文件与验收

新增/修改：

- `src/citeguard/evidence_map.py`：`build_graph`、`write_graph`、`validate_graph`、`--graph` CLI；
- `tests/test_evidence_graph.py`：12 个契约测试；
- `data/evidence_map/graph/ai_education.json`、`data/evidence_map/graph/medical_imaging.json`：生成产物（未改 web）；
- 本文档。

验收命令：

```bash
python -m pytest tests/test_evidence_graph.py -q
# 12 passed
```

未验证：真实前端渲染、队长抽查图数据交互、105 格 key 的长期可复现性（见风险 1）。

## 9. 2026-11-16 四主题扩展

t28 在原有 2 个静态主题之外新增 `ai_mental_health`、`ai_climate`（各 12 篇 OA 论文、4 条 claim、10 条人工摘要证据、2 条 `auto_evidence` 机器候选），并把机器候选与人工层分键。

- 新增图产物：`data/evidence_map/graph/ai_mental_health.json`、`ai_climate.json`；每个主题 12 个 paper 节点、4 个 claim 节点、10 个 evidence 节点、10 条 `abstract_only` 边，`fulltext_edges=0`、`machine_edges=0`、`none_edges=0`、`cells=0`。
- `auto_evidence` 不进入图：`tests/test_evidence_graph.py::test_extension_topics_keep_auto_evidence_out_of_graph` 断言 10 个 evidence 节点均非 `-auto`。
- 旧 2 主题图仍保留 105 格审计边（40 fulltext / 11 abstract / 87 none）；新增主题没有 105 格审计，因此不生成 parent-cell 边，不能把“10 条摘要证据”误读为全文覆盖。
- 4 个静态主题人工 evidence 合计 40 条（旧 2×10 + 新 2×10）；`auto_evidence` 合计 4 条，仅作契约样例。
- 回归：`python -m pytest tests/test_evidence_map.py tests/test_evidence_graph.py -q` → 175 passed / 10 skipped；`--check` exit 0。
