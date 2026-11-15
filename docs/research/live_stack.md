# Live 开源技术栈调研：页面抽取 / 引用解析 / 来源查找 / 排序

> 2026-11-16 调研。结论先说：**正文抽取和来源查找可以主要复用现成开源件；「HTML 参考文献列表 → 正文 `[n]` 映射」没有可直接复用的成熟件，必须自建适配层；服务端抓取出版商页面（Nature / Springer / MDPI / PubMed）被 Bot 墙或 JS 门挡住，抽取要前移到扩展侧**。因此 10 页 / 30 句 MVP **可做**，但前提是接受「扩展侧抽取 + 本地服务查找/判定」的混合架构；若坚持纯服务端抓取任意网页，则**不满足，需换方案**。

本文只做调研与实测，不改产品代码。实测脚本在临时目录 `D:\Temp\cg_live_stack`，未入库；仓库内只新增本文件。

## 0. 分层结论

| 层 | 可直接复用 | 需要胶水 | 必须自建 | 许可 | 结论 |
| --- | --- | --- | --- | --- | --- |
| 正文抽取（浏览器内） | Readability.js 0.6.0 | 扩展 content script 注入 | — | Apache-2.0 | **可复用**；arXiv / PMC / Wikipedia 实测通过 |
| 正文抽取（服务端） | Readability 同款算法（jsdom）、trafilatura 2.3.1 | 抓取 + 反爬兜底 | — | Apache-2.0 | **部分可用**；出版商页面 0/3，不能作为唯一路径 |
| 参考文献列表解析 | — | — | HTML 适配器 + 编号映射 | 自有 | **必须自建**；arXiv 已有约 200–300 行，PMC / Wikipedia / 通用页需新增 |
| 正文引用标记识别 | — | — | 正则 + 中文全角/作者-年份 | 自有 | 现有 `_CITATION_RE` 只认 ASCII `[n]`，需扩展 |
| 来源查找 | Crossref、OpenAlex、Europe PMC、arXiv API | HTTP 客户端 + 缓存 | — | 免费/CC0/开放 | **可复用**；无需付费 key |
| OA 链接 | Unpaywall | email 参数 | — | 页面无许可声明 | 仅运行时查询，不进入仓库数据 |
| 摘要 | OpenAlex、Europe PMC | inverted index 还原 | — | CC0 / 开放 | **可复用**；t17 已落地 |
| 排序 | 现有词面打分、rank_bm25 0.2.2 | 阈值与融合 | — | Apache-2.0 | **可复用**；候选 ≤5 时词面足够 |
| 跨语言排序 | BGE-M3（可选） | 现有 embeddings 接口 | — | MIT | 可选，非 MVP 必需 |
| 浏览器扩展 | 本仓库 `extension/v2`（MV3 + sidePanel） | content script + 新消息契约 | — | Apache-2.0 | **可复用**；只缺抽取与侧栏真机验证 |
| 评测 | 现有 5 页 / 30 句 + 新增 5 页 | 标注 | — | 页面各自许可 | 10 页 / 30 句可扩展 |

一句话：**能复用的是「读网页」和「查论文」，不能复用的是「把网页里的引用编号对上参考文献条目」。**

## 1. 方法与边界

- 环境：Windows，Node v24.15.0 / npm 12.0.2，Python 3.13.14；`jsdom` + `@mozilla/readability@0.6.0` 在临时目录安装（56 packages，26 s）。
- 抓取：`Invoke-WebRequest`，UA 为 Chrome/140；只抓公开页面，不登录、不绕付费墙。
- 判据：Readability 解析后的 `textContent` 里是否仍保留原页的参考文献条目、首条题名、`[n]` 标记；条目数用页面原始 DOM 选择器对照。
- 未验证：中文页面的真实抽取（Wikimedia 两次 429）、出版商全文（Bot 墙）、真实用户侧栏手势（此前只以普通标签页打开过 `sidepanel.html`）、外部 AI 客户端加载（本任务不涉及 MCP）。
- 时效：价格 / 限流以 2026-11 页面为准；OpenAlex 的 2026 年定价页已取代旧的「10 万次/天」说法，下文按新口径写。

## 2. 页面正文抽取

### 2.1 候选件

| 件 | 版本 / 仓库 | 许可 | 体积 / 依赖 | 适用 |
| --- | --- | --- | --- | --- |
| [Mozilla Readability](https://github.com/mozilla/readability) | 0.6.0（2025-03-03 发布，仓库约 11.4k stars，最后 push 2026-07-09） | Apache-2.0 | npm 解包 154,574 B；无运行时依赖 | 浏览器 / Node（jsdom）通用正文抽取 |
| [Defuddle](https://github.com/kepano/defuddle) | 0.19.6（10,041 stars，2026-10-25 仍有 push） | MIT | 解包 2,765,043 B；依赖 commander、mathml-to-latex；`./node` 仅 ESM | 把网页转 Markdown（阅读模式），不是引用管线 |
| [trafilatura](https://github.com/adbar/trafilatura) | 2.3.1 | Apache-2.0（仓库；PyPI 元数据未填 license 字段） | Python ≥3.10 | 服务端抽取备选 |
| [GROBID](https://github.com/grobidOrg/grobid) | 仓库活跃（push 2026-11-14，5,230 stars） | Apache-2.0 | Java 服务，重 | PDF 参考文献解析，不处理 HTML |

补充：npm 上名为 `readability` 的包是另一个 2014 年的旧包（0.1.0，MIT），不是 Mozilla 版本，集成时要用 `@mozilla/readability`。

### 2.2 实测（2026-11-16，Readability 0.6.0 + jsdom，`{keepClasses:true}`）

| 页面 | HTTP | 原始字节 | Readability 正文 / 原始正文（字符） | 参考文献保留 | `[n]` 标记（读/原） | 首条题名保留 | 解析耗时 |
| --- | --- | ---: | --- | ---: | ---: | --- | ---: |
| arXiv [2611.07772](https://arxiv.org/html/2611.07772) | 200 | 269,526 | 68,672 / 71,924 | 54 / 54 | 36 / 36 | 是 | 180–319 ms |
| arXiv [2610.38049](https://arxiv.org/html/2610.38049) | 200 | 292,141 | 84,590 / 88,377 | 126 / 126 | 156 / 157 | 是 | 同上 |
| arXiv [2610.24037](https://arxiv.org/html/2610.24037) | 200 | 244,870 | 66,583 / 69,932 | 60 / 60 | 136 / 136 | 是 | 同上 |
| arXiv [2610.32576](https://arxiv.org/html/2610.32576) | 200 | 224,872 | 90,413 / 92,785 | 63 / 63 | 212 / 212 | 是 | 同上 |
| arXiv [2610.18926](https://arxiv.org/html/2610.18926) | 200 | 184,908 | 78,014 / 80,482 | 19 / 19 | 121 / 121 | 是 | 同上 |
| [PMC13541550](https://pmc.ncbi.nlm.nih.gov/articles/PMC13541550/) | 200 | 216,812 | 70,606 / 75,947 | 首条保留（总数未计） | 有 | 是 | 92 ms |
| [PMC13198158](https://pmc.ncbi.nlm.nih.gov/articles/PMC13198158/) | 200 | 154,310 | 28,503 / 32,538 | 36 / 36（首条保留） | 48 | 是 | 约 100 ms |
| [Wikipedia: Retrieval-augmented generation](https://en.wikipedia.org/wiki/Retrieval-augmented_generation) | 200 | — | 17,422 / 37,438 | — / 44（首条保留） | 45 / 45 | 是 | 206 ms |
| [PubMed 42698590](https://pubmed.ncbi.nlm.nih.gov/42698590/) | 203 | 5,590 | **28** | 0 | 0 | 否 | — |
| [Nature s41586-023-06221-2](https://www.nature.com/articles/s41586-023-06221-2) | 200 | 3,038 | **209** | 0 | 0 | 否 | — |
| [Springer 10.1007/s10664-022-10241-3](https://link.springer.com/article/10.1007/s10664-022-10241-3) | 200 | 3,038 | **209** | 0 | 0 | 否 | — |
| [MDPI 14/7/406](https://www.mdpi.com/2078-2489/14/7/406) | 403 | — | — | — | — | — | — |

读法：

- arXiv 是 LaTeXML HTML：`.ltx_bibitem` 数量全部保留，首条题名与 `references` 标题都在；标记仅 1 条差异（157→156），属于 Range 被规范化，不影响映射。
- PMC 两页正文与参考文献都保留，Readability 可用；但 PubMed 的 `/42698590/` 是 5.6 KB 的 JS 壳，Readability 只能拿到 28 个字符、标题退化成域名 → **服务端抽取 PubMed 不可行**。
- 出版商三页都是 Bot 墙：Nature / Springer 返回 3,038 B 的 "Client Challenge" 页，MDPI 403。Readability 只能得到 209 字符 → **服务端抽取出版商页面 0/3**。
- Defuddle 在 5 篇 arXiv 上正文更长（96,971–125,353 字符，含页面其它区块），但 **`[n]` 标记数为 0**，首条参考文献题名不保留，`references` 标题仅 1/5 命中 → 它把引用转成了别的形式，**不能作为引用映射的抽取器**；PMC / Wikipedia 同样 0 标记。
- 中文页面：`zh.wikipedia.org` 两次均 429（Wikimedia 对云端 IP 的限流），没有拿到真实中文页样本；Readability 算法本身与语言无关，但中文站点的 `References / 参考文献` 标题启发式、全角标点需另行实测。**这一项标记为「未验证」，不写「支持」。**

### 2.3 失败模式清单

| 模式 | 现象 | 影响 | 处理 |
| --- | --- | --- | --- |
| Bot 墙 / Challenge | 3 KB 壳页，含 `Client Challenge` | 抽取为空 | 扩展侧抽取（用户浏览器已通过），服务端不重试 |
| JS 渲染 | PubMed 5.6 KB 壳 | 抽取为空 | 改用 PubMed E-utilities 或扩展 DOM |
| 参考文献非列表结构 | 纯段落式References、脚注 | 条目切不开 | 通用启发式 + 降级为「无候选」 |
| 动态加载 | 需滚动/点击才出参考文献 | 首屏无条目 | 扩展侧等待/用户触发后再抽 |
| 页面语言 | 中文全角 `［1］`、`（1）` | 现有正则不匹配 | 新增归一化（见 §3） |

### 2.4 结论

**复用 Readability（Apache-2.0）为主抽取器**：浏览器内在用户已渲染的 DOM 上跑，绕开 Bot 墙与登录态；服务端仅对 arXiv / PMC 这类开放 HTML 兜底。Defuddle 适合「把网页变 Markdown 阅读」，不适合引用映射，不进入管线。

## 3. 引用解析

### 3.1 候选件与能力边界

| 件 | 版本 | 许可 | 输入 | 能做什么 | 不能做什么 |
| --- | --- | --- | --- | --- | --- |
| [Citation.js](https://github.com/citation-js/citation-js) | 0.9.0（解包 6.48 MB） | MIT | BibTeX / RIS / DOI / Wikidata / CSL-JSON | 格式互转、CSL 输出；插件包括 DOI / RIS / BibTeX / CSL / Wikidata / PubMed | **不解析 HTML 参考文献列表，不做正文 `[n]` 映射**；没有 HTML 参考文献插件 |
| [refextract](https://github.com/inspirehep/refextract) | 1.1.7（Python 3.11–3.14） | GPL-2.0-or-later | PDF / LaTeX（pdftotext、pypdf） | HEP 论文参考文献抽取 | 无 HTML、无中文、无浏览器；**GPL 与 Apache-2.0 产品核心不兼容** |
| [GROBID](https://github.com/grobidOrg/grobid) | 活跃 | Apache-2.0 | PDF | 学术 PDF 的参考文献/结构解析 | 只吃 PDF，服务端 Java，重；对网页 HTML 无用 |
| [trafilatura](https://github.com/adbar/trafilatura) | 2.3.1 | Apache-2.0 | HTML | 正文 + 元数据（标题/作者/日期） | 不输出结构化参考文献列表；无 `[n]` 映射 |

结论：**没有现成件能完成「HTML 参考文献列表 → 条目 → 正文标记对齐」**。Citation.js 只在需要 CSL/DOI 格式化时有用；refextract 和 GROBID 解决的是 PDF，不是网页。

### 3.2 必须自建的部分（按页面形态）

| 页面形态 | 结构 | 已有 | 需新增 |
| --- | --- | --- | --- |
| arXiv LaTeXML | `section.ltx_bibliography` / `ol.ltx_bibliography`，`li.ltx_bibitem`，`span.ltx_tag_bibitem` + `span.ltx_bibblock` | `src/citeguard/live_check.py` 的 `_BibliographyParser`（949 行起）、`_parse_bibliography`（1078 行起）、`[n]` 映射（约 200–300 行） | 无（已实测 30/30 映射） |
| PMC | `section.ref-list`，`ol > li`，`.mixed-citation` / `.element-citation` | 无 | 适配器 ~80–120 行 |
| Wikipedia | `ol.references > li`，`cite` 模板渲染后的文本 | 无 | 适配器 ~50–80 行 |
| 通用网页 | `h2/h3` 含 References/参考文献 后的 `ol/ul` | 无 | 启发式 ~120–180 行 |
| 正文标记 | ASCII `[1]`、`[1-3]`、`[1,2]`、`[1;2]`；上标；全角 `［1］`；`（1）`；作者-年份 `(Smith, 2020)` / `（张三，2020）` | `_CITATION_RE = re.compile(r"\[\d+(?:\s*[-–—,，]\s*\d+)*\]")`（`live_check.py:94`）只认 ASCII 方括号；`_CJK_BLOCK_RE`（95 行）只做中文分块 | 归一化 + 作者-年份匹配 ~100–150 行；中文分词可选用 jieba（MIT） |

编号对齐的坑已经在 t15 踩过：arXiv LaTeXML 的 `li id="bib.bibN"` 内部 id **不等于**页面显示编号，必须按页面渲染顺序/显示标签建索引，否则来源错配（见 `docs/research/live_holdout.md` §3）。这是自建解析器的核心逻辑，不是「调个库」能解决的。

### 3.3 中文支持

- 现状：`_CITATION_RE` 仅 ASCII；`[n]` 之外的 `［n］`、`（n）`、上标数字都不会被识别。
- 自建量：全角/半角归一化 + 括号形态 + 作者-年份（中文 `（作者，年份）`、英文 `(Author, Year)`）匹配，约 100–150 行；不需要模型。
- 风险：中文网页参考文献格式差异大（GB/T 7714、APA、脚注），首版只保证「有显式编号或作者-年份」的页面，纯脚注页明确返回「不支持」。
- 未验证：中文真实页面（Wikimedia 429）；这条是设计判断，不是实测结论。

### 3.4 结论

**必须自建，但边界可控**：arXiv 已有实现可复用；新增 PMC / Wikipedia / 通用适配器 + 中文标记归一化，合计约 300–500 行（不含测试）。Citation.js 不解决抽取；refextract 因 GPL 与输入格式双重原因排除；GROBID 只在未来做 PDF 全文时考虑。

## 4. 来源查找

### 4.1 候选服务对比

| 服务 | 鉴权 | 限流（2026-11 页面口径） | 数据许可 / 条款 | 适用 | 成本 |
| --- | --- | --- | --- | --- | --- |
| [Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | 无需注册；建议 `mailto` 进 polite pool | 未公布硬上限；polite pool 优先 | 元数据「几乎不受版权保护，可用于任何目的」；摘要可能归出版商 | DOI / 题名 → 元数据、期刊、作者 | 免费 |
| [OpenAlex](https://docs.openalex.org/) | 无需 key；免费 key 提高额度 | 无 key 10 req/s；免费 key 30 req/s + 每日预算 10×（激活后约 $1/天）；语义检索 1 req/s；超限 429 | 数据 CC0 | 摘要（inverted index）、`referenced_works`、DOI 元数据 | 免费层 |
| [Europe PMC REST](https://www.ebi.ac.uk/europepmc/webservices/rest) | 无需 key / email / 注册 | 无公开每秒上限；要求合理使用；分页用 `cursorMark` | OA 内容 + 元数据；**禁止对非 OA 内容做批量自动下载** | 生物医学摘要 / OA 全文 | 免费 |
| [PMC OA Subset](https://www.ncbi.nlm.nih.gov/pmc/tools/oa-service/) | 无 | 自动化只能走 PMC Cloud / OAI-PMH / E-utilities / BioC API；**其它批量抓取禁止** | 每篇许可不同（CC BY / CC BY-NC / CC BY-NC-ND 等） | 单篇 OA 全文/摘要 | 免费 |
| [Unpaywall](https://unpaywall.org/products/api) | 必须带**真实** email 参数（占位邮箱返回 422） | 约 100,000 次/天；更大量用数据库快照 | 页面无许可声明（`feature_radar.md` 也因此未入许可矩阵） | DOI → OA 链接 | 免费 |
| [Semantic Scholar API](https://www.semanticscholar.org/product/api) | 无鉴权可用；key 提高限额 | 公共端点合计 1000 req/s（所有未鉴权用户共享，可能进一步限流）；key 入门 1 RPS | S2 Data 为 CC BY-NC 或 ODC-BY；要求署名 + 引用；**禁止转售/再分发 API** | 引用网络、SPECTER2 向量 | 免费但许可受限 |
| [arXiv API](https://info.arxiv.org/help/api/index.html) | 无 | 建议 ≤1 请求/3 秒 | arXiv 元数据；全文许可按论文 | arXiv 摘要 / 元数据 | 免费 |
| [doi.org handle](https://doi.org/api/handles/) | 无 | 无硬限 | 开放 | DOI 存在性校验（t15 30/30） | 免费 |

结论：

- **主路径**：页面参考文献条目先取出 DOI / 题名/作者/年份 → Crossref（DOI 或题名精确匹配）→ OpenAlex（摘要与引用关系）→ Europe PMC（生物医学摘要）→ arXiv（预印本）。
- **Unpaywall 只做运行时 OA 链接查询**，不把返回数据落库/再分发；其页面无许可声明，产品里要标注「第三方服务」。
- **Semantic Scholar 排除在 MVP 外**：S2 Data 的 CC BY-NC 条款与「可商用/可再分发」不确定，且公共 1000 req/s 是所有人共享；除非拿到书面许可，不进入产品核心。
- 成本：全部免费层足够 10 页 / 30 句；OpenAlex 免费 key 是可选的稳定性手段，不是必需。
- **许可证不满足、需换方案的两项**：refextract（GPL-2.0，与 Apache-2.0 产品核心不兼容）→ 换自建解析器；Semantic Scholar S2 Data（CC BY-NC / ODC-BY）→ 换 Crossref/OpenAlex/Europe PMC。这两项已从 MVP 排除。

### 4.2 对 10 页的覆盖预期

| 页面 | 参考文献可获得性 | 来源查找路径 | 风险 |
| --- | --- | --- | --- |
| arXiv ×3 | HTML 内（实测 54/126/60 条） | 页面 DOI / arXiv ID → Crossref / arXiv | 低；已有 30/30 映射 |
| PMC ×2 | HTML 内（36 条等） | Europe PMC / Crossref | 中；需新适配器 |
| Wikipedia ×1 | HTML 内（44 条） | 部分条目无 DOI → Crossref 题名查询 | 中；题名查询有噪声 |
| Nature / Springer ×2 | 扩展侧 DOM | Crossref DOI | 中；服务端抽取为 0，必须扩展 |
| MDPI ×1 | 扩展侧 DOM | Crossref DOI | 中；403 |
| PubMed ×1 | 扩展侧 DOM 或 E-utilities | Europe PMC / PubMed | 中；JS 壳 |

预期「页面能拿到参考文献列表」：arXiv 3/3、PMC 2/2、Wikipedia 1/1、出版商 3/3（仅扩展侧）、PubMed 1/1（扩展侧）；**服务端路径只有 6/10**。这正是架构要前移的原因。

## 5. 排序与匹配

现状（已在仓库中）：

- 候选来源优先级：页面参考文献（`source="page-reference"`）> OpenAlex `referenced_works` > 关键词检索；合并去重；`MAX_CANDIDATES=5`。
- 词面排序：`_page_candidate_score` 用标题覆盖 0.85 + 数字匹配 0.15（见 `docs/live_eval.md` §5.2）；t15 在 5 页 / 30 句上 **hit@1 27/30（0.9000）、hit@3 30/30（1.0000）**。
- 跨语言：跨语言集（30 句中文查询、页面与查询无关）hit@3 = 0/30；现有词面打分为 0。

候选件：

| 方案 | 许可 | 成本 | 评估 |
| --- | --- | --- | --- |
| 现有词面打分 | 自有 | 0 | **MVP 首选**；候选 ≤5 时足够，可解释 |
| [rank_bm25](https://github.com/dorianbrown/rank_bm25) 0.2.2 | Apache-2.0 | 8.5 KB wheel，依赖 numpy | 可选增强；对标题/摘要做 BM25，约 1–2 天接入 |
| [BGE-M3](https://github.com/FlagOpen/FlagEmbedding) | MIT | 约 0.6B 参数；仓库 `src/citeguard/embeddings.py` 已支持 OpenAI 兼容接口，默认 `BAAI/bge-m3` | **仅跨语言场景**值得；中文查询 vs 英文参考文献是明确缺口，但会增加模型服务与延迟 |
| [SPECTER2](https://github.com/allenai/SPECTER2) | Apache-2.0 | 需任务适配器；本机 HuggingFace 访问超时（`feature_radar.md` 已记录） | **不推荐 MVP**：下载与适配器复杂度高，收益不确定 |

可行目标（建议写进验收，而不是现在宣称）：

- 同一批 arXiv HTML 页面：hit@1 ≥ 0.85、hit@3 ≥ 0.95（现有 0.90 / 1.00，留回退空间）。
- 10 页混合集首版：hit@1 ≥ 0.60、hit@3 ≥ 0.80；扩展侧抽取 + PMC/Wikipedia 适配器稳定后，目标 hit@3 ≥ 0.90。
- 排序不是主瓶颈：t15 已经 30/30 hit@3，主要缺口是「摘要/证据不足」和「页面抽取不到」。

## 6. 浏览器扩展（MV3 side panel）

### 6.1 仓库现状

`extension/v2/manifest.json` 已经是 MV3，且**已经声明 side panel**：

- `manifest_version: 3`，`minimum_chrome_version: 116`，版本 0.2.1。
- `permissions`: `storage`、`contextMenus`、`activeTab`、`sidePanel`。
- `side_panel.default_path`: `sidepanel.html`。
- `host_permissions` 只有 `http://127.0.0.1/*`、`http://localhost/*` 及 https 对应项——**只允许访问本地服务**。
- `sidepanel.js` 约 13.3 KB；当前消息只带 `claim`、`page_url`、`page_title`，**不带页面正文**（`docs/extension_v2.md`）。

Chrome sidePanel API 自 Chrome 114+ 提供；`sidePanel.open()` 需要用户手势，`sidePanel.setPanelBehavior({openPanelOnActionClick:true})` 可让点击扩展图标直接打开。参考 [Chrome sidePanel 文档](https://developer.chrome.com/docs/extensions/reference/api/sidePanel)。

### 6.2 可复用骨架

| 骨架 | 许可 | 说明 |
| --- | --- | --- |
| 本仓库 `extension/v2` | Apache-2.0 | 最贴近：已有 side panel、本地 API、选区上下文菜单；**首选** |
| [sidepanel-extension-template](https://github.com/thatbeautifuldream/sidepanel-extension-template) | MIT | WXT + React 19 + Tailwind 4；0 stars，2025-08 创建；只作结构参考 |
| [mv3-sidebar-panel](https://github.com/theluckystrike/mv3-sidebar-panel) | 未核实 | MV3 React 模板；许可不明，不直接拷贝 |

### 6.3 MVP 还缺什么

1. **content script**：在用户当前页 DOM 上跑 Readability（或等价抽取），拿到正文段落 + 参考文献容器；只在用户点击/划词时注入。
2. **消息契约**：扩展 → 本地服务增加页面侧结构，例如 `page_html`（截断 2 MB）或 `references_html` + 已抽好的正文段落；服务端复用现有 Python 解析器，避免 JS/Python 两套解析逻辑漂移。
3. **侧栏真机验证**：此前的验证是「以普通标签页打开 sidepanel.html」，**没有验证 docked side panel 手势**；需要真实点击扩展图标/选区菜单后确认侧栏停靠。
4. **权限与隐私**：保持 `activeTab` 按需注入，不申请 `<all_urls>`；页面内容只发 `127.0.0.1`；不做历史留存；设置页可关闭「发送页面参考文献」。

### 6.4 最小实现草案

MV3 下 side panel 的最小闭环（Readability 需随扩展打包，不能用 CDN，MV3 CSP 禁止远程脚本）：

```js
// background.js（service worker）
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === 'live:page') {
    // 转发给 side panel；页面内容不出本机
    chrome.runtime.sendMessage({ type: 'live:page:ready', payload: msg });
    reply({ ok: true });
  }
  return true;
});
```

```js
// content.js —— 由用户点击/划词触发后注入，不常驻
import { Readability } from '@mozilla/readability';
const dom = document.cloneNode(true);
const article = new Readability(dom, { keepClasses: true }).parse();
const refs = document.querySelector(
  '.ltx_bibliography, section.ref-list, ol.references'
);
chrome.runtime.sendMessage({
  type: 'live:page',
  url: location.href,
  title: document.title,
  articleText: (article?.textContent || '').slice(0, 2_000_000),
  referencesHtml: (refs?.outerHTML || '').slice(0, 2_000_000),
});
```

要点：`activeTab` + 用户手势才注入；`sidePanel.open({ tabId })` 也必须在手势回调里调用；页面 HTML 到本地服务前截断并做大小校验；不申请 `<all_urls>`，不把内容发往远端。

### 6.5 结论

扩展骨架**可直接复用**，工作量集中在「抽取 + 契约 + 真机验证」，不需要新的扩展框架。`sidePanel` 权限与 `side_panel` 清单项已经就位，这一点比多数模板更接近可用。

## 7. 10 页 / 30 句 MVP 设计

### 7.1 页面与句子

| # | 页面 | 语言 | 抽取路径 | 许可 / 备注 |
| --- | --- | --- | --- | --- |
| 1 | arXiv 2611.07772 | en | 服务端 + 扩展 | CC BY 4.0 |
| 2 | arXiv 2610.38049 | en | 服务端 + 扩展 | CC BY 4.0 |
| 3 | arXiv 2610.24037 | en | 服务端 + 扩展 | CC BY-NC-SA 4.0，仅评测 |
| 4 | PMC13541550 | en | 服务端 + 扩展 | 逐篇记录许可；仓库只存 URL/句子 |
| 5 | PMC13198158 | en | 服务端 + 扩展 | 同上 |
| 6 | Wikipedia: Retrieval-augmented generation | en | 服务端 + 扩展 | CC BY-SA 4.0 |
| 7 | Nature s41586-023-06221-2 | en | **仅扩展侧** | 受 Bot 墙；仅运行时读取，不存全文 |
| 8 | Springer 10.1007/s10664-022-10241-3 | en | **仅扩展侧** | 受 Bot 墙；仅运行时读取，不存全文 |
| 9 | MDPI 14/7/406 | en | **仅扩展侧** | CC BY 4.0；服务端 403 |
| 10 | PubMed 42698590 | en | **仅扩展侧** / E-utilities | 摘要页；不存全文 |

- 30 句 = 10 页 × 3 句；其中 arXiv 3 页的 9 句直接取自现有 30 句 held-out 集（每页 3 句），其余 21 句新标，避免与已有 hit@1 0.90 过拟合。
- 选句规则：句内有显式引用标记（`[n]` / 全角 / 作者-年份），且能在页面参考文献中找到对应条目；不按「产品是否命中」筛选。
- 金标：被引条目的 DOI（优先）或题名 + 第一作者 + 年份；stance 标签可选（support / partial / contradict / no_evidence），单人标 30 句、双人复核 10 句。
- 数据只存 URL、句子、金标；**不存页面全文**（订阅/NC 页面尤其）。

### 7.2 输入与展示

- **输入**：用户在页面上选中一句话（claim，≤500 字符）；扩展自动带 `page_url`、`page_title`，以及页面参考文献 HTML（截断 2 MB）。无扩展的网页入口允许手动粘贴 claim + URL，由服务端尝试抓取。
- **展示（侧栏）**：四档标签（support / partial / contradict / no_evidence）+ 来源卡片（题名、作者/年份、DOI 链接、候选排名）+ **逐字证据句**（原文摘录 + 出处：摘要/页面参考文献/OpenAlex）；`no_evidence` 时显示「未找到可核对的来源」及原因（页面无参考文献 / 查找超时 / 无摘要），不伪造来源或证据。
- **不展示**：精确到小数点的「可信度」数字（避免伪精确）；没有证据时不给「支持」结论。
- **边界**：只把 claim 与页面参考文献发到本机 `127.0.0.1`；外部查询只发 DOI/题名；不保存页面全文，不做历史留存（除非用户显式开启）。

### 7.3 指标与门槛

| 指标 | 定义 | 首版目标 | 现状对照 |
| --- | --- | --- | --- |
| 抽取成功 | 正文 ≥500 字符、参考文献 ≥5 条、至少 1 个标记可映射 | ≥8/10 页 | 服务端 6/10；扩展侧预期 10/10 |
| hit@1 | 排名第 1 候选含金标 DOI 或题名 | ≥0.60（混合集） | arXiv 5 页 0.90 |
| hit@3 | 前 3 候选含金标 | ≥0.80，稳定后 ≥0.90 | arXiv 5 页 1.00 |
| 证据可用率 | `evidence` 非空 | ≥0.35 | t17：11/30（0.37） |
| 延迟 | p50 / p95（缓存命中，不含首次冷启动） | p50 ≤2.5 s，p95 ≤6 s；冷启动首屏 ≤5 s | t17：p50 3.0 s，p95 16.1 s（冷 + 外部 API） |
| 诚实未命中 | 无候选/无证据时明确 `no_evidence` + 原因 | 100% | 已有 |

延迟说明：t17 的 P95 16.1 s 主要来自「每句重新抓/解析 HTML + 摘要补全」；MVP 必须做页面级缓存（解析后的参考文献 + 摘要），否则不设 p95 承诺。若缓存后仍 >8 s，则把「≤8 s」作为门槛并明确标注。

### 7.4 失败降级

- 页面抽取失败 → 不猜，返回「本页无法读取参考文献」；扩展侧可提示用户重试。
- 参考文献为空 → 允许退回 OpenAlex `referenced_works` / 关键词候选，但标签必须标 `no_evidence` 或降置信。
- 来源查找超时 → 返回已有候选 + 「查找超时」，不伪造 DOI。
- 无摘要 → `has_abstract=false`，不生成证据句；`no_evidence` 是合法结果。

### 7.5 人日

| 工作 | 人日 |
| --- | ---: |
| 扩展 content script + Readability 打包 + 消息契约 | 3 |
| PMC / Wikipedia / 通用 HTML 参考文献适配器 | 4 |
| 中文/全角/作者-年份标记归一化 | 1.5 |
| Crossref / OpenAlex / Europe PMC / arXiv 客户端 + 缓存 | 3 |
| 排序（词面 + 可选 BM25）与阈值 | 1.5 |
| 10 页 / 30 句构集与标注 | 2 |
| side panel 真机验证 + 交互细节 | 1.5 |
| 测试 / 文档 | 2 |
| **合计** | **18.5（区间 15–22）** |

约「单人 3–4 周」或「两人 1.5–2 周」；不含 BGE-M3 跨语言增强（再加 3–5 人日与模型服务）。

### 7.6 Kill 条件

1. 扩展侧抽取在 10 页上 <8 页成功 → 缩小到 arXiv / PMC，**不再宣称通用网页**。
2. 混合集 hit@3 <0.80 → 停止「定位到来源」的对外表述，回到候选列表 + 人工判断。
3. 缓存后 p95 >8 s → 不上线；先砍摘要补全或改为异步。
4. 需要 `<all_urls>` 或上传页面到远端才能工作 → 隐私评审不通过，放弃出版商页面。
5. 许可不清（S2 NC、refextract GPL、PMC 批量）未替换 → 不进入产品核心。
6. 证据可用率 <20% 且无法提升 → 产品价值不足，重新评估 Live 定位。

## 8. 复用 / 自建矩阵与架构选择

### 8.1 矩阵

| 能力 | 复用 | 胶水 | 自建 |
| --- | --- | --- | --- |
| 正文抽取 | Readability 0.6.0 | 扩展注入 / jsdom | — |
| 参考文献解析 | — | — | arXiv（已有）+ 3 个适配器 |
| 标记映射 | — | — | 编号/作者-年份映射（已有 arXiv 版） |
| 来源查找 | Crossref / OpenAlex / Europe PMC / arXiv | HTTP + 缓存 | — |
| OA 链接 | Unpaywall（运行时） | email 参数 | — |
| 排序 | 现有词面 / rank_bm25 | 融合 | — |
| 跨语言 | BGE-M3（可选） | embeddings 接口 | — |
| 扩展 | extension/v2 | content script + 契约 | — |
| 评测 | 现有 5 页/30 句 | 新增 5 页/21 句 | — |

### 8.2 两种架构（A/B）与推荐落地（C）

**A. 服务端抓取（现状）**

- 做法：服务端 GET 页面 HTML → Readability/trafilatura 抽取 → 解析参考文献 → 查找 → 判定。
- 优点：实现简单、单测容易、无扩展依赖；arXiv/PMC 已验证。
- 缺点：出版商 Bot 墙（Nature/Springer/MDPI 0/3）、PubMed JS 壳、延迟高（每句重抓）、只能覆盖开放 HTML。
- 结论：**保留为开放页面与无扩展用户的兜底，不能作为唯一路径**。

**B. 扩展侧抽取（推荐作为主路径）**

- 做法：content script 在用户 DOM 上跑 Readability，取正文 + 参考文献容器；把「claim + 页面参考文献 HTML/结构化条目」发给本地服务；服务端只做查找/排序/判定。
- 优点：绕开 Bot 墙与登录态；页面内容不出本机；任意用户可读页面都能用；复用现有 Python 解析器（发 HTML 而不是在 JS 里重写解析）。
- 缺点：需要扩展改动与真机验证；`activeTab` 注入要用户手势；页面 HTML 截断与大小校验；侧栏 UX。
- 结论：**出版商/PubMed 页面的唯一可行路径**。

**C. 混合（推荐落地）**

- 服务端路径保留（arXiv / PMC / API 用户），扩展路径覆盖其余页面；两条路径共用同一套 Python 参考文献解析与查找管线。
- 新增契约建议：`POST /api/live/check` 增加可选 `page_html`（≤2 MB，截断后发送）或 `page_references`（结构化条目）；服务端标记来源为 `extension`，与 `page-reference` 区分但共用打分。
- 风险控制：先做 arXiv + PMC 的服务端评测（1 周），再接扩展（1 周）；扩展侧先用 3 页出版商页面做冒烟，不急着全量。

## 9. 逐项回答 t23 的问题

1. **页面正文抽取**：可复用 Readability（Apache-2.0）。实测 arXiv 5/5、PMC 2/2、Wikipedia 1/1 保留参考文献与标记；服务端对 Nature/Springer/MDPI 0/3、PubMed 失败。**结论：浏览器内复用；服务端只作开放页面兜底。**
2. **引用解析**：没有可直接复用的 HTML 参考文献解析器；Citation.js 只做格式转换，refextract 是 GPL + PDF/HEP，GROBID 只吃 PDF。**必须自建适配器（约 300–500 行）**；中文全角/作者-年份需扩展，约 100–150 行。
3. **来源查找**：**大部分可复用**。Crossref + OpenAlex + Europe PMC + arXiv 覆盖 DOI/题名/摘要/引用关系；Unpaywall 仅运行时 OA 链接；S2 因 CC BY-NC 与共享限流排除。全部免费层足够 MVP。
4. **排序**：候选 ≤5 时现有词面打分已够（hit@1 0.90 / hit@3 1.00）；BM25 可选；BGE-M3 仅跨语言场景值得；SPECTER2 不推荐。**排序不是瓶颈。**
5. **扩展**：`extension/v2` 已是 MV3 + sidePanel（Chrome 116+，`side_panel.default_path` 就位，host 仅 localhost）；缺 content script、页面契约、侧栏真机验证。**骨架可直接复用。**
6. **10 页 / 30 句 MVP**：页面组合、指标、降级、人日见 §7；合计约 18.5 人日（15–22），p50 ≤2.5 s / p95 ≤6 s（缓存后），否则降到 ≤8 s 并标注。
7. **必须自建 vs 直接复用**：自建 = 参考文献适配器 + 标记映射（含中文）+ 扩展 content script/契约；复用 = Readability、Crossref/OpenAlex/Europe PMC/arXiv、现有词面排序、extension/v2、现有 30 句评测。**许可证层面无阻塞**（排除 GPL 的 refextract 与 NC 的 S2）。

**推荐**：C 混合架构，先服务端把 PMC/Wikipedia 适配器与 10 页评测做出来，再把扩展侧抽取接上；出版商页面只在扩展侧承诺，服务端不承诺。

## 10. 未验证 / 诚实边界

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 中文页面抽取 | 未验证 | Wikimedia 两次 429；中文标记归一化为设计判断 |
| Readability 浏览器内注入 | 未单独验证 | 用 jsdom 跑同一 0.6.0 包；扩展 CSP/打包方式未真机验证 |
| 出版商页面扩展侧抽取 | 未验证 | 只有服务端 Bot 墙实测；扩展 DOM 路径需真机 |
| side panel 停靠手势 | 未验证 | 此前只以普通标签页打开 sidepanel.html |
| 10 页 / 30 句集 | 未构建 | 本任务只做调研，不写数据文件 |
| stance 金标 | 无 | 与 t15 一致，只做来源命中，不宣称判定准确率 |
| 外部 AI 客户端 / 截图 | 不涉及 | 本任务不产生客户端验证结论 |

## 11. 复现

临时目录（未入库）：

```powershell
$tmp = Join-Path $env:TEMP 'cg_live_stack'
New-Item -ItemType Directory -Force $tmp | Out-Null
Set-Location $tmp
npm install --no-audit --no-fund @mozilla/readability@0.6.0 jsdom defuddle
```

抽取脚本（ESM，Readability 与 Defuddle 对比；完整脚本见临时目录 `extract.mjs`，思路如下）：

```js
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { JSDOM } = require('jsdom');
const { Readability } = require('@mozilla/readability');
const html = fs.readFileSync(process.argv[2], 'utf8');
const dom = new JSDOM(html, { url: 'https://example.org/page' });
const art = new Readability(dom.window.document, { keepClasses: true }).parse();
console.log(JSON.stringify({ title: art?.title, text: art?.textContent.length }));
```

下载与统计命令（UA 与页面列表见 §2.2）用 `Invoke-WebRequest`；仓库内已有 Live 测试基线：

```powershell
cd D:\ai+ky\citeguard
$env:PYTHONPATH='src'
python -m pytest tests/test_live_check.py tests/test_live_page.py tests/test_live_eval.py -q
# 2026-11-16 实测：62 passed in 10.40s
```

仓库内相关文档：[docs/live.md](../live.md)、[live_holdout.md](live_holdout.md)、[live_eval.md](../live_eval.md)、[extension_v2.md](../extension_v2.md)、[feature_radar.md](feature_radar.md)。

## 12. 参考链接与许可

| 件 / 服务 | 链接 | 版本 | 许可 / 条款 | 成本 |
| --- | --- | --- | --- | --- |
| Mozilla Readability | https://github.com/mozilla/readability | 0.6.0 | Apache-2.0 | 免费 |
| Defuddle | https://github.com/kepano/defuddle | 0.19.6 | MIT | 免费 |
| Citation.js | https://github.com/citation-js/citation-js | 0.9.0 | MIT | 免费 |
| refextract | https://github.com/inspirehep/refextract | 1.1.7 | GPL-2.0-or-later（排除） | 免费（GPL，排除） |
| GROBID | https://github.com/grobidOrg/grobid | 活跃 | Apache-2.0 | 免费（自托管） |
| trafilatura | https://github.com/adbar/trafilatura | 2.3.1 | Apache-2.0 | 免费 |
| rank_bm25 | https://github.com/dorianbrown/rank_bm25 | 0.2.2 | Apache-2.0 | 免费 |
| BGE-M3 | https://github.com/FlagOpen/FlagEmbedding | — | MIT | 模型免费；推理资源另计 |
| SPECTER2 | https://github.com/allenai/SPECTER2 | — | Apache-2.0 | 模型免费；需适配器 |
| Crossref REST | https://api.crossref.org/ | — | 元数据开放，摘要可能受版权 | 免费 |
| OpenAlex | https://docs.openalex.org/ | — | 数据 CC0 | 免费层（key 可选） |
| Europe PMC | https://www.ebi.ac.uk/europepmc/webservices/rest | — | 开放；禁止非 OA 批量 | 免费 |
| PMC OA | https://www.ncbi.nlm.nih.gov/pmc/tools/oa-service/ | — | 逐篇许可；限定自动化入口 | 免费（限入口） |
| Unpaywall | https://unpaywall.org/products/api | — | 页面无许可声明；仅运行时 | 免费（需真实 email） |
| Semantic Scholar | https://www.semanticscholar.org/product/api | — | S2 Data CC BY-NC / ODC-BY，禁止转售 | 免费（许可受限，排除） |
| arXiv API | https://info.arxiv.org/help/api/index.html | — | 建议 ≤1 请求/3 秒 | 免费 |
| Chrome sidePanel | https://developer.chrome.com/docs/extensions/reference/api/sidePanel | Chrome 114+ | Chrome 扩展 API | 免费（Chrome 114+） |
| sidepanel 模板 | https://github.com/thatbeautifuldream/sidepanel-extension-template | — | MIT | 免费（MIT） |

## 13. 文件

- 本文件：`docs/research/live_stack.md`（唯一交付物）
- 未改：`src/`、`web/`、`extension/`、`scripts/`、`tests/`
