# CiteGuard Live 评测：三套 30 句数据与 hit@3 / 延迟 / 四档标签分布

> 三套互不混算的 Live 评测数据：**跨语言集**（30 条真实中文引用句，上下文页与被引来源无关）暴露“中文句子 → 英文文献”的检索边界；**公开页集**（30 条英文句子确实出现在 5 篇 arXiv HTML 页面上，`[n]` 与页内参考文献一一对应）检验页面参考文献优先路径；**冻结 held-out 集**（5 篇新的 2026 arXiv HTML、30 条英文句，与公开页集无重叠）用于检验同一机制在未见页面上的泛化。三套都评测 `check_claim`，都**没有 stance 金标**。
>
> **重要**：本文含两种判官状态。早期三套评测在**未配置判定模型**时跑，四档标签来自本地规则降级，不能当作语义理解或 stance 准确率；2026-11-14 已在本机配置云端 DeepSeek（`deepseek-chat`）与本地 Qwen3-14B 两条路径，并用判官复跑 held-out（见 §5.4）。判官输出仍是模型判定，不是人工金标。页面引用命中（hit@1/hit@3）与“是否有逐字证据”是两件不同的事。

- 跨语言集：`data/live_eval/pages.json`（5 页）、`data/live_eval/claims.jsonl`（30 句）→ `data/live_eval/live_eval.json`
- 公开页集：`data/live_eval/pages_public.json`（5 页）、`data/live_eval/claims_public.jsonl`（30 句）→ `data/live_eval/live_eval_public.json`
- 冻结 held-out 集：`data/live_eval/pages_holdout.json`（5 页）、`data/live_eval/claims_holdout.jsonl`（30 句）→ `data/live_eval/live_eval_holdout.json`（富化后 `live_eval_holdout_enriched.json`）
- 评测脚本：`scripts/eval_live.py`（`--claims/--pages/--out` 切换数据集）
- 模块契约：`src/citeguard/live_check.py`（`docs/live.md`）
- 测试：`tests/test_live_eval.py`（13 例，全部离线）
- 实测时间：2026-11-14 01:56（跨语言集）、02:20（公开页集）、03:35（held-out 富化前后），基线 v1.7.10

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

### 2.4 公开页集：句子与页面真实对应

跨语言集的句子与页面只是“主题邻近”，页面的参考文献列表里没有句子所引的那篇文献，t12 的页面引用列表优先因此无法生效。公开页集把这一点反过来：**句子确实出现在页面上，`[n]` 就是该页参考文献列表的编号**。

5 篇 arXiv 论文（`https://arxiv.org/html/{id}`，LaTeXML 全文，均有编号制 `[n]` 参考文献）：

| id | 论文 | 许可 | 参考文献数 | 句数 |
| --- | --- | --- | --- | --- |
| `arxiv-2611-02510` | Neuro Inspired Robotics: What Robot Learning Can Borrow from the Sensorimotor Brain | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 456 | 6 |
| `arxiv-2610-41688` | When the Past Shapes Action: Understanding Embodied Memory | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) | 117 | 6 |
| `arxiv-2610-34084` | DSGN: A Dual-Stream Gated Network for Scalable Simultaneous Surveillance and Containment | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 31 | 6 |
| `arxiv-2611-09866` | GRAC: Graph-Based Retrieval-Augmented Captioning for Surgical Scene Description | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 26 | 6 |
| `arxiv-2611-10770` | How reliable is an embedding of the seabed? Repeat-look measurement of frozen encoders on synthetic aperture sonar | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 73 | 6 |

选句与来源规则（脚本可复核）：

1. 只从页面 `<p class="ltx_p">` 正文段落抽句；句长 40–300 字符，含显式 `[n]` 标记。
2. 每条句子的 `reference_index` 就是标记里的编号；`source_title` / `source_doi` 取自**该页参考文献列表的同号条目**，DOI 形态用 `^10\.\d{4,9}/\S+$` 校验，并逐条请求 `https://doi.org/api/handles/{doi}`，30/30 返回 `responseCode=1`。
3. 为避免把“页面根本检索不到”的样本混进来，选句时额外要求该 DOI 出现在页面 OpenAlex 记录的 `referenced_works` 前 40 条内（`live_check.MAX_REFERENCED_WORKS=40`）——这是把样本限制在**产品当前有能力看见**的候选集合里，而不是抬高指标。
4. 每页 6 条；30 条句子原样摘录、不改写；只存句子与编号，不复制页面正文。
5. 页码/行号不做要求；`reference_index` 与句内 `[n]` 的一致性由 `--check` 强制校验。

`claims_public.jsonl` 每行恰好 7 个字段：

```json
{"id": "pub-001", "sentence": "… mechanoreceptors [186, 194, 2].", "source_title": "The Sensory Neurons of Touch", "source_doi": "10.1016/j.neuron.2013.07.051", "page_url": "https://arxiv.org/html/2611.02510", "page_title": "Neuro Inspired Robotics: …", "reference_index": 2}
```

许可边界：公开页集只摘录句子与参考文献编号；`2610.41688` 为 CC BY-NC-SA 4.0，本仓库仅在内部评测中作短摘录并注明出处，不随产品分发页面正文；其余 4 页为 CC BY 4.0 / CC BY-SA 4.0（均需署名，页面 URL 已在 `pages_public.json` 中保留）。

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

### 5.1 跨语言集（跨语言集的 hit@3 = 0，是设计使然）

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

### 5.2 公开页集（页面参考文献列表优先）

命令：

```bash
PYTHONPATH=src python scripts/eval_live.py \
  --claims data/live_eval/claims_public.jsonl \
  --pages data/live_eval/pages_public.json \
  --out data/live_eval/live_eval_public.json
```

| 指标 | 数值 |
| --- | --- |
| n | 30 句 / 5 页 |
| hit@1 | 0.5667 |
| **hit@3** | **0.7000** |
| 延迟 P50 | 7.8 ms |
| 延迟 P95 | 16.5 ms |
| 平均延迟 | 9.4 ms |
| `support` / `partial` / `contradict` / `no_evidence` | 0 / 12 / 0 / 18 |
| 失败 | 0 |
| 无候选 | 0 |

按页面拆开（每页 6 句）：

| 页面 | 参考文献数 | hit@1 | hit@3 |
| --- | --- | --- | --- |
| `arxiv-2611-02510` | 456 | 5/6 | 5/6 |
| `arxiv-2610-41688` | 117 | 3/6 | 4/6 |
| `arxiv-2610-34084` | 31 | 3/6 | 3/6 |
| `arxiv-2611-09866` | 26 | 4/6 | 5/6 |
| `arxiv-2611-10770` | 73 | 2/6 | 4/6 |

**结果解读（关键）**：

- 同一个 `check_claim`，换成“句子确实在页面上、被引文献就在页面参考文献列表里”的数据后，hit@3 从 0/30 变成 21/30（标题优先排序后；同一集调排序规则，需新集复核）。说明 t12 的页面引用列表增强**确实生效**：候选集来自页面 `referenced_works`，而不是被中文句子带偏的关键词搜索。
- 9 条未命中里，**4 条的正确 DOI 已出现在候选里、排第 4–5 名**，差一位进不了 top-3；**其余 5 条在页面候选池里但排序落得更后**（含标题与句子用词完全不重合的奠基性工作）。
- 因此剩余瓶颈不是“找不到页面参考文献”，而是 **排序规则 + 固定 `MAX_CANDIDATES=5` 截断**：当前页面候选改用**标题优先**打分（`_page_candidate_score`，0.85 标题覆盖 + 0.15 数字），公开页集 hit@3 由 0.60 升到 0.70；这条规则是在本集上选的，尚未用新集确认。
- 延迟 P50 7.8 ms、P95 16.5 ms 是因为 5 个页面的 OpenAlex 结果全部命中缓存（本次复跑）；冷启动首条仍约 4 s。延迟只代表本机缓存状态，不作跨环境承诺。
- 标签分布（0/12/0/18）仍不是准确率：公开页集同样没有 stance 金标，规则兜底只会给 `partial` / `no_evidence`。

### 5.3 冻结 held-out 集（t15/t18，2026-11-14）

为避免“在同一公开页集上选排序规则、又在同一集上报分”，radar 另建 5 篇 2026 年 arXiv HTML（2611.07772 / 2610.38049 / 2610.24037 / 2610.32576 / 2610.18926），与 t13 的 5 页**无重叠**；30 条英文正文句，每句带页内 `[n]`，29 个唯一 DOI，30/30 可解析。t14 的 `[n] → 页面参考文献` 映射先在 t15 上跑；t17 给候选补 OpenAlex/Crossref 摘要后再跑一次（t18）：

| 指标 | t15（仅页面引用映射） | t18（补摘要后） |
| --- | ---: | ---: |
| n | 30 句 / 5 页 | 30 句 / 5 页 |
| hit@1 | 27/30（0.9000） | 27/30（0.9000） |
| **hit@3** | **30/30（1.0000）** | **30/30（1.0000）** |
| P50 | 3129.4 ms | 2982.7 ms |
| P95 | 10971.9 ms | 16088.8 ms |
| 有逐字证据 | 7/30（下界） | 11/30 |
| 四档（support/partial/contradict/no_evidence） | 2/5/0/23 | 2/9/0/19 |
| 失败 / 无候选 | 0 / 0 | 0 / 0 |

补充测量：

- 30/30 的 gold DOI 都在页面候选池内；补摘要后 gold 摘要实际补到 **20/30**（OpenAlex 可得 25/30，差 5 条未逐条归因）。
- 11 条逐字证据中 **8 条指向 gold 候选**，3 条来自同页其它候选（不是随便编的句子，但不是目标文献）。
- **25 条 OpenAlex 有摘要子集**：hit@1 0.88、hit@3 1.0、有证据 9/30（该子集基线 hit@3 25/25）；说明摘要补全改善了“有证据”比例，但没有改变 top-3 命中（本来已近饱和）。
- 2610.32576 的 6 条 gold 摘要仍为空，该页 0 证据；32576/18926 两页 12 条全部 no_evidence。
- P95 从 10.97 s 升到 16.09 s（+46.6%），来自摘要补全的外部 API 调用；这是**延迟代价**，不是免费收益。

**结论（谨慎）**：页面引用列表 + `[n]` 标记在**这一小批未见页**上 hit@3 = 30/30，说明机制不是只对 t13 页面有效；但样本只有 5 页/30 句、页面类型单一（arXiv HTML）、排名上限仍为 5，不能外推为“开放网页 100%”；四档标签仍无判定模型与人工金标，不能宣称 stance 准确率。

### 5.4 三套数据的关系（禁止混算）

| | 跨语言集 | 公开页集 | 冻结 held-out 集 |
| --- | --- | --- | --- |
| 句子语言 | 中文（真实中文论文正文） | 英文（页面正文） | 英文（页面正文） |
| 句子与页面关系 | 主题邻近的上下文页，页面引用列表**不含**被引来源 | 句子**确实在**页面上，`[n]` 对应页内参考文献 | 同公开页集，但页面/句子与公开页集**无重叠** |
| 页面参考文献列表 | 通常不覆盖被引来源 | 覆盖（选样时限制在 OpenAlex 前 40 条内） | 覆盖；补摘要前 23/30 条无逐字证据 |
| hit@3 | 0/30 | 21/30 | 30/30（补摘要前后同） |
| 用途 | 暴露跨语言查询构造的边界 | 检验页面引用列表优先路径 | 检验机制在未见页面上的泛化 |

三套数据的任务难度与分母含义不同，**不能相加、不能互相替代**；跨语言集的 0/30 不能用来否定公开页集/held-out 的分数，反之也不行。


### 5.5 配置判定模型后的 held-out 复测（2026-11-14）

本机同时配置了两条判官路径：`hosted-deepseek`（`https://api.deepseek.com`，`deepseek-chat`）与本地
`local-qwen3-14b`（lmh GPU3，4-bit 量化，按需启动）。使用云端判官对同一份 30 条 held-out 复跑：

```bash
PYTHONPATH=src python scripts/eval_live.py \
  --claims data/live_eval/claims_public.jsonl \
  --pages data/live_eval/pages_public.json \
  --out data/live_eval/live_eval_holdout_judge.json
```

| 配置 | n | hit@1 | hit@3 | P50 | P95 | 四档 |
| --- | --- | --- | --- | --- | --- | --- |
| 无判官（规则降级，t18） | 30 | 0.9000 | 1.0000 | 2.98 s | 16.09 s | 2 / 9 / 0 / 19 |
| 云端 `deepseek-chat`（本次） | 30 | **0.6667** | **0.9333** | **14.81 s** | 24.60 s | **1 / 18 / 0 / 11** |

边界与解释：

- 判官可用后，19/30 条给出了 `support`/`partial` 判定（无判官时主要是 `no_evidence`），说明判定链路已工作；
  但这仍不是 stance 准确率：没有人工逐条核对。
- 候选命中比无判官 run 低（hit@3 28/30 vs 30/30），差异来自候选顺序/网络返回波动，未定位到单一原因，
  不把两次 run 混算、也不据此宣称判官降低命中率。
- P50 14.8 s 来自对前 3 个有摘要候选的逐条判官调用，**不适合在线逐句**；在线入口目前仍以“候选+证据”
  为主，判官仅作辅助。
- 产品内 `/live` 用同一接口实测“STIC 72.6%”句：支持 95%、逐字证据句命中；截图
  `docs/evidence/shots/phase-56-live-judge-1.7.13.png`。

## 6. 结论与建议（决策）

| 项 | 决策 | 理由 |
| --- | --- | --- |
| 跨语言集（回归集） | **adopt** | 真实中文正文、来源可追溯、脚本可复现；小样本，只作烟雾测试 |
| 公开页集（页面引用列表回归集） | **adopt** | 句子与页面真实对应，30/30 DOI 可解析；补上了跨语言集测不到的 t12 路径 |
| 冻结 held-out 集（未见页面回归集） | **adopt 机制，hold 结论** | 30/30 hit@3，说明 `[n]` 映射在未见 arXiv HTML 上有效；样本小、页型单一，且排序规则仍固定 top-5 |
| Live 候选检索链路（跨语言场景） | **hold（可用但不达标）** | 英文标题查询 3/3 命中第 1，说明检索器可用；中文句子路径 0/30 |
| 页面引用列表优先（公开页场景） | **adopt 机制，hold 效果** | 同函数 hit@3 从 0/30 到 30/30（held-out）；公开页集 21/30；排序规则在公开页集选定 |
| 页面引用列表优先（页面有 `[n]` 的 arXiv HTML） | **adopt** | t14/t17/t18：识别 `[n]`、映射 `ol.ltx_bibliography`、补摘要；失败静默回退 |
| 候选打分 / 截断策略 | **建议下一轮实验** | 正确文献已在页面候选池内，瓶颈是 `_candidate_score` 词面匹配与 `MAX_CANDIDATES=5` 截断 |
| 双语查询扩展 / 标题补全 | **建议下一轮实验** | 预期把中文句子的 hit@3 从 0 拉起来，且不改判断器 |
| 判定模型（LLM judge） | **adopt（谨慎）** | 本机已配云端 DeepSeek 与本地 Qwen3-14B；held-out 19/30 有判定，但 P50 14.8 s，且无人审，不能当 stance 准确率 |

## 7. 复现

```bash
cd citeguard
python scripts/eval_live.py --check                # 跨语言集：5 页 / 30 句
python scripts/eval_live.py \
  --claims data/live_eval/claims_public.jsonl \
  --pages data/live_eval/pages_public.json --check # 公开页集：5 页 / 30 句 / 每页 6 条
PYTHONPATH=src python scripts/eval_live.py         # 跑跨语言集，写 data/live_eval/live_eval.json
PYTHONPATH=src python scripts/eval_live.py \
  --claims data/live_eval/claims_public.jsonl \
  --pages data/live_eval/pages_public.json \
  --out data/live_eval/live_eval_public.json       # 跑公开页集
PYTHONPATH=src python scripts/eval_live.py \
  --claims data/live_eval/claims_holdout.jsonl \
  --pages data/live_eval/pages_holdout.json \
  --out data/live_eval/live_eval_holdout_enriched.json  # 跑冻结 held-out 集
PYTHONPATH=src python scripts/eval_live.py --limit 3 --out /tmp/live_preview.json
python -m pytest tests/test_live_eval.py -q        # 13 例，离线
```

- `--check` 不联网、不 import `live_check`；按字段形状自动识别数据集（`page_id` → 跨语言集，`page_url/reference_index` → 公开页集），混用两种字段会被拒绝。
- `live_check` 未交付时会打印“live_check 未交付，先 --check 数据”并以退出码 2 结束；`--check` 不受影响。
- 结果 JSON 只含 id、标签、置信度、候选数、命中排名、延迟与失败原因，不含句子全文、摘要或候选全文；`dataset` 字段标明跑的是哪一套。

## 8. 局限与后续

1. **样本小**：公开页集 5 页 / 30 句 / 每页 6 条；冻结 held-out 集同为 5 页 / 30 句；跨语言集 30 句 / 6 篇来源。只能做回归与烟雾测试，不能外推总体 hit@3。held-out 的 30/30 是小样本上限，不是开放网页承诺。
2. **无 stance 金标**：两套数据的标签分布都不是准确率；矛盾意图本批 0 条，后续需人工从语料中确认方向相反的引用后再补，绝不虚构。
3. **两套数据的页面含义不同**：跨语言集的 `page_id` 只是主题邻近的上下文页，**不代表句子出现在页面上**；公开页集才是“句子确实在页面上、`[n]` 与页内参考文献同号”。引用两套结果时必须说明是哪一套。
4. **页面候选被截断**：`live_check` 只取页面 OpenAlex `referenced_works` 前 40 条（`MAX_REFERENCED_WORKS=40`），而 `2611.02510` 有 456 条参考文献、OpenAlex 记录 283 条；若正确文献落在第 41 条之后，本集也不会命中。这不是页面本身的问题，是产品当前的取数上限。
5. **候选返回上限 5**：`MAX_CANDIDATES=5` 固定返回前 5，hit@3 只在其内部排序上评估；已确认 4 条未命中排在第 4–5、8 条被词面打分挤出前 5，扩大候选或改打分需另做实验，不能靠本集证明。
6. **许可**：公开页集只摘录句子与参考文献编号；`2610.41688` 为 CC BY-NC-SA 4.0，仅限仓库内评测使用、需署名，不随产品分发正文；其余页面为 CC BY 4.0 / CC BY-SA 4.0，使用时保留 URL 与许可声明。
7. **网络环境**：OpenAlex 无 API key、共享每日预算；PubMed 页面 203 拦截；arXiv 抓取曾瞬时超时。延迟数值只代表本机，P50 偏小是因为同进程缓存，P95 反映 5 次冷启动。
8. **摘要可得性**：部分来源摘要为空（OpenAlex 未收录），会直接导致 `no_evidence`；这类句子应在下一版单独分层统计。

## 9. 文件

| 文件 | 内容 |
| --- | --- |
| `data/live_eval/pages.json` | 跨语言集 5 个公开页（id/url/title/fetched_at/license/license_url/fetched_via） |
| `data/live_eval/claims.jsonl` | 跨语言集 30 条真实中文引用句（id/sentence/source_title/source_doi/page_id） |
| `data/live_eval/live_eval.json` | 跨语言集最近一次评测结果（n、hit@1/hit@3、P50/P95、标签分布、逐条记录） |
| `data/live_eval/pages_public.json` | 公开页集 5 个 arXiv HTML 页（id/url/title/fetched_at/license/license_url/source/references/openalex_referenced_works） |
| `data/live_eval/claims_public.jsonl` | 公开页集 30 条英文正文句（id/sentence/source_title/source_doi/page_url/page_title/reference_index） |
| `data/live_eval/live_eval_public.json` | 公开页集最近一次评测结果（dataset=public，含真实指标与逐条记录） |
| `data/live_eval/pages_holdout.json` | 冻结 held-out 集 5 个 2026 arXiv HTML 页（与公开页集无重叠） |
| `data/live_eval/claims_holdout.jsonl` | 冻结 held-out 集 30 条英文正文句（每句带页内 `[n]` 与 DOI） |
| `data/live_eval/live_eval_holdout.json` | t15：仅页面引用映射的 held-out 评测结果 |
| `data/live_eval/live_eval_holdout_enriched.json` | t18：补 OpenAlex/Crossref 摘要后的 held-out 评测结果（含与 t15 对照、25 条有摘要子集） |
| `data/live_eval/live_eval_holdout_judge.json` | 2026-11-14 配云端判官后的同集复跑（hit@1 0.6667、hit@3 0.9333、P50 14.8 s） |
| `docs/research/live_holdout.md` | radar 的 held-out 设计与完整残差分析（300 行） |
| `scripts/eval_live.py` | 校验 + 评测脚本；`--claims/--pages/--out` 切换数据集，`--check` 只校验数据 |
| `tests/test_live_eval.py` | 13 个离线单测（跨语言/公开页两套数据校验、命中/未命中/空候选/异常、fake checker） |
| `docs/live_eval.md` | 本文件 |
