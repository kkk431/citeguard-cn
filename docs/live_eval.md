# CiteGuard Live 30 句评测集：hit@3、延迟与四档标签分布

> 用 30 条来自开放获取中文论文正文的真实引用句，评测 `check_claim(claim, page_url="", page_title="")` 能否在候选文献前 3 条里找回被引文献（hit@3），并记录 5 个真实公开页、四档标签分布与单次核验延迟。**本集没有 stance 金标**，标签分布是模型/规则输出，不是准确率。

- 数据集：`data/live_eval/pages.json`（5 页）、`data/live_eval/claims.jsonl`（30 句）
- 评测脚本：`scripts/eval_live.py`；结果：`data/live_eval/live_eval.json`
- 模块契约：`src/citeguard/live_check.py`（`docs/live.md`）
- 测试：`tests/test_live_eval.py`（7 例，全部离线）
- 实测时间：2026-11-14 01:56（Asia/Shanghai），基线 v1.7.3

## 1. 目的与边界

Live 的产品假设是：读者在浏览器里读到一句“像结论”的话，想知道有没有论文支持/反驳它。评测要回答两个可量化的问题：

1. **找得回吗**：被引文献是否出现在候选前 3 条（hit@3）？
2. **够快吗**：单次核验的 P50/P95 延迟是多少？

不回答“判断对不对”——本集没有人工 stance 金标，四档标签只用于观察输出分布和失败模式。

**页面语义（重要）**：`page_id` 指向 Live 场景里打开的公开页面（上下文页），**不是句子出处**。句子的出处是本地 `data/real_corpus` 的 PDF，出处信息单独记录在 `source_title` / `source_doi`。因此本集**不声称**任何句子出现在这 5 个页面上；页面只作为 `page_url` / `page_title` 上下文参数，且按主题与句子邻近选取，避免把被引文献直接泄漏给检索器。

## 2. 数据

### 2.1 五个真实公开页

| id | 页面 | 标题 | 许可 | 抓取时间 |
| --- | --- | --- | --- | --- |
| `arxiv-1706-03762` | <https://arxiv.org/abs/1706.03762> | Attention Is All You Need | [arXiv 非独占分发许可](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | 2026-11-14T01:50:33+08:00 |
| `arxiv-2005-11401` | <https://arxiv.org/abs/2005.11401> | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | [arXiv 非独占分发许可](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | 2026-11-14T01:50:33+08:00 |
| `arxiv-2303-08774` | <https://arxiv.org/abs/2303.08774> | GPT-4 Technical Report | [arXiv 非独占分发许可](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | 2026-11-14T01:50:33+08:00 |
| `pubmed-42698590` | <https://pubmed.ncbi.nlm.nih.gov/42698590/> | Students' experiences of using ChatGPT for English language learning: a qualitative study in a Malaysian higher education institution | [CC BY 4.0（PMC13541550）](https://pmc.ncbi.nlm.nih.gov/articles/PMC13541550/) | 2026-11-14T01:50:39+08:00 |
| `pubmed-42181435` | <https://pubmed.ncbi.nlm.nih.gov/42181435/> | Harnessing ChatGPT for Medical Education: A Narrative Review | [CC BY 4.0（PMC13198158）](https://pmc.ncbi.nlm.nih.gov/articles/PMC13198158/) | 2026-11-14T01:50:40+08:00 |

抓取方式与真实性说明：

- 3 个 arXiv abs 页面直接请求返回 HTTP 200，标题取自页面 `citation_title` 元数据，许可链接取自页面内的 `http://arxiv.org/licenses/nonexclusive-distrib/1.0/`。
- PubMed 页面直接请求返回 203（JS/反爬拦截），标题与 `cc by` 许可改由 **Europe PMC REST** 记录取得（`EXT_ID:42698590`、`EXT_ID:42181435`），并逐条打开 PMC 全文页确认 “Creative Commons Attribution License (CC BY)” 与 `https://creativecommons.org/licenses/by/4.0/`。`pages.json` 的 `fetched_via` 字段如实记录了这一点。
- 只存页面元数据，不存页面全文；评测运行时也只读候选摘要片段，不落盘摘要。

### 2.2 三十条真实中文引用句

来源是 `data/real_corpus` 的 6 篇 hanspub 开放获取中文论文（20 篇语料中选 6 篇），分布如下：

| 来源论文 | 主题 | 句数 | 默认上下文页 |
| --- | --- | --- | --- |
| `hanspub_152575.pdf` | AI 在电子商务中的文献计量综述 | 12 | `arxiv-2303-08774`（GPT-4） |
| `hanspub_152577.pdf` | 软子空间聚类 | 7 | `arxiv-1706-03762`（Transformer） |
| `hanspub_152680.pdf` | 不完整多视图聚类 | 5 | `arxiv-1706-03762` |
| `hanspub_152700.pdf` | POA 学术英语写作与 AI 反馈 | 3 | `pubmed-42698590`（ChatGPT 英语学习） |
| `hanspub_152679.pdf` | 初中物理漫画学伴与 RAG | 2 | `arxiv-2005-11401`（RAG） |
| `hanspub_152678.pdf` | 博士生课程与模式 III 知识生产 | 1 | `pubmed-42181435`（ChatGPT 医学教育） |

选句规则（全部可脚本复核，非模板造句）：

1. 从 PDF 正文抽句：`extract_text_with_meta → split_references → parse_reference_list`，把 PDF 换行拼回句子，再按 `。！？` 切句。
2. 只保留 20–220 字、含 `[n]` 或“作者(年份)”引用标记的中文完整句。
3. 引用标记展开后**必须恰好对应一条有 DOI 的参考文献**——避免“一句多引”导致来源不可判定。
4. 人工排除定义/公式/定理句（数学论文 152595 全部排除），保留可核验的结论句、方法句、综述总结句。
5. 最终 30 句长度 46–167 字，覆盖 6 篇论文、26 个不同 DOI；每篇最多 12 句，避免单篇主导。
6. 句子原样保存，不改写、不补全、不翻译。

许可边界：30 句是本地开放获取语料的**短摘录**（每篇 ≤12 句、单句 ≤167 字），仅用于评测；原 PDF 不随仓库分发。语料 manifest 未逐篇记录期刊许可，**具体再分发条款待核实**；`claims.jsonl` 只随本仓库用于内部评测，不作为可再分发的数据集发布。

### 2.3 `claims.jsonl` 字段

每行恰好 5 个字段：

```json
{"id": "live-001", "sentence": "该研究通过随机实验发现……[2]。", "source_title": "AI-Based Chatbots in Customer Service and Their Effects on User Compliance", "source_doi": "10.1007/s12525-020-00414-7", "page_id": "arxiv-2303-08774"}
```

`source_title` / `source_doi` 来自该句引用标记展开后的那一条参考文献；`page_id` 是上下文页。字段数、唯一性、DOI 形态、页面引用完整性由 `scripts/eval_live.py --check` 校验。

## 3. 四档意图覆盖

意图标签沿用 `docs/live.md`：`support` / `partial` / `contradict` / `no_evidence`。**本集不给金标**，只在文档里记录选句规则如何覆盖四类，供人工复核与后续标注。

| 意图 | 选句规则 | 本批句数 | 说明 |
| --- | --- | --- | --- |
| `support` | 句子转述来源的实证发现（“X 等(年)…发现…”），来源摘要方向一致 | 14（预期） | 综述类 152575 的 12 条 + 152679 的 2 条；摘要可得时最可能判支持 |
| `partial` | 句子只借用来源的方法/定义/框架，或只与摘要部分重合 | 14（预期） | 152577/152680 的 12 条方法描述 + 认知负荷、模式 III 理论引用 |
| `no_evidence` | 句中的数字/结论无法在来源摘要中找到，或来源摘要缺失 | 2 条疑似（152700 的 95.24%/92.06% 等百分比，引用 [26] 一篇观点型文章） | 疑似“自调查数据挂他人引用”，标 **待核实**，不冒充金标 |
| `contradict` | 句子方向与来源摘要相反，或数字/对象与来源明确不符 | **0（未确认）** | 30 句中没有可人工确认的矛盾引用；不虚构矛盾金标。补法见 §8 |

预期标签是作者按句子类型与摘要做的预判，**不是标注金标**；疑似误引只写“待核实”，不写成事实。

## 4. 指标与判定

- **hit@k**：`check_claim` 返回的 `candidates` 按模块内部顺序取前 k 条；命中判定为
  - 候选 DOI 归一化后与 `source_doi` 相同，或候选 URL 中解析出的 DOI 相同；或
  - 候选标题归一化（去标点/空白、小写）后相等，或一方包含另一方且长度 ≥20，或 `SequenceMatcher` 相似度 ≥0.88。
- **P50 / P95 延迟**：单次 `check_claim` 的墙钟耗时（含 OpenAlex/Crossref 检索），毫秒。
- **标签分布**：四档计数；非法 label 记为失败，不计入分布。
- **失败**：检查器抛异常、返回非 dict、label 非法、`candidates` 非列表；单条失败不影响整批。
- 分母固定为 30（失败也算未命中），避免“跳过难例”抬高指标。

## 5. 实测结果（2026-11-14）

命令：`PYTHONPATH=src python scripts/eval_live.py`（本机网络，未配置判定模型 API key，走规则兜底）。

| 指标 | 数值 |
| --- | --- |
| n | 30 句 / 5 页 |
| hit@1 | 0.0000 |
| **hit@3** | **0.0000** |
| 延迟 P50 | 5469.8 ms |
| 延迟 P95 | 7266.3 ms |
| 平均延迟 | 5613.6 ms（最小 4144.0，最大 7472.6） |
| `support` / `partial` / `contradict` / `no_evidence` | 0 / 1 / 0 / 29 |
| 失败 | 0 |
| 无候选 | 0 |

**结果解读（关键）**：30 句全部检索到了 5 条候选，但 29 条判 `no_evidence`、1 条 `partial`，hit@3 为 0。原因不是网络失败，而是**查询语言与被引文献语言错位**：

- 句子是中文，`_build_query` 抽出的检索词以中文块为主；OpenAlex/Crossref 对中文查询返回的是**中文文献**（例如 live-001 的候选是《AI 客服……》《人工智能服务……》等中文论文），而被引来源是英文论文（`10.1007/s12525-020-00414-7`），根本不在候选里。
- 29 条 `no_evidence` 的 reason 均为“未启用判断模型，规则回退未在候选摘要中找到与引用句关键词/数字足够重合的句子”，即**候选本身不对**，不是判断器判错。
- 对照诊断（研究者手动跑，**不是产品指标**）：把 `claim` 换成英文 `source_title` 再调用同一函数，抽查 3 条全部在**第 1 名**命中正确 DOI（`10.1007/s12525-020-00414-7`、`10.1016/j.eswa.2023.121801`、`10.1016/j.techsoc.2025.102898`）。说明检索链路本身可用，瓶颈在“中文句子 → 英文文献”的查询构造。

延迟方面，P50 5.47 s 高于 Live 交互式核验的常见预算（约 3 s）；本机为共享网络，数值只作本环境证据，不作跨环境承诺。

**结论**：Live 的“候选检索 + 摘要级判断”链路能跑通，但当前版本对“中文句子引用英文文献”这一主场景 hit@3 = 0，需双语查询扩展/标题补全后再评测；延迟也需优化。**这不是“中文语义检索天花板”的结论**，只是 30 句小样本、单一版本、单一网络环境的结果。

## 6. 结论与建议（决策）

| 项 | 决策 | 理由 |
| --- | --- | --- |
| Live 候选检索链路 | **hold（可用但不达标）** | 英文标题查询 3/3 命中第 1，说明检索器可用；中文句子路径 0/30 |
| 30 句评测集 | **adopt（作为回归集）** | 真实正文、来源可追溯、脚本可复现；小样本，只作烟雾测试 |
| 双语查询扩展 / 标题补全 | **建议下一轮实验** | 预期把中文句子的 hit@3 从 0 拉起来，且不改判断器 |
| 判定模型（LLM judge） | **hold** | 本机未配 API key，规则兜底；候选都不对时 judge 无意义 |

## 7. 复现

```bash
cd citeguard
python scripts/eval_live.py --check                # 只校验数据：5 页 / 30 句，来源可追溯
PYTHONPATH=src python scripts/eval_live.py         # 跑 30 句，写 data/live_eval/live_eval.json
PYTHONPATH=src python scripts/eval_live.py --limit 3 --out /tmp/live_preview.json
python -m pytest tests/test_live_eval.py -q        # 7 例，离线
```

- `--check` 不联网、不 import `live_check`；`live_check` 未交付时会打印“live_check 未交付，先 --check 数据”并以退出码 2 结束。
- 结果 JSON 只含 id、标签、置信度、候选数、命中排名、延迟与失败原因，不含句子全文、摘要或候选全文。

## 8. 局限与后续

1. **样本小**：5 页 / 30 句 / 6 篇来源，只能做烟雾测试与回归，不能外推总体 hit@3。
2. **无 stance 金标**：标签分布不是准确率；矛盾意图本批 0 条，后续需人工从语料中确认方向相反的引用后再补，绝不虚构。
3. **页面是上下文页**：不代表句子出现在页面上；若要测“网页正文 ↔ 句子的对应”，需要另建带页码/锚点的页面集。
4. **网络环境**：OpenAlex 无 API key、共享每日预算；PubMed 页面 203 拦截；arXiv 抓取曾瞬时超时。延迟数值只代表本机。
5. **候选上限 5**：`live_check` 固定返回前 5，hit@3 只在其内部排序上评估，不能测“扩大候选能否救回”。
6. **摘要可得性**：部分来源摘要为空（OpenAlex 未收录），会直接导致 `no_evidence`；这类句子应在下一版单独分层统计。

## 9. 文件

| 文件 | 内容 |
| --- | --- |
| `data/live_eval/pages.json` | 5 个公开页（id/url/title/fetched_at/license/license_url/fetched_via） |
| `data/live_eval/claims.jsonl` | 30 条真实中文引用句（id/sentence/source_title/source_doi/page_id） |
| `data/live_eval/live_eval.json` | 最近一次评测结果（n、hit@1/hit@3、P50/P95、标签分布、逐条记录） |
| `scripts/eval_live.py` | 校验 + 评测脚本 |
| `tests/test_live_eval.py` | 7 个离线单测（命中/未命中/空候选/异常/数据校验） |
| `docs/live_eval.md` | 本文件 |
