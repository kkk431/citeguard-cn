# CiteMap / CiteGuard Live 开源资源可行性总表（E4 / t21）

> 调研日期：2026-11-16。只做资源与选型调研，不改产品代码。
> 结论先行：**Live 最小复用 MVP 约 5.5 人日（含 10 页真实验证、扩展联调、held-out 复测），建议 GO；CiteMap 摘要级 MVP 约 7.5–9 人日，建议“有条件 GO”（2 主题 × 15 篇 + 1 篇全文纵向样例）；两个功能的“自研补齐”架构都 ≥11 人日，不作为主亮点。**
> 人日均为**估算**（±40%），不含队长整合、材料/截图、验收测试；许可证未核项集中列在 §11，不阻塞选型。所有外部结论附来源链接；本网络无法访问 huggingface.co，HF 只作下载指针，不作唯一许可来源。

## 0. 一页结论（给队长拍板）

| 功能 | 最小复用架构 | 估算人日 | 关键数据/许可 | 决策 | 理由 |
|---|---|---|---|---|---|
| CiteGuard Live | A：Readability + OpenAlex/Crossref/Europe PMC + 现有 `check_claim` + BGE-M3 | 5.5（含 10 页验证 1.0、扩展联调 1.5、held-out 复测 0.5） | OpenAlex CC0、Crossref 开放、Europe PMC 按文章、Readability Apache-2.0、BGE-M3 MIT | **GO** | 已有 t13 21/30、t15 30/30、t18 证据 11/30 的真实数字；缺口是判官未配置，可降级展示 |
| CiteGuard Live | B：全文抓取 + GROBID/PDF.js + AlignScore/MiniCheck/ContextCite | 10–14 | MiniCheck 代码许可未核；AlignScore 代码许可未核；全文许可按文章 | 不选主亮点 | 超出 10 人日门槛，且英文对齐模型对中文收益未验证 |
| CiteMap | A：OpenAlex 主题检索 + 摘要级 claim/evidence + 现有判官 + citation-js/CSL | 7.5–9 | OpenAlex CC0、citation-js MIT、CSL CC BY-SA 3.0 | **有条件 GO** | 2 主题 × 15 篇可端到端；摘要级对 method/sample 覆盖弱，需 1 篇全文纵向样例补深度 |
| CiteMap | B：GROBID/docling 全文解析 + 方法/样本抽取 + PaperQA2/OpenScholar 综述 | 15–20 | GROBID Apache-2.0、docling MIT、PaperQA2 Apache-2.0 | 不选主亮点 | 超 15 人日门槛；PaperQA2/OpenScholar 还依赖自备 LLM |

**一句话**：两个功能都能在 2–3 周内做成“可演示”，但都必须用 A 架构、冻结范围、把“规则判定/构造标签”写在脸上；B 架构只保留为赛后扩展。

## 1. 估算口径与拆分（回答“5.5 人日是否含验证/联调/复测”）

### 1.1 Live A 的 5.5 人日拆分

| 工作项 | 人日（估算） | 是否含在 5.5 | 说明 |
|---|---|---|---|
| 10 页真实页面验证（抓取、60 句选句、DOI handle 校验、逐页 hit@3） | 1.0 | 是 | 网络失败/重试占一半；页面许可逐页记录 |
| 扩展联调（v2 MV3 已能加载；接本地 API、错误态、证据展示） | 1.5 | 是 | 不含浏览器商店上架；只做本地加载演示 |
| held-out 复测 + 数字固化（同 30 句 before/after） | 0.5 | 是 | 复用 `scripts/eval_live.py`，只换数据路径 |
| 候选/证据展示打磨（无摘要、无候选、规则判定的三种空态文案） | 1.0 | 是 | 与 §6 降级路径绑定 |
| 评测脚本/数据校验维护 | 0.5 | 是 | `--check` + pytest |
| 缓冲/回归（网络抖动、接口字段变化） | 1.0 | 是 | 建议保留，不要压到 4.5 |
| **合计** | **5.5** | — | 若去掉缓冲为 4.5；对外承诺建议写 6–7 人日 |

> 结论：5.5 人日**包含** 10 页验证、扩展联调、held-out 复测；但这是“顺利路径”，实际排期建议 6.5–7.5 人日（含一次返工）。

### 1.2 CiteMap A 的 7.5–9 人日拆分

| 工作项 | 人日（估算） | 说明 |
|---|---|---|
| 主题→论文清单（OpenAlex 检索 + 15 篇/主题筛选 + 元数据落盘） | 1.0 | 2 个主题 |
| 摘要级 claim/evidence 抽取（复用现有判官/规则，加 schema 映射） | 2.0 | paper/claim/evidence/method/sample/stance/gap |
| stance/覆盖/gap 计算与可视化数据 | 1.5 | gap = 无证据/矛盾/覆盖空白 |
| 1 篇全文纵向样例（PDF 解析 + 方法/样本抽取） | 1.5 | 只做 1 篇，证明“能深” |
| 导出 JSON/页面联调 | 1.0 | 与队长主线页面接口 |
| 缓冲 | 0.5–1.5 | 领域筛选返工 |
| **合计** | **7.5–9** | 不含 B 架构 |

## 2. 资源矩阵（单表，按功能列区分；Map ≥12、Live ≥12）

字段说明：版本写“未标注版本”表示仓库/服务没有可核的语义化版本；成熟度按 release/提交活跃度/文档粗判（高/中/低）；人日为**估算**；商用/展示列区分“随产品分发”和“仅评测/展示”。

| ID | 名称 | 版本 | 许可证（来源） | 覆盖能力 | 成熟度 | 接入人日（估算） | 商用/比赛展示 | 缺口 | 功能 |
|---|---|---|---|---|---|---|---|---|---|
| M01 | OpenAlex API | REST v1（无版本号） | CC0（[FAQ](https://ourresearch.gitbook.io/help.openalex.org/faq)） | works/authors/参考文献/摘要倒排索引 | 高 | 0.5–1 | 是 | 中文社科覆盖率低；摘要非全量 | Map/Live |
| M02 | Crossref REST API | 无版本（REST） | 开放、免费 API（[文档](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)） | DOI 元数据、参考文献、撤稿 | 高 | 0.5–1 | 是 | 中文期刊参考文献字段稀疏 | Map/Live |
| M03 | arXiv API | 无版本 | 元数据 CC0（[使用条款](https://info.arxiv.org/help/api/tou.html)） | 预印本元数据/摘要 | 高 | 0.5 | 是 | 非同行评审；PDF 许可按论文 | Map/Live |
| M04 | Semantic Scholar Graph API | 无版本 | S2 Data：CC BY-NC 或 ODC-BY，需署名（[License](https://www.semanticscholar.org/product/api/license)） | 引用上下文/意图、参考文献、TLDR | 高 | 1–1.5 | 是（展示/评测需署名；商用需确认 NC 范围） | 限流、at-will、不可转售 | Map/Live |
| M05 | OpenCitations COCI | 无版本 | 数据 CC0（[站点](https://opencitations.net/)） | DOI→DOI 引用链（约 11.9 亿条，2021 快照） | 高 | 1 | 是 | 只覆盖有 DOI 的文献 | Map |
| M06 | Unpaywall API | 无版本 | **未验证**（[产品页](https://unpaywall.org/products/api) 无许可声明） | OA 全文位置 | 中 | 0.5 | 未验证 | 许可/条款未核 | Map/Live |
| M07 | GROBID | 0.9.0（镜像标签；release 页本轮限流未核） | Apache-2.0（[仓库](https://github.com/grobidOrg/grobid)） | PDF→TEI 头信息、参考文献、引用上下文 | 高 | 2–3 | 是 | 扫描件/复杂中文混排弱；Java 服务 | Map/Live |
| M08 | Anystyle | 1.6.0 | BSD-2-Clause（[rubygems 元数据](https://rubygems.org/api/v1/gems/anystyle.json)；GitHub license 字段 NOASSERTION） | 参考文献列表解析（CRF） | 中 | 1.5–2 | 是 | Ruby 服务化；模型需随包 | Map |
| M09 | Docling | 2.150.1 | MIT（[PyPI](https://pypi.org/project/docling/)） | PDF 版面/阅读顺序/表格；元数据抽取仍标注 coming soon | 高 | 1.5–2 | 是 | 引用解析不是主项 | Map/Live |
| M10 | MinerU | 未标注版本（仓库 HEAD） | Apache-2.0 + 附加条款（[LICENSE](https://github.com/opendatalab/MinerU)） | 中文 PDF 版面/OCR | 高 | 2–3 | 有条件（MAU 1 亿/月营收 2000 万美元阈值） | 依赖重；商用阈值需法务确认 | Map/Live |
| M11 | citation-js | 0.9.0 | MIT（[npm](https://registry.npmjs.org/citation-js/latest)） | CSL 格式化/解析（BibTeX/RIS/CSL-JSON） | 高 | 1 | 是 | 中文 GB/T 细节依赖 CSL 样式 | Map |
| M12 | CSL styles（含 GB/T 7714） | 仓库 HEAD | CC BY-SA 3.0（[仓库](https://github.com/citation-style-language/styles)） | 中文 GB/T 7714 数字制样式 | 高 | 1–1.5 | 是（SA 只覆盖样式文件，不改产品代码） | 字段映射/中文姓名需调试 | Map |
| M13 | PaperQA2 | 未标注版本 | Apache-2.0（[仓库](https://github.com/Future-House/paper-qa)） | 科学文献 RAG + 引用 | 中 | 3–5 | 是 | 需自备 LLM/embedding；答案质量依赖模型 | Map |
| M14 | OpenScholar | 未标注版本 | Apache-2.0（[仓库](https://github.com/AkariAsai/OpenScholar)） | 文献综述 + 引用 | 中 | 5+ | 是 | 8B 模型 + 检索，超出 3 周窗口 | Map |
| M15 | SPECTER2 | 未标注版本 | Apache-2.0（[仓库](https://github.com/allenai/specter2)；权重卡未验证） | 论文向量/相似度 | 高 | 1–2 | 是（权重许可按模型卡） | 英文为主 | Map/Live |
| M16 | BGE-M3 | 未标注版本 | MIT（[FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding)） | 多语向量（已接入） | 高 | 已接入 | 是 | 语义检索上限；477 池 R@3 0.3219 | Map/Live |
| M17 | FActScore | 未标注版本 | MIT（[仓库](https://github.com/shmsw25/FActScore)） | 原子事实分解 + 核验 | 中 | 2–3 | 是 | 需 LLM 分解；英文基准 | Map |
| M18 | RefChecker | 未标注版本 | Apache-2.0（[仓库](https://github.com/amazon-science/refchecker)） | claim-evidence 三元组检查 | 中 | 2–3 | 是 | 需 LLM；主要英文 | Map/Live |
| M19 | SciFact | 2020 | claims CC BY 4.0 / corpus ODC-By 1.0 / code Apache-2.0（[LICENSE](https://github.com/allenai/scifact/blob/master/LICENSE.md)） | 科学 claim/stance/evidence 评测 | 高 | 0.5 | 是 | 英文；生物医学域 | Map/Live |
| M20 | LongCite-45k | 2024 | Apache-2.0（[仓库](https://github.com/THUDM/LongCite)） | 44,600 条句级引用 QA（中英） | 高 | 1–2 | 是 | 长上下文；训练成本高 | Map/Live |
| M21 | CFEVER | AAAI-24 | Apache-2.0（[数据仓库](https://github.com/IKMLab/CFEVER-data)） | 中文 fact verification（dev 3,000 / train 24,012） | 高 | 0.5–1 | 是 | 百科域，非论文域 | Map/Live |
| M22 | RAGTruth | ACL 2024 | MIT（[仓库](https://github.com/ParticleMedia/RAGTruth)） | 约 18,000 条响应的词级幻觉标注 | 高 | 1 | 是 | 英文；任务域偏 QA/摘要 | Map/Live |
| M23 | SciCite | NAACL 2019 | 代码 Apache-2.0（[仓库](https://github.com/allenai/scicite)）；**数据许可未验证** | 引用意图分类 | 中 | 0.5–1 | 未验证（数据） | 英文；意图标签 3 类 | Map |
| M24 | ACL-ARC | 2018 | **未验证**（[论文](https://aclanthology.org/N19-1363/)；数据页 403） | 引用意图 1,941 条 | 中 | 1–2 | 未验证 | 获取渠道与许可都不明确 | Map |
| M25 | CiteWorth | 2022 | 代码 MIT / 数据 CC BY-NC 4.0（[仓库](https://github.com/copenlu/cite-worth)） | 引用价值判断 | 中 | 0.5–1 | 评测可以，商用否 | NC 数据不能随产品分发 | Map |
| M26 | ContextCite | NeurIPS 2024 | MIT（[仓库](https://github.com/MadryLab/context-cite)） | 生成句→上下文片段归因 | 中 | 2–3 | 是 | 需模型；中文未验证 | Map/Live |
| M27 | Readability.js | 0.6.0 | Apache-2.0（[npm](https://registry.npmjs.org/@mozilla/readability/latest)） | 网页正文/标题抽取 | 高 | 0.5 | 是 | 依赖 DOM；对 PDF 页无效 | Live |
| M28 | Europe PMC REST | 无版本 | 内容按文章许可（[EBI Europe PMC REST](https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=chatgpt&format=json&pageSize=1)；europepmc.org 页面本网络 403）；统一 API 条款未验证 | 3,300 万+ 文献、1,020 万全文、650 万 OA | 高 | 0.5–1 | 是（摘要/评测） | 统一许可未验证；OA 子集才可复用全文 | Live |
| M29 | PDF.js | 无版本（仓库 HEAD） | Apache-2.0（[仓库](https://github.com/mozilla/pdf.js)） | PDF 文本层/渲染 | 高 | 已接入 | 是 | 版面/阅读顺序弱 | Live |
| M30 | MiniCheck | EMNLP 2024 | 代码许可**未验证**；数据卡 MIT（[仓库](https://github.com/Liyan06/MiniCheck)） | 轻量 groundedness 判定 | 中 | 1.5–2 | 未验证 | 代码/权重许可未核；英文训练 | Live |
| M31 | AlignScore | ACL 2023 | MIT（HF 卡标注；[仓库](https://github.com/yuh-zha/AlignScore)） | NLI/句子对齐 | 中 | 1.5–2 | 是（代码许可未核） | 英文训练；中文效果未验证 | Live |
| M32 | cross-encoder（ms-marco-MiniLM 类） | 未标注 | Apache-2.0 基座（[sentence-transformers](https://github.com/UKPLab/sentence-transformers)）；模型卡未验证 | 候选重排 | 高 | 0.5–1 | 未验证（模型卡） | 英文为主；需逐模型核许可 | Live |
| M33 | Crossref Retraction Watch | 2025-01 更新 | CC BY 4.0（[文档](https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/)） | 撤稿状态查询 | 高 | 0.5 | 是 | 覆盖不全；更新滞后 | Live |
| M34 | DOI Handle API | 无版本 | 公共解析服务（[DOI 手册](https://www.doi.org/the-identifier/what-is-a-doi/)）；批量条款未验证 | DOI 是否存在/可解析 | 高 | 已接入 | 未验证（批量） | 只验证存在性，不验证内容 | Live |
| M35 | arXiv HTML/abs 页面 | 无版本 | 页面许可按论文（[许可说明](https://info.arxiv.org/help/license/index.html)） | 公开全文/参考文献列表 | 高 | 已接入 | 是（按论文许可） | 每篇许可不同；需解析 LaTeXML | Live |
| M36 | CiteME | NeurIPS 2024 | **未验证**（[仓库](https://github.com/bethgelab/CiteME)） | 130 道引用检索题 | 中 | 1 | 未验证 | 英文、规模小 | Live |

计数：功能列含 Map 的行 26 个，含 Live 的行 26 个（含 Map/Live 共用行），均 ≥12。

## 3. CiteMap：两种架构与“摘要 vs 全文”口径

### 3.1 架构 A（最小复用，推荐）

```text
主题关键词
  └─ OpenAlex /works 检索（per-page 15，去重）
       ├─ 元数据：标题/作者/年份/DOI/摘要(倒排索引还原)
       ├─ 参考文献：referenced_works → OpenAlex/Crossref 补元数据
       └─ claim 抽取（现有判官 prompt 或规则句）
            ├─ evidence：摘要句与 claim 的关键词/数字重合（规则）+ 判官（若配置）
            ├─ stance：support / partial / contradict / neutral（判官；规则只给 support/no_evidence）
            ├─ method/sample：摘要级正则 + 关键词（覆盖有限）
            └─ gap：无 evidence、contradict、样本空白
                 └─ 输出 JSON（paper/claim/evidence/method/sample/stance/gap）
                      └─ 主线页面证据地图 + 导出
```

- **评委现场能看到什么**：选 1 个主题 → 15 篇论文节点 → 点任一 claim 展开“支持/部分支持/无证据”的彩色证据卡 → 右侧 gap 面板列出“3 篇无证据、1 处矛盾、2 篇样本缺失” → 一键导出 JSON。
- **数字怎么来**：claim/evidence 数量、stance 分布、gap 计数全部由导出 JSON 统计；引用健康分沿用五维权重（真实性 25/支持度 25/相关性 20/覆盖 15/规范性 15）；现有支持度判官在 ClaimSupport-CN 100 条构造集 macro-F1 0.9597（**构造标签，非人工金标**）。
- **失败时显示什么**：摘要缺失 → “该论文未开放摘要，证据不可核”；stance 未配置判官 → “本地规则：仅能判断有无重合证据”；method/sample 抽不到 → 明确标“未提取”，不猜。

### 3.2 架构 B（自研补齐）

```text
主题
 └─ OpenAlex 检索 → 候选论文 PDF（Unpaywall/arXiv/Europe PMC）
      ├─ GROBID/docling 解析全文（章节、参考文献、引用上下文）
      ├─ 方法/样本抽取（LLM + 规则，带原文引用）
      ├─ 全文 evidence（句子级，含页码）
      ├─ SPECTER2 聚类 → 主题簇
      ├─ RefChecker/FActScore 三元组核验
      └─ PaperQA2/OpenScholar 综述（可选，需自备 LLM）
           └─ 证据地图 + 综述草稿 + 引用溯源
```

- 评委可见增量：方法/样本列有值、证据来自正文而非摘要、gap 能定位到“某方法在某数据集上无对比”。
- **数字怎么来**：解析成功率（PDF→章节/参考文献）、method/sample 抽取覆盖率、页码级 evidence 条数、簇内论文数；全部写入导出 JSON。
- **失败时显示什么**：PDF 下载失败 → 该论文标“未获取全文”，不编造；解析失败 → 标“未解析”，回退摘要级；抽取为空 → “未提取”。
- 成本：PDF 获取/解析 3–4、抽取 4–6、核验 3–5、综述 3–5，合计 **15–20 人日** → 超门槛，不选。

### 3.3 摘要级 vs 全文：对“完成度 25 分”的支撑差距

| 口径 | 人日（估算） | 能支撑的完成度表述 | 评委可能追问 | 风险 |
|---|---|---|---|---|
| 纯摘要级（2 主题 × 15 篇） | 7.5–9 | “CiteMap 已端到端：主题→论文→claim→证据→stance→gap→导出” | “证据只有摘要，方法/样本呢？” | 中：像“摘要地图”，深度不足 |
| 摘要级 + 1 篇全文纵向样例 | 8.5–10 | 上述 + “全文页码级证据、方法/样本抽取在样例上跑通” | “为什么只有 1 篇？” | 低：可解释为“纵向验证”，成本可控 |
| 全量全文（2 主题 × 15 篇都解析） | 15–20 | “全文级证据地图” | 解析失败率/许可/耗时 | 高：3 周窗口内难稳 |

**建议口径**：报“摘要级 MVP + 1 篇全文样例”，完成度叙事写成“功能闭环 + 深度样例”，不要把 15 篇都宣称全文级。评分表对应证据可写：功能闭环（导出 JSON/页面）、可复现命令、1 篇全文页码证据、2 个主题的 gap 统计；缺口写“全量全文解析未做”。

## 4. CiteGuard Live：两种架构

### 4.1 架构 A（最小复用，推荐）

```text
浏览器扩展（MV3，v2 已可本地加载）
  └─ 选中句 + 当前页 URL/标题
       ├─ 页面识别：DOI → OpenAlex work；arXiv id → arXiv API；否则 Readability 取标题
       ├─ 候选：OpenAlex referenced_works（≤40）→ 摘要补全（OpenAlex/Crossref）
       │        └─ 无页面引用列表时，回退标题/关键词检索（现有逻辑）
       ├─ 排序：BGE-M3 向量 + 标题覆盖（现有 _page_candidate_score）
       ├─ 判定：现有 check_claim（判官可用则 LLM；否则规则）
       └─ 展示：label + confidence + 逐字 evidence 引文 + 候选来源链接
            └─ 空态：无摘要 / 无候选 / 规则判定 三种文案
```

- **评委现场能看到什么**：打开一篇 arXiv HTML 论文 → 选中带 `[12]` 的句子 → 侧栏/弹窗给出“支持/部分支持/无证据”、命中候选、逐字证据引文、来源链接；换一篇页面，展示“页面参考文献优先”的差异。
- **数字怎么来**：`scripts/eval_live.py` 直接调 `check_claim`，输出 hit@1/hit@3、P50/P95、四档分布；t13 公开页集 21/30（0.70），t15 held-out 30/30，t18 证据 11/30、P50 2982.7 ms、P95 16088.8 ms（同 30 句，缓存热）。
- **失败时显示什么**：`no_candidates=0` 但 `evidence` 为空 → “候选已找到，但摘要不足以核对”；无摘要 → “该来源未开放摘要”；判官未配置 → 角标“本地规则判定”，不显示 confidence 的语义解释。

### 4.2 架构 B（自研补齐）

```text
扩展
 └─ 页面全文（Readability / PDF.js / arXiv HTML / Europe PMC）
      ├─ 段落级索引（GROBID/PDF.js 页码）
      ├─ 句子→段落对齐（AlignScore / MiniCheck）
      ├─ 生成句→片段归因（ContextCite）
      ├─ 句级引用抽取（LongCite 风格，中英）
      └─ 证据阈值（RAGTruth 校准）
```

- 增量：证据可定位到页码/段落、能标“无依据句”、可做整页体检。
- **数字怎么来**：页码级 evidence 覆盖率、对齐分数分布、无依据句计数；由脚本按同一批判定输出统计。
- **失败时显示什么**：全文拿不到 → 回退摘要级并标注；对齐低于阈值 → “无法对齐到具体段落”，不给假证据。
- 成本：全文获取 2–3、解析 3–4、对齐/归因 3–5、评测 2，合计 **10–14 人日** → 不作为主亮点；可在 MVP 后按 2–3 人日加“页码定位”单点。

## 5. 两个 MVP 的可验收定义

### 5.1 Live MVP（目标 6–7 人日含缓冲）

- 范围：5 个公开页 + 30 句（t13 集）+ 另行 10 页真实验证；只读公开页/摘要。
- 演示脚本：打开页 → 选句 → 侧栏结果（label/evidence/candidates）→ 展示 3 种空态 → 切换到 held-out 集报 hit@3。
- 验收数字：t13 hit@3 ≥ 21/30（不下降）；10 页验证 hit@3 ≥ 0.70；P50 ≤ 3 s（缓存热）；证据可用 ≥ 11/30（同 t18 口径，规则判定）。
- 边界：不宣称语义理解；不宣称跨语言检索已解决（旧中文集 0/30 的失败原因单独写）。

### 5.2 CiteMap MVP（目标 8.5–10 人日）

- 范围：2 个主题 × 15 篇（OpenAlex 开放元数据/摘要），其中 1 篇做全文纵向样例。
- 演示脚本：主题页 → 论文节点 → claim 证据卡 → stance 颜色 → gap 面板 → 导出 JSON。
- 验收数字：15 篇/主题、claim 覆盖率 ≥70%（有 claim 的论文占比）、导出 JSON 通过 schema 校验、1 篇全文有页码级证据、gap 计数可复现。
- 边界：method/sample 摘要级未提取就写“未提取”；stance 用判官/规则分别标注。

## 6. judge 未配置时的降级路径（本环境实测 `judge_available()=False`）

| 能力 | 本地规则能做 | 不能宣称 | 外部数据/人工标签能否替代 |
|---|---|---|---|
| 证据是否存在 | 关键词/数字重合 + 摘要逐字回查（t18 证据 11/30，其中 8 条指向 gold） | “语义上支持/矛盾” | SciFact/CFEVER/RAGTruth 可校准阈值和做外部评测，但不能替代中文产品判定 |
| stance | 仅 support（有重合）/no_evidence；partial 需阈值 | 可靠的 contradict、置信度校准 | ClaimSupport-CN 有 40 条人工复核模板（未填，约 1 小时可补）；可作小样本金标，不足以训练 |
| 候选排序 | 标题覆盖 + 数字重合 + 向量（BGE-M3） | “语义检索已解决” | t13/t15 已有逐页 hit@3，可作回归；T2Retrieval 可作检索 sanity |
| 置信度 | 不给或只给“规则/判官”来源标记 | 概率校准 | 需人工标注 200+ 条才谈得上校准，3 周内不做 |

**降级展示建议**：UI 角标“规则判定/判官判定”；文档与 PPT 分开写两套数字；演示话术用“可核对证据 + 明确空态”，不用“理解语义”。若队长能配 DeepSeek API 或本地 1.7B LoRA（adapter 已有，test60 0.9721），估计 1–2 人日可切回判官路径；但**不得把 4B LoRA 的 1.0 当亮点**（构造模板饱和，见 `docs/model_card_support_lora_4b.md`）。

## 7. go/no-go 门槛与评分表支撑

| 门槛 | 规则 | 本次判定 |
|---|---|---|
| 主亮点 | ≤10 人日可做 MVP，且关键数据/许可齐 | Live A 5.5 → 保留；CiteMap A 7.5–9 → 保留（有条件） |
| 降 beta | 10–15 人日，或关键数据要等 | CiteMap 全文样例 8.5–10 边缘；Live B 10–14 → beta |
| 砍 | >15 人日，或关键许可不可用 | CiteMap B 15–20；refextract/GPL、PyMuPDF/AGPL 直接不用 |

**不满足项与替代（开发前先确认）**：

- ACL-ARC：获取页 403、脚本库无许可 → **不满足**；改用 SciCite 作英文意图对照（数据许可仍待核），或干脆不做意图分类。
- MiniCheck / AlignScore：代码/权重许可未核 → **MVP 不依赖**；用现有规则 + BGE-M3 排序，若要用先核许可。
- Unpaywall：许可页无声明 → **不满足作为产品依赖**；改用 arXiv/Europe PMC 的公开全文（按文章许可）。
- refextract（GPL-2.0）、PyMuPDF（AGPL-3.0）、SingleFile（AGPL-3.0）：**许可边界不满足**；分别换 GROBID、PDF.js、docling。
- CNKI / Wanfang 数据再分发：**不满足**；只保留本地题录库与公开元数据，演示不打包商业数据。

| 评分项 | 当前证据 | 缺口 | MVP 后可补 |
|---|---|---|---|
| 15 问题场景 | 五维健康分 + 撤稿/DOI + 修复替换 + 公开页 Live | 场景量化仍偏少 | 10 页验证 + CiteMap gap 统计 |
| 20 创新 | 页面引用列表优先 + [n] 映射 + held-out 评测 | 无人工 stance 金标 | 40 条人工复核（1 小时） |
| 20 AI+开源 | BGE-M3/1.7B LoRA/14B 对比；Apache/MIT 资源矩阵 | judge 未配置；4B 饱和 | 1.7B LoRA 接产品（1–2 人日） |
| 25 完成度 | CiteMap 闭环 + Live 扩展 + 复现脚本 | 全文/页码证据只 1 篇样例 | 1 篇全文样例 + 导出 JSON |
| 15 开放成果 | 数据集 CC BY 4.0/ODC-By；代码 Apache-2.0 | 部分资源许可未核 | 许可清单 + 不随包分发 NC |
| 5 材料 | 截图/视频已有基础 | 需按新口径重拍 | MVP 演示脚本 |

## 8. 风险清单

1. **许可证污染**：refextract GPL-2.0、PyMuPDF/SingleFile AGPL-3.0 不能进核心镜像；MinerU 有商用阈值。→ 只选 Apache/MIT/BSD；NC 数据只评测、不随包。
2. **外部 API 不可控**：OpenAlex/Crossref/Europe PMC/S2 都有限流/无 SLA；HF 在本网络不可达。→ 本地缓存 + 失败静默 + 演示前预热。
3. **判官不可用**：`judge_available=False` 时只有规则；不能宣称语义理解。→ 角标 + 两套数字分开。
4. **数据域不匹配**：SciFact/SciCite/RAGTruth 是英文；CFEVER 是百科；不能直接当“中文论文证据”金标。→ 只作外部对照/阈值校准。
5. **中文覆盖**：OpenAlex/Crossref 中文社科覆盖低；中文题录仍需本地库/Wanfang（商业条款）。→ Live 以英文公开页演示，中文走本地题录库；不承诺全中文。
6. **范围蔓延**：CiteMap 全文 + Live 全文对齐同时做会超 3 周。→ 冻结为 A 架构 + 单点样例。
7. **数字误读**：4B LoRA 1.0 饱和、构造集 0.96、21/30 与 30/30 不同集。→ 每张表标 n/数据集/是否人工金标。

## 9. 许可证边界

| 许可 | 义务/限制 | 本项目用法 |
|---|---|---|
| Apache-2.0 / MIT / BSD-2 | 保留版权与许可声明；Apache 含专利授权 | 可进核心镜像；保留 NOTICE |
| CC0 / ODC-By | CC0 无义务；ODC-By 需署名 | OpenAlex/OpenCitations 可自由用；SciFact corpus 署名 |
| CC BY 4.0 | 署名 | SciFact claims、Retraction Watch、公开页引用 |
| CC BY-SA 3.0 | 署名 + 相同方式共享（仅样式文件） | CSL 样式文件单独分发，不改产品代码 |
| CC BY-NC 4.0 | 非商业 | CiteWorth/S2 Data 仅评测，不随包、不用于收费功能 |
| GPL-2.0 / AGPL-3.0 | 传染性/网络分发义务 | **不用**：refextract、PyMuPDF、SingleFile |
| Apache-2.0 + 附加条款 | 商用阈值/署名 | MinerU：MAU<1 亿且月营收<2000 万美元可用；超阈值需商业许可 |
| 按文章许可 | 逐篇确认 | arXiv/Europe PMC 全文；演示只选 CC BY 页面 |

**拒绝项（不做）**：refextract（GPL-2.0，与 Apache 产品不兼容）、PyMuPDF（AGPL-3.0，已隔离为可选）、SingleFile（AGPL-3.0）、CiteWorth/CiteME 数据随包（NC/未验证）、CNKI/Wanfang 数据再分发（商业条款）、DuReader-Retrieval 全量（800 万段落，成本过高）、ACL-ARC（获取 403、许可未验证）。

## 10. 未验证清单（不阻塞，开发前需复核）

1. Unpaywall API 许可（页面无声明）。
2. Europe PMC 统一 API 条款（内容按文章；批量/缓存条款未核）。
3. Semantic Scholar Data 的 CC BY-NC 适用范围（商用功能需法务确认）。
4. ACL-ARC 数据获取与许可（allenai 页面 403；脚本库无许可）。
5. SciCite 数据集许可（代码 Apache-2.0，数据未声明）。
6. MiniCheck 代码/权重许可（数据卡 MIT，仓库未核）。
7. AlignScore 代码许可（HF 卡 MIT，仓库 LICENSE 未逐行核）。
8. SPECTER2/cross-encoder 模型权重卡许可。
9. DOI Handle API 批量使用条款。
10. AnyStyle GitHub license 字段 NOASSERTION 与 rubygems BSD-2-Clause 的差异（以 rubygems 为准，需读 LICENSE）。
11. MinerU 版本号（仓库未打语义化 tag；以 LICENSE 条款为准）。

## 11. 核实与复现

核实日期 2026-11-16；方法：GitHub REST API（license/pushed/stars）、npm registry、rubygems API、PyPI JSON、官方条款页；HF 不可达，未作唯一来源。

```powershell
# 许可证/版本抽查（示例；GitHub API 本机曾触发 403 限流，用网页/镜像替代）
Invoke-RestMethod https://registry.npmjs.org/@mozilla/readability/latest | Select-Object version,license
Invoke-RestMethod https://rubygems.org/api/v1/gems/anystyle.json | Select-Object version,licenses
Invoke-RestMethod https://pypi.org/pypi/docling/json | Select-Object -ExpandProperty info | Select-Object version,license_expression

# 行数与链接校验（本文件）
python D:\Temp\citeguard_e3\check_feasibility.py
```

配套矩阵数据可直接从本文表格抄录；产品侧现有数字见 `docs/live_eval.md`、`docs/research/live_holdout.md`、`docs/research/ablation_matrix.md`、`data/experiments/replacement_eval.json`、`data/experiments/support_lora_qwen3_1.7b.json`、`data/experiments/ablation_matrix.json`。

## 12. 文件

- 本文件：`docs/research/feature_feasibility.md`（t21 唯一交付）
- 引用到的现有证据：`docs/live_eval.md`、`docs/research/live_holdout.md`、`docs/research/ablation_matrix.md`、`docs/research/feature_radar.md`、`data/experiments/support_lora_qwen3_1.7b.json`、`data/experiments/replacement_eval.json`、`data/live_eval/live_eval_public.json`、`data/live_eval/live_eval_holdout.json`、`data/live_eval/live_eval_holdout_enriched.json`
- 未改任何产品代码/配置。
