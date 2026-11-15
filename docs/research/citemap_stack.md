# CiteMap 复用尽调：schema → 全文证据 → 关系图的最短路径

> 调研日期：2026-11-16  
> 范围：只做技术尽调，不改产品代码；结论尽量区分“仓库里已验证”“公开资料声称”“我们的估算”。  
> 一句话结论：**CiteMap 可以先不重造解析/对齐，用仓库现有 `pdf_extract` + `refs_layout` + `reference_parser` + `citation_anchor` + `citemap_verify` 做出 10 篇 / 20 条的全全文证据 demo；GROBID/Anystyle 等不是当前瓶颈。真正不满足的是“中文论文级 claim→全文证据”的公开数据与许可，必须自建 10 篇人工金标，或明确缩小到英文/摘要范围。**

---

## 0. 结论先行

### 0.1 能直接复用的部分

| 能力 | 仓库现状 | 判断 |
| --- | --- | --- |
| PDF 文本 | `src/citeguard/pdf_extract.py`，pypdf / pdfplumber / pypdfium2 多后端 | 直接复用 |
| 参考文献列表（PDF 版式） | `src/citeguard/refs_layout.py`，按悬挂缩进/分栏抽条目，pypdfium2，无 PyMuPDF | 直接复用，作为 `reference_parser` 的回退 |
| 参考文献字符串解析 | `src/citeguard/reference_parser.py`，GB/T 7714、APA、ACL 等，中英文 | 直接复用 |
| 正文引用锚点 | `src/citeguard/citation_anchor.py`，`[12]`、`[3-5]`、`文献[12]`、作者-年、脚注 | 直接复用，这是最容易被低估的资产 |
| 引用句→参考文献映射 | `support.build_claims(body, intext, refs)`；`pipeline._judge_support` 已按参考文献逐条挂支持度 | 直接复用/小改 |
| 全文抓取 | `scripts/fetch_citemap_fulltext.py`，OpenAlex OA / Europe PMC JATS / PMC HTML / arXiv；PDF 解析后删除，只缓存文本 | 直接复用；当前 25/30 篇可取得全文 |
| 句子检索 + 判官 | `citemap_verify.split_sentences/rank_sentences/verify_claim_in_text`；引文必须逐字命中候选句 | 直接复用；已有 258 个组合的实测 |
| 向量检索（可选） | `src/citeguard/embeddings.py`，OpenAI-compatible endpoint，默认 `BAAI/bge-m3`，无内置权重 | 可选复用；不配 endpoint 就不启用，不影响离线 |
| 证据 schema | `src/citeguard/evidence_map.py` 已有 paper/claim/evidence/method/sample/stance/gap | 可承载全文证据；只差“引用来源/页码范围”等可选字段 |
| 前端 | `web/templates/citemap.html`、`citemap.js`、`citemap.css` 已有主题页、论文列表、证据卡 | 可扩展实线/虚线状态与关系图 |

### 0.2 明确“不满足，需换方案”的部分

**不存在可直接拿来用的“中文论文 claim → 被引论文全文证据”公开数据集。**

- SciFact 是英文摘要级 claim/evidence（1,409 claims / 5,183 abstracts），不是中文、不是全文。
- CFEVER 是中文维基百科 claim（30,012 条），不是论文、没有 DOI/全文。
- LongCite-45k 是长上下文问答里的句子级引用（44,600 条，中英），不是“支持/反驳”金标。
- RAGTruth 是 RAG 回答的幻觉片段（2,965 个源/17,790 条回答），不是论文 claim。
- SciCite/ACL-ARC 是引用意图，不是“这篇被引论文是否支持这句话”；CiteWorth 是“这句话该不该引用”。

所以：**做公开的“中文论文全文证据”基准，数据与许可都不满足，必须换方案**——要么自建 10 篇 / 20 条人工金标（只在本仓库内部评测、不分发全文），要么把产品范围诚实缩到英文 arXiv/摘要级。

### 0.3 推荐路线（先给结论）

**推荐“轻架构 B”**：现有仓库管线 + 可选 BGE-M3 + JSON 关系图投影 + 10 篇人工金标；**6–8 人日**可做出可演示版本。  
**不推荐“重架构 A”**：GROBID 全量结构化 + 向量库 + 图数据库 + 中文模型重训；英文可做，中文要额外标注/重训，**12–18 人日**且不确定性高，3 周赛程不划算。

---

## 1. 仓库现状：最短路径已经铺了一半

### 1.1 已有模块与实测

| 模块/脚本 | 关键事实 | 证据 |
| --- | --- | --- |
| `src/citeguard/citation_anchor.py` | `Citation(key, style, ref_numbers, sentence, start, end)`；支持数字、中文“文献[n]”、作者-年、中文作者-年、脚注；`_expand_numbers` 展开 `[3-5]`；单条最多 300 个编号，句子截断 320 字符 | 31 个相关测试通过（含 anchor/layout） |
| `src/citeguard/refs_layout.py` | `extract_reference_entries(pdf_path, max_pages=12)`：按字符框聚行、检测分栏、找 `references/bibliography/参考文献` 标题、按悬挂缩进切条目；`recover_title` 修复 URL/DOI 开头的坏标题 | `tests/test_refs_layout.py`、`tests/test_refs_layout_pdfium.py` |
| `src/citeguard/reference_parser.py` | `parse_reference`, `parse_reference_list`, `parse_intext_citations`；GB/T 7714、APA、ACL 等；纯规则，无模型 | `tests/test_reference_parser.py` |
| `src/citeguard/pipeline.py` | `split_references` → `parse_reference_list`；若 PDF 且条目少，用 `refs_layout` 候选，仅当标题健康度更好才替换；`build_claims` 把引用句挂到 reference index；`_judge_support` 用被引论文摘要判支持度 | 代码路径已存在；摘要级，不是全文 |
| `scripts/fetch_citemap_fulltext.py` | 30 篇固定论文中 25 篇取得 OA 全文；来源 OpenAlex OA、Europe PMC `fullTextXML`、PMC HTML、arXiv；PDF 下载到临时文件，解析后删除，文本缓存到 `data/cache/citemap_fulltext/` | `docs/citemap_atomic_fulltext.md` |
| `scripts/eval_citemap_atomic_fulltext.py` | 21 条原子断言 × 25 篇全文 = 258 组合；`full/partial/none/error` | 输出 `data/experiments/citemap_atomic_fulltext_v3.json` |
| `src/citeguard/citemap_verify.py` | 切句、词面重合排序、可选翻译查询；判官必须逐字引用候选句，引用不在候选句里就降级/丢弃 | `tests/test_citemap_verify.py` 5 个测试通过 |

### 1.2 已有实测数字（不是估算）

来自 `data/experiments/citemap_atomic_fulltext_v3_summary.json` 与 `docs/citemap_atomic_fulltext.md`：

| 指标 | 数值 |
| --- | --- |
| 全文覆盖 | 25 / 30 篇 |
| 断言 × 论文组合 | 258 |
| full / partial / none / error | 10 / 15 / 233 / 0 |
| full 覆盖率 | 3.9% |
| full+partial 覆盖率 | 9.7% |
| 人工正例格（有人工判定且该论文有本地全文） | 7 |
| 完整支持命中 | 5/7（71.4%） |
| 支持证据命中（full+partial） | 6/7（85.7%） |

边界必须一起读：21 条原子断言尚未逐条人工确认；25/30 全文、7 个人工正例，样本很小；判官是单模型；引用逐字校验只防“编句子”，不防“句子真实但推断错误”。

### 1.3 引用锚点覆盖（不是准确率）

来自 `data/experiments/citation_anchor_real.json`：

| 指标 | 数值 |
| --- | --- |
| 论文数 | 22 |
| 有引用的论文 | 21（95.5%） |
| 参考文献条目 | 529 |
| 正文引用 | 543 |
| 被正文引用到的条目 | 318（60.1%） |
| 自洽率（同一引用在正文/参考文献两侧能对上） | 486/543 = 89.5% |

注意：这是“自洽率”，**不是人工标注准确率**；`auto_check_note` 已写明。它能说明“引用锚点可跑”，不能说明“每条都抽对”。

### 1.4 当前真正的缺口

1. **引用句 → 被引论文全文** 还没有连起来：`pipeline` 把引用句挂到参考文献，再用 **被引论文摘要** 判支持度；`fetch_citemap_fulltext` 抓的是 **CiteMap 主题论文** 的全文，不是“被引论文”的全文。
2. **证据不是全文 quote**：`evidence_map` 的 10 条人工示例是摘要级 quote；`citemap_atomic_fulltext` 是实验脚本，不是产品 UI 的稳定数据层。
3. **关系图没有投影**：schema 有 `evidence.stance` 和 `gap`，但没有把 paper/claim/evidence/gap 变成图节点/边的 API 或前端。
4. **中文被引论文全文** 的许可/可获取性不稳定；不能把版权不明 PDF 提交进仓库。

这四点都不需要重写解析器，主要是“胶水 + 评测 + UI”。

---

## 2. 外部组件尽调

### 2.1 参考文献 / 全文解析器

| 工具 | 版本/许可 | 输入→输出 | 中文/英文 | 部署成本 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **GROBID** | 0.9.1（2026-08-04），Apache-2.0 | PDF → TEI XML（header/正文/参考文献/引文） | 英文/欧洲语言强；默认模型对中文期刊不稳，需自行标注/重训（社区经验：每个模型约 100 篇标注；有论文用 250 篇台湾图书馆学文章） | Java + Docker，约 2–4 GB RAM；单篇约 0.5–2 s（估算） | 英文可选；中文 demo 不值得接 |
| **CERMINE** | 1.13（2017-04-28），AGPL-3.0 | PDF → 元数据/正文/参考文献 | born-digital，英文为主；中文弱 | Java，约 1–2 GB；老项目，维护少 | AGPL + 老，排除 |
| **refextract** | 0.2.6（2025-04-07），GPL-2.0 | PDF/URL/纯文本 → 参考文献字符串 | HEP/INSPIRE 词典驱动；中文弱 | Python，轻；约 0.2–0.5 s/篇（估算） | GPL copyleft，且领域偏，排除 |
| **Anystyle** | v1.5.0（tag，2026-11-16 查），BSD-2-Clause（GitHub API 显示 Other/NOASSERTION，LICENSE 文本是 BSD-2） | 纯文本参考文献 → 结构化字段 | 官方明确只支持 Latin/Cyrillic，不支持中文/日文/阿拉伯文/印度文字 | Ruby gem，轻；PDF 需先 pdftotext | 中文不可用，排除 |
| **仓库现有** `refs_layout` + `reference_parser` | 项目内代码；依赖 pypdfium2（BSD-3/Apache-2.0 兼容） | PDF/文本 → 条目字符串 → Reference | 中英文都覆盖；规则法 | 0 新增服务；单篇约 1–3 s | **推荐** |

补充：

- GROBID 不是“装上就能中文学术 PDF”：它的默认 CRF/DeLFT 模型主要按英文/欧洲语言训练，中文期刊的标题、作者、参考文献切分需要重新标注；`pdfalto` 能出坐标，但结构模型仍要训练。
- Anystyle 的 README/文档明确“not suitable for Chinese, Japanese, Arabic, or Indian scripts”；中文引用串直接不适用。
- refextract 的 GPL-2.0 对“闭源分发/商业化”不友好；即使只做内部工具，也会给许可审查添麻烦。
- CERMINE 的 AGPL-3.0 + 2017 年后基本不维护，不适合新产品依赖。

### 2.2 引用上下文 / 引用意图数据：能不能校准“相关 ≠ 支持”？

| 数据集 | 规模 | 标签 | 许可 | 能否校准“相关≠支持” | 建议 |
| --- | --- | --- | --- | --- | --- |
| **SciCite** | 10,969 条（8,194/916/1,859） | method / background / result | 仓库 Apache-2.0；HF 数据集卡 license unknown | **部分**：`result` 可当候选支持；`method/background` 是“相关但通常不是证据”。**没有 contradict**，不能单独校准四档 | 内部评测/意图分类，不分发 |
| **ACL-ARC** | 1,943 条引用上下文 | background / motivation / uses / extends / compare-contrast / future（6 类） | 数据集包内无 LICENSE；源自 ACL Anthology，许可未声明 | **部分**：`uses/extends/compare` 是候选证据；`background/motivation/future` 通常不是支持。**没有 support/contradict 金标** | 研究/内部评测，不分发 |
| **CiteWorth** | 1,181,793 句（945,426/118,182/118,185；31.76% cite-worthy） | cite-worthy / non-cite-worthy（二分类） | 数据 HF 卡 CC-BY-NC-4.0；代码 MIT | **不能**：它判断“这句话该不该引用”，不判断“引用是否支持”。可用于“哪些句子值得进入证据候选” | 仅研究/评测；NC 不进商业产品 |
| **SciFact** | 1,409 claims / 5,183 abstracts | SUPPORT / REFUTE / NOT_ENOUGH_INFO | 论文/数据卡口径 claims CC BY 4.0、abstracts ODC-By 1.0；HF 数据集卡另标 cc-by-nc-2.0，仓库 NOASSERTION | **能校准 stance**，但是英文摘要级、无引用上下文 | 判官校准/回归测试；使用前逐项确认许可 |
| **CFEVER** | 30,012 条中文 claim | Supports / Refutes / Not Enough Info | 标注 Apache-2.0；claim 文本来自中文维基（Wikipedia Copyright Policy，署名/相同方式共享） | **能校准中文 stance**，但不是论文、无 DOI/全文 | 中文判官校准；不分发维基文本 |
| **LongCite-45k** | 44,600 条长上下文 QA | 句子级引用（citation sentences） | Apache-2.0 | **不能**直接校准支持/反驳；能校准“引用是否落到正确句子” | 引用召回/引用粒度研究 |
| **RAGTruth** | 2,965 个源 / 17,790 条回答；7,664 条幻觉回答，14,289 个 span | 回答/词级幻觉 span | MIT | **不能**：不是论文 claim→证据 | 引用逐字校验/幻觉检测的负例 |

结论：

1. **SciCite/ACL-ARC 只能把“相关”拆成“方法/背景/使用/扩展”等意图，不能直接给出 support/contradict。** 它们适合做“候选门禁”：`method/background/motivation/future` 默认不进入证据，`result/uses/extends/compare` 才进入判官；但最终仍要判官 + 人工。
2. **SciFact/CFEVER 才能校准 stance**，但一个英文摘要、一个中文维基，**不能拼成同一个“论文全文”测试集**。
3. 因此“related≠support”的产品规则应是：**意图门禁 + stance 判官 + 逐字引用 + 人工复核**，不能只靠一个引用意图模型。

### 2.3 断言-证据数据：同集 harness 可行性

| 数据集 | 字段 | 语言/粒度 | 许可 | 能否直接做 CiteMap 同集 harness |
| --- | --- | --- | --- | --- |
| SciFact | claim, cited abstract, evidence sentence, label | 英文/摘要 | 论文/数据卡口径 claims CC BY 4.0、abstracts ODC-By 1.0；HF 卡另标 cc-by-nc-2.0，仓库 NOASSERTION | **可以做摘要级 harness**：claim→evidence 句→SUPPORT/REFUTE/NEI；但无全文、无引用上下文 |
| CFEVER | claim, evidence, label | 中文/维基 | 标注 Apache-2.0；文本维基 | **可做中文 stance harness**：claim→evidence 句；但不是论文、无 DOI/全文 |
| LongCite-45k | 长上下文、问题、答案、句子级引用 | 中英/长文本 | Apache-2.0 | **可做引用召回 harness**：答案句是否引用正确句子；不是 claim 支持/反驳 |
| RAGTruth | 回答、源文本、幻觉 span | 英文/回答 | MIT | **可做 quote grounding/幻觉负例**：引用句是否真实存在；不是论文 claim |

**同集不可行**：四套数据的任务、语言、粒度、标签都不同，不能合成一个“CiteMap 通用 benchmark”。可行的做法是分开跑：

- **SciFact 摘要级**：校准判官对 SUPPORT/REFUTE/NEI 的基本能力；
- **CFEVER 中文**：校准中文 claim/evidence 的判官；
- **LongCite**：校准引用句召回；
- **RAGTruth**：校准“引用句必须逐字出现”的负例；
- **10 篇 / 20 条人工金标**：唯一能同时覆盖“被引论文全文 + 中文 claim + 真实引用上下文”的评测，但只能内部使用。

### 2.4 检索 / 对齐模型

| 模型/组件 | 规模/许可 | 适合什么 | 成本（估算） | 是否需要 |
| --- | --- | --- | --- | --- |
| **BGE-M3** | 567M，约 2.27 GB，MIT，100+ 语言，8192 tokens | 中英跨语言、句子/段落检索；把中文 claim 和英文全文句子放同一向量空间 | CPU 可跑；20 条 claim + 250 篇全文段落，首次索引约数分钟；单 query 约几十毫秒–数百毫秒（视机器） | **可选**：词面检索不够时加；不配 endpoint 就退回 `rank_sentences` |
| **SPECTER2** | 约 110M，Apache-2.0，英文科学论文 | 论文级相似度/推荐；不是句子级 | 轻量；但英文、文档级 | **不需要**：CiteMap 要的是句子证据，不是论文向量 |
| **BAAI/bge-reranker-v2-m3** | 约 568M，约 2.27 GB，MIT，cross-encoder | 对 top-50 候选句精排 | CPU 较慢；20 claims × 50 句约数分钟 | **可选**：只在候选多、精度不够时加；MVP 不必 |
| 仓库 `rank_sentences` | 无模型，词面重合 + 可选翻译查询 | 20 条 claim × 10 篇全文足够做基线 | 几乎为零 | **先用这个** |

判断：

- **句子级检索是必须的**：证据必须是原文句，摘要/段落级无法逐字引用；`citemap_verify` 已经按句切分并强制 quote 命中。
- 对 10 篇 / 20 条，`rank_sentences` 的词面重合 + 一次翻译查询已经够跑通；BGE-M3 是“中文 claim vs 英文全文”召回下降时的增强，不是前置依赖。
- SPECTER2 是文档级，不解决句子证据；不建议为它增加依赖。
- cross-encoder 的收益要等有 20 条人工金标后才能判断；没有金标就上 reranker，属于“用工具掩盖评测缺失”。

### 2.5 许可证红线（必须在材料里写清）

| 资产 | 许可 | 能不能进仓库/产品 | 备注 |
| --- | --- | --- | --- |
| SciCite 数据 | HF `unknown`；仓库 Apache-2.0 | **不能分发数据** | 仅内部评测；仓库代码许可不等于数据许可 |
| ACL-ARC 数据 | 未声明；包内无 LICENSE | **不能分发** | 源自 ACL Anthology；仅研究 |
| CiteWorth 数据 | CC-BY-NC-4.0 | **不能商业分发** | 代码 MIT，数据 NC，分开看 |
| SciFact | 论文/数据卡口径 claims CC BY 4.0、abstracts ODC-By 1.0；HF 卡 cc-by-nc-2.0；仓库 NOASSERTION | 需逐项核对后再用，不能仅凭单一卡片 | 摘要来自 S2ORC，注意 ODC-By；NC 口径按更严格处理 |
| CFEVER | 标注 Apache-2.0；维基文本 Wikipedia policy | 标注可用；文本需署名/相同方式共享 | 不能把维基文本当自有数据 |
| LongCite-45k | Apache-2.0 | 可用 | 仍需遵守底层语料 |
| RAGTruth | MIT | 可用 | 英文 |
| GROBID | Apache-2.0 | 可用 | 模型权重也需核对 |
| CERMINE | AGPL-3.0 | **避免** | 传染性 |
| refextract | GPL-2.0 | **避免** | copyleft |
| Anystyle | BSD-2-Clause | 可用 | 但中文不支持 |
| BGE-M3 / reranker | MIT | 可用 | 模型卡为准 |
| 论文 PDF 全文 | 各出版社/CC 许可 | **不提交仓库** | 只存 URL、manifest、短 quote；全文缓存放 `data/cache/` 且不入库 |

---

## 3. 最短路径：把现有零件接起来

### 3.1 目标链路

```text
10 篇 citing papers（有 OA 全文/参考文献）
  → pdf_extract.extract_text / HTML 正文
  → split_references + reference_parser.parse_reference_list
      └─ 条目少时 refs_layout.extract_reference_entries 回退
  → citation_anchor.extract_citations（正文 [n]/作者-年）
  → support.build_claims（引用句 → reference index）
  → 被引论文 DOI 解析（OpenAlex/Crossref）
  → fetch_citemap_fulltext 的同款抓取器（Europe PMC/arXiv/PMC/OA PDF）
  → citemap_verify.rank_sentences + verify_claim_in_text（逐句、逐字 quote）
  → Evidence(stance, quote, locator, confidence)
  → CiteMap JSON → 图投影 → 实线/虚线/无证据 UI
```

### 3.2 哪些是“已有”，哪些是“胶水”

| 步骤 | 现状 | 需要新增的工作量 |
| --- | --- | --- |
| PDF/HTML 取文 | 已有 `pdf_extract`；Live 已有 arXiv HTML 抓取 | 复用；HTML 正文抽取可借 Live 的 `_fetch_page_html`/解析器 |
| 参考文献列表 | 已有 `refs_layout` + `reference_parser` | 复用；对 10 篇做一次人工抽查 |
| 正文引用锚点 | 已有 `citation_anchor` | 复用；对 `[n]` 与显示编号错位做校验（Live t14 已踩过这个坑） |
| 引用句→参考文献 | 已有 `build_claims` | 基本复用；作者-年歧义时标记“未映射”，不猜 |
| 被引论文 DOI | 已有 `metadata_verify.search_openalex/search_crossref` | 复用；加 DOI 归一化 |
| 被引论文全文 | 已有 `fetch_citemap_fulltext` 的抓取逻辑，但当前按主题 corpus 抓 | **小改**：输入 DOI 列表而非固定 corpus；缓存 key 用 DOI/paper_id |
| 句子检索 | 已有 `rank_sentences`；可选 `embeddings.rerank` | 复用；先用词面，不够再开 BGE-M3 |
| 支持判定 | 已有 `verify_claim_in_text` + `support.judge_support` | 复用；把 `full/partial/none` 映射到 schema stance（support/partial→support，contradict 需额外提示词，none→neutral/no evidence） |
| 证据落库 | `evidence_map` 有 evidence.quote/locator/confidence/verified | 复用；加 `source_paper_id`/`citation_key`/`page` 可选字段（或写 notes） |
| 关系图 | 无投影 | **新增**：从 JSON 派生 nodes/edges，SVG/Canvas 渲染；不需要图数据库 |
| UI 实线/虚线 | CiteMap 页面有证据卡，无“证据强度”视觉 | **新增**：solid=有逐字 quote 且判官 full/partial；dashed=候选相关但无 quote/无全文；灰色=无证据 |

### 3.3 schema 映射（不破坏现有 30 篇）

| schema | 在全文证据链路里的含义 |
| --- | --- |
| `Paper` | citing paper（正文来源）或被引 paper（证据来源）；用 `paper_id` 区分 |
| `Claim` | citing paper 里带 `[n]` 的引用句；建议可选加 `source_paper_id`（不改现有必填） |
| `Evidence` | `paper_id` = 被引论文；`quote` = 被引论文原文句；`locator` = 章节/页码；`stance` = support/contradict/neutral；`confidence`；`verified` |
| `Method` / `Sample` | 从被引论文全文抽；没有就留空，不阻断 |
| `Gap` | 该 claim 在 10 篇里没有找到全文证据，或只有相关句没有支持句 |

**关键规则**：`quote` 必须是候选句的精确子串；没有 quote 就不能生成 `support` 证据，只能 `neutral`/`no_evidence`。这条在 `citemap_verify` 已实现，产品层不要再放宽。

### 3.4 关系图投影

不要先上图数据库。直接从业已存在的 JSON 派生：

| 节点 | 边 |
| --- | --- |
| Paper（citing/cited） | Claim --about--> Paper（citing） |
| Claim | Evidence --supports/contradicts/neutral--> Claim |
| Evidence | Evidence --cited_from--> Paper（被引） |
| Gap | Gap --addresses--> Claim |

前端用 `topic_payload` 增加一个只读 `graph` 字段（服务端派生，不改 schema 文件）：

```json
{
  "nodes": [{"id": "paper:edu-001", "type": "paper", "label": "..."}],
  "edges": [{"source": "evidence:edu-e01", "target": "claim:edu-c1", "type": "supports"}]
}
```

这样：

- 现有 30 篇 abstract 级地图照常工作；
- 全文证据 demo 只多一个 `graph` 投影；
- 不需要 Neo4j/图数据库，也不需要前端引入 CDN 图库（可用 SVG 或项目内已有依赖）。

---

## 4. MVP：10 篇 / 20 条 claim

### 4.1 输入与选样

- **10 篇 citing papers**：从现有 `data/evidence_map/corpus` 的 30 篇里选（已有 OA 状态/许可/DOI），优先选有 PDF/HTML 全文、参考文献列表完整、正文有 `[n]` 的。
- **20 条 claim**：每篇 2 条带 `[n]` 的引用句；`[n]` 必须能在该文参考文献列表中解析到条目。
- **被引论文**：20 条 claim 对应的被引论文需有 OA 全文（Europe PMC/arXiv/PMC/OA PDF 任一）；没有全文的 claim 只作为虚线/无证据样本，不硬凑。
- **选样记录**：每篇记录 DOI、OpenAlex ID、全文 URL、许可、抓取日期；不提交 PDF，只提交 manifest 与短 quote。
- **不做的**：不伪造页面、不把“主题相关句”当支持、不把摘要句冒充全文句。

### 4.2 处理流程（对应 3.1）

1. `pdf_extract.extract_text` 取正文；HTML 走现有抓取器。
2. `split_references` + `parse_reference_list`；条目 <5 或标题异常时用 `refs_layout`。
3. `citation_anchor.extract_citations` 找 `[n]`；用 `build_claims` 生成引用句→reference index。
4. `metadata_verify.search_openalex/search_crossref` 解析被引 DOI；失败则标题匹配 + 人工确认。
5. 用 `fetch_citemap_fulltext` 的抓取函数取被引论文全文（缓存文本，不存 PDF）。
6. `citemap_verify.split_sentences` + `rank_sentences` 选 top-12；`verify_claim_in_text` 判定 full/partial/none，并要求 quote 精确命中。
7. 人工复核 20 条 claim：每条记录“solid / dashed / no_evidence”，以及 quote 是否正确。
8. 写入 CiteMap JSON（复用 `evidence_map` schema），生成 graph 投影，前端渲染。

### 4.3 UI 实线 / 虚线 / 无证据

| 状态 | 条件 | 视觉 | 文案 |
| --- | --- | --- | --- |
| **实线（solid）** | 有被引论文全文；判官 full/partial；quote 逐字命中；人工复核通过 | 实线边 + 证据卡（quote + locator + DOI） | “全文证据句，逐字引用” |
| **虚线（dashed）** | 找到相关句/候选，但没有支持判定，或只有摘要 | 虚线边 + 候选卡 | “相关候选，不构成支持证据” |
| **无证据（no_evidence）** | 没有全文/没有候选/判官 none | 灰色占位 + 原因 | “未找到支持该句的全文证据” |
| **不可用（error）** | 抓取失败/解析失败/无 DOI | 灰色 + 原因 | “无法核验，不猜测” |

禁止：把“虚线”画成“支持”；把“没有证据”写成“造假”；把模型置信度当人工金标。

### 4.4 工作量估算（1 名熟悉仓库的工程师）

| 工作 | 人日 |
| --- | --- |
| 10 篇选样、许可/全文 URL 核对、manifest | 0.5 |
| 文本/参考文献/引用锚点跑通 + 10 篇抽查 | 1.0 |
| 被引论文全文抓取（改输入 + 缓存） | 0.5 |
| 句子检索 + 判官 + quote 校验 | 1.0 |
| schema/API 适配（evidence、graph 投影） | 1.0 |
| 前端 solid/dashed/no_evidence + 图 | 1.5 |
| 20 条人工复核 + 误差分析 | 1.0 |
| 缓冲/修 bug | 1.0 |
| **合计** | **7.5（约 6–8）** |

若加 BGE-M3：+0.5–1 人日（部署 endpoint/索引），不必 GPU；若加 GROBID 中文：+5–10 人日标注/重训，不在 MVP。

### 4.5 失败降级

| 失败 | 降级 |
| --- | --- |
| 被引论文无 OA 全文 | 只给摘要级/虚线；UI 明确“未取得全文” |
| 参考文献解析失败 | 允许人工粘贴 10 条参考文献；或从 DOI 反查；不猜条目 |
| `[n]` 与显示编号错位 | 用页面/列表显示编号对齐；对不上就标“未映射”，不按内部 id 猜 |
| 作者-年歧义 | 只匹配年份+第一作者；仍歧义就标未映射 |
| 判官不可用/超时 | 退回 `rank_sentences` 规则：只有逐字 quote 才 dashed，不生成 solid |
| 中文 claim vs 英文全文召回差 | 只把翻译用于检索；判官看原文；仍无候选就 no_evidence |
| 许可不明 | 排除出 demo；只保留 DOI/链接，不进 quote 数据集 |
| 图数据不完整 | 渲染部分图 + 明确缺口；不补假节点 |

### 4.6 验收与 kill criteria

**MVP 验收（硬指标）**

- 10 篇 citing papers 有 OA 全文或可解析全文；许可字段无空。
- 20 条 claim 中 ≥14 条能映射到被引论文；≥10 条有全文候选句。
- 人工复核：solid 证据的 quote 正确率 ≥80%；solid+partial 覆盖率 ≥50%。
- 0 条伪造 quote；所有 quote 都能在被引论文文本中精确找到。
- UI 至少展示 5 条 solid、5 条 dashed、5 条 no_evidence，且没有把 dashed 标成 solid。
- 仓库不出现版权不明 PDF；全文缓存在 `data/cache/`。

**Kill criteria（触发就缩小范围/停）**

1. 10 篇里 <7 篇能拿到全文/明确许可 → 改用英文 arXiv 页面或只做摘要级。
2. 20 条 claim 的 `[n]`→参考文献映射 <70% → 先人工映射，仍不达标就砍到 5 篇。
3. 人工复核 solid 精确率 <75% → 不发布 solid 状态，只展示 dashed/no_evidence。
4. 单人 >10 人日仍跑不通 10 篇 → 砍关系图/向量检索，保留 3 篇纵向 demo。
5. 判官不可用/成本不可控 → 只做“引用存在性 + 逐字 quote”规则版，不做 support 判定。
6. 任何关键数据许可不清 → 该数据只做内部评测，不进公开材料。

---

## 5. 两种架构与推荐

### 5.1 架构 A：重结构（GROBID + 向量库 + 图数据库）

```text
PDF → GROBID TEI → 结构化正文/参考文献
    → BGE-M3/SPECTER2 向量库 → cross-encoder 精排
    → LLM judge → 图数据库（Neo4j）→ 前端图
```

- 适合：英文论文为主、追求长期可扩展、愿意维护 Java 服务和标注。
- 成本：GROBID 2–4 GB + 向量模型 2.3 GB + reranker 2.3 GB；图数据库另算；12–18 人日；中文还要 5–10 人日标注/重训。
- 风险：3 周内做不完；中文结构解析不保证；多服务运维；图数据库对 10 篇/20 条是过度设计。
- 结论：**不推荐作为本次比赛主路径**；可作为英文长期路线。

### 5.2 架构 B：轻结构（推荐）

```text
PDF/HTML → pdf_extract + refs_layout + reference_parser
         → citation_anchor + build_claims
         → 被引 DOI → OA 全文抓取
         → rank_sentences（可选 BGE-M3）→ judge + quote 校验
         → CiteMap JSON → graph 投影 → 现有 CiteMap 前端
```

- 适合：3 周、10 篇/20 条、中文/英文混合、无 GPU。
- 成本：0 新服务（BGE-M3 可选）；6–8 人日；不新增图数据库；不下载大模型也能跑。
- 风险：规则解析在复杂 PDF 上会漏；中文参考文献格式多；没有公开中文全文 benchmark；靠 10 篇人工金标保证诚实。
- 结论：**推荐**。先把“引用句→被引全文→逐字 quote→UI 实线/虚线”跑通，再决定是否加 BGE-M3/reranker。

---

## 6. 必须自建 vs 直接复用

| 能力 | 直接复用 | 必须自建/小改 | 理由 |
| --- | --- | --- | --- |
| PDF 取文 | `pdf_extract` | 无 | 已有三后端 |
| 参考文献版式 | `refs_layout` | 调阈值/抽查 | 已有 PDFium 坐标系 |
| 参考文献字符串 | `reference_parser` | 补格式 | GB/T/APA/ACL 已有 |
| 正文引用锚点 | `citation_anchor` | 无 | 数字/作者-年/脚注已有 |
| 引用句→参考文献 | `support.build_claims` | 歧义处理 | 已按 index 映射 |
| 被引论文全文 | `fetch_citemap_fulltext` 抓取逻辑 | 输入改 DOI、缓存 key | 当前按主题 corpus |
| 句子检索 | `citemap_verify.rank_sentences` | 可选 BGE-M3 | 词面基线够 MVP |
| 支持判定 | `verify_claim_in_text` / `support.judge_support` | stance 映射/提示词 | full/partial/none 已有 |
| 证据 schema | `evidence_map` | 可选 `source_paper_id`/`page` | 现有 quote/locator/confidence 够 |
| 关系图 | 无 | **自建投影 + SVG** | 不需要图数据库 |
| UI 实线/虚线 | CiteMap 页面 | **自建状态样式** | 现有只有证据卡 |
| 10 篇/20 条金标 | 无 | **自建** | 没有可直接用的中文全文数据 |
| 引用意图门禁 | SciCite/ACL-ARC（研究） | **自建映射规则** | 标签不是 stance，且许可限制 |
| stance 校准 | SciFact/CFEVER（研究） | 自建 harness | 语言/粒度不同，不能同集 |

---

## 7. 已验证 / 未验证

### 7.1 已验证（本机）

```text
python -m pytest tests/test_citation_anchor.py tests/test_refs_layout.py tests/test_refs_layout_pdfium.py -q
31 passed in 3.19s

python -m pytest tests/test_citemap_verify.py -q
5 passed in 1.56s
```

- 读了 `data/experiments/citation_anchor_real.json`：22 篇 / 529 refs / 543 citations / 318 cited refs（60.1%）/ 自洽率 89.5%（非人工准确率）。
- 读了 `data/experiments/citemap_atomic_fulltext_v3_summary.json`：25/30 全文、258 组合、10 full / 15 partial / 233 none；7 个人工正例格，full 5/7、any 6/7。
- 读了 `docs/citemap_atomic_fulltext.md`、`docs/citemap_dynamic.md`，确认现有全文链路是“主题论文全文 + 原子断言”，不是“被引论文全文 + 引用句”。
- 未新增依赖、未下载模型、未改产品代码。

### 7.2 未验证（必须在材料里标明）

- GROBID 0.9.1 在中文期刊 PDF 上的实际结构准确率；社区经验不等于本仓库实测。
- Anystyle/refextract/CERMINE 的实际中文表现（官方文档已说明不支持或领域偏，未跑）。
- BGE-M3 / bge-reranker-v2-m3 在 20 条 claim 上的召回/延迟；本轮无 endpoint、无 GPU、未下载权重。
- 10 篇/20 条端到端 demo；本轮只做尽调与代码路径核对。
- SciCite/ACL-ARC 的数据许可最终解释；两者都只能内部评测，不能分发。
- SciFact 的 HF 卡（cc-by-nc-2.0）与论文/数据卡口径（claims CC BY 4.0、abstracts ODC-By）存在冲突；正文按更严格的 NC 处理，正式使用前需逐项确认。
- CFEVER 维基文本的署名/相同方式共享义务在比赛材料中的具体满足方式。

---

## 8. 参考资料

**解析器**

- [GROBID 仓库](https://github.com/grobidOrg/grobid)；[0.9.1 release](https://github.com/grobidOrg/grobid/releases/tag/0.9.1)
- [CERMINE 仓库](https://github.com/CeON/CERMINE)
- [refextract 仓库](https://github.com/inspirehep/refextract)
- [Anystyle 仓库](https://github.com/inukshuk/anystyle)
- [pypdfium2](https://github.com/pypdfium2-team/pypdfium2)

**引用意图/上下文**

- [SciCite 仓库](https://github.com/allenai/scicite)；[HF 数据集](https://huggingface.co/datasets/allenai/scicite)
- [ACL-ARC 论文（LREC 2018）](https://aclanthology.org/L18-1239/)
- [CiteWorth 仓库](https://github.com/copenlu/cite-worth)；[HF 数据卡](https://huggingface.co/datasets/copenlu/citeworth)

**断言-证据/引用**

- [SciFact 仓库](https://github.com/allenai/scifact)；[HF 数据集](https://huggingface.co/datasets/allenai/scifact)
- [CFEVER 仓库](https://github.com/IKMLab/CFEVER-data)；[HF 数据集](https://huggingface.co/datasets/IKMLab-team/cfever)
- [LongCite 仓库](https://github.com/THUDM/LongCite)；[LongCite-45k](https://huggingface.co/datasets/THUDM/LongCite-45k)
- [RAGTruth 仓库](https://github.com/ParticleMedia/RAGTruth)

**检索模型**

- [BGE-M3](https://huggingface.co/BAAI/bge-m3)
- [SPECTER2](https://huggingface.co/allenai/specter2)
- [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)

**仓库内证据**

- [CiteMap 全文原子核验](../citemap_atomic_fulltext.md)
- [CiteMap 动态生成](../citemap_dynamic.md)
- [Live held-out 研究](live_holdout.md)
- `data/experiments/citation_anchor_real.json`
- `data/experiments/citemap_atomic_fulltext_v3_summary.json`
- `data/evidence_map/claims_atomic.json`

---

## 9. 给队长的三句话

1. **不用重造解析器**：`citation_anchor + refs_layout + reference_parser + citemap_verify` 已经能把“引用句→被引论文全文→逐字 quote”串起来，缺的是被引论文全文抓取和 graph/UI 胶水。
2. **数据不满足**：没有可直接分发的“中文论文 claim→全文证据”数据集；SciFact/CFEVER/LongCite/RAGTruth 都不是同一任务。MVP 必须自建 10 篇/20 条人工金标，且只内部使用。
3. **推荐轻架构 B，6–8 人日**；GROBID/Anystyle 不是当前瓶颈，GROBID 只在英文长期路线里考虑，中文不要碰重训。
