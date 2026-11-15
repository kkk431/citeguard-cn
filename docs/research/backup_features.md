# 备用功能开源资源充分性矩阵（E5 / t24）

> 调研日期：2026-11-16。只做调研，不改产品代码。
> 定位：E4（`docs/research/feature_feasibility.md`）回答“Live/CiteMap 能不能做成”；本文件回答“**如果它们资源不够/时间不够，还有哪些功能能用现有开源件顶上**”。两者不重复：E4 是主亮点选型，E5 是备选池与 kill criteria。
> 结论：**优先备份 C3 引用推荐/替换（4–6 人日，复用 438 条评测）、C1 审稿辅助（8–10 人日，复用证据矩阵）、C6 数据集/评测/API 开放服务（3–5 人日，补开放成果）**；C7 浏览器引用收集器是 3–4 人日的快速补位。人日为**估算**（±40%），不确定项写“未验证”。

## 0. 一页结论

| 排名 | 候选 | 估算人日 | 评分项 | 复用度 | go/no-go | kill criteria（摘要） |
|---|---|---|---|---|---|---|
| 1 | C3 引用推荐/替换 | 4–6 | 完成度/创新 | 高（438 查询/477 候选 + 脚本） | **GO** | 438 条 R@3 <0.30 或较 BM25 增益 <+0.02；单查询 >2 s |
| 2 | C1 审稿辅助（审稿单） | 8–10 | 创新/完成度 | 高（证据矩阵/五维分/verification_packet） | **GO（有条件）** | 20 条人工断言抽取 P <0.60；DOCX 流程 >8 人日 |
| 3 | C6 数据集/评测/API 开放服务 | 3–5 | 开放成果/材料 | 高（CiteBench 500/ClaimSupport 300/Live 两套 30 句） | **GO** | 数据卡/许可 3 天内定不下来；无稳定托管 |
| 4 | C7 浏览器引用收集器 | 3–4 | 易用性 | 高（扩展 v2 + 题录库） | GO（备选） | 20 页 DOI 抽取准确率 <70%；>4 人日 |
| 5 | C2 表格/图表抽取 | 6–8 | 创新/完成度 | 中（22 篇 PDF/页映射） | 有条件 | 20 张表 cell F1 <0.60；单篇耗时 >3× 现状 |
| 6 | C5 团队题录库/投稿流程 | 7–9 | 易用性/完成度 | 高（408 条题录/GB-T 100 条） | 有条件 | 导入→核验→导出 >8 人日；权限模型要重写 |
| 7 | C4 综述/带引用草稿 | 6–8 | 创新 | 低（无中文长文数据） | 降级 | 引用解析率 <95%；30 句事实抽检错误 >10% |
| 8 | C8 Word/Office 审稿窗格 | 6–8 | 易用性 | 中（本地 API/DOCX 导出） | 降级 | 必须云端托管或 >6 人日；Word 侧载不可用 |

## 1. 矩阵（候选 × 资源 × 许可证 × 人日 × 评分项 × 风险）

人日为该项工作量的**估算**；“评分项”指最能支撑的评审维度（15 问题场景 / 20 创新 / 20 AI+开源 / 25 完成度 / 15 开放成果 / 5 材料）。

| 候选 | 资源（名称+版本） | 许可证（来源链接） | 人日（估算） | 评分项 | 风险 |
|---|---|---|---|---|---|
| C1 审稿辅助 | GROBID 0.9.0 | Apache-2.0（[仓库](https://github.com/grobidOrg/grobid)） | 2–3 | 完成度 | 扫描件/中文混排弱 |
| C1 审稿辅助 | Docling 2.150.1 | MIT（[PyPI](https://pypi.org/project/docling/)） | 2 | 完成度 | 引用解析非主项 |
| C1 审稿辅助 | FActScore（仓库 HEAD） | MIT（[仓库](https://github.com/shmsw25/FActScore)） | 2–3 | 创新 | 需 LLM；英文基准 |
| C1 审稿辅助 | RefChecker（仓库 HEAD） | Apache-2.0（[仓库](https://github.com/amazon-science/refchecker)） | 2–3 | 创新 | 需 LLM；中文未验证 |
| C1 审稿辅助 | SciFact（2020） | claims CC BY 4.0 / corpus ODC-By 1.0（[LICENSE](https://github.com/allenai/scifact/blob/master/LICENSE.md)） | 0.5 | 证据 | 英文生物医学域 |
| C1 审稿辅助 | python-docx 1.2.0 | MIT（[PyPI](https://pypi.org/project/python-docx/)） | 1 | 材料 | Word 批注能力有限 |
| C2 表格/图表抽取 | Docling 2.150.1（内置 TableFormer，权重许可未验证） | MIT（[PyPI](https://pypi.org/project/docling/)） | 2–3 | 完成度 | 中文表格精度未验证 |
| C2 表格/图表抽取 | pdfplumber 0.11.10 | MIT（[PyPI](https://pypi.org/project/pdfplumber/)；仓库本网络暂不可达） | 1 | 完成度 | 复杂合并单元格弱 |
| C2 表格/图表抽取 | Camelot 2.0.0 | MIT（[PyPI](https://pypi.org/project/camelot-py/)） | 1 | 完成度 | 依赖 Ghostscript/OpenCV |
| C2 表格/图表抽取 | MinerU（仓库 HEAD） | Apache-2.0 + 附加条款（[仓库](https://github.com/opendatalab/MinerU)） | 2–3 | 创新 | 商用阈值；依赖重 |
| C2 表格/图表抽取 | ChartCheck 数据（2023） | MIT（[数据仓库](https://github.com/mubasharaak/chartfc_dataset_wikicommons)） | 0.5 | 证据 | 英文图表 claim |
| C2 表格/图表抽取 | CharXiv（2024） | **未验证**（[项目页](https://charxiv.github.io/)） | 0.5 | 证据 | 许可未核；图表理解需 VLM |
| C3 引用推荐/替换 | OpenAlex API | CC0（[FAQ](https://ourresearch.gitbook.io/help.openalex.org/faq)） | 1 | 完成度 | 中文社科覆盖低 |
| C3 引用推荐/替换 | Crossref REST | 开放（[文档](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)） | 0.5 | 完成度 | 参考文献字段稀疏 |
| C3 引用推荐/替换 | BGE-M3（已接入） | MIT（[FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding)） | 0.5 | 完成度 | 语义上限；477 池 R@3 0.3219 |
| C3 引用推荐/替换 | SPECTER2（仓库 HEAD） | Apache-2.0（[仓库](https://github.com/allenai/specter2)） | 1–2 | 创新 | 权重卡未验证；英文为主 |
| C3 引用推荐/替换 | T2Retrieval（2023） | Apache-2.0（[任务页](https://leaderboard.mteb.org/tasks/T2Retrieval)） | 0.5 | 证据 | 中文 web QA 域，非论文 |
| C4 综述/带引用草稿 | ALCE（2023） | MIT（[仓库](https://github.com/princeton-nlp/ALCE)） | 1 | 创新 | 数据集底层许可未验证；英文 |
| C4 综述/带引用草稿 | PaperQA2（仓库 HEAD） | Apache-2.0（[仓库](https://github.com/Future-House/paper-qa)） | 3–4 | 创新 | 需自备 LLM/embedding |
| C4 综述/带引用草稿 | OpenScholar（仓库 HEAD） | Apache-2.0（[仓库](https://github.com/AkariAsai/OpenScholar)） | 4+ | 创新 | 8B 模型+检索，超窗口 |
| C4 综述/带引用草稿 | LongCite-45k（2024） | Apache-2.0（[仓库](https://github.com/THUDM/LongCite)） | 1–2 | 证据 | 长上下文训练成本 |
| C4 综述/带引用草稿 | AttributionBench | **未验证**（[仓库](https://github.com/osu-nlp-group/AttributionBench) 无许可字段） | 0.5 | 证据 | 许可不明，不能作主证据 |
| C5 团队题录库 | SQLite（3.x） | Public Domain（[版权页](https://www.sqlite.org/copyright.html)） | 1 | 完成度 | 并发/多用户弱 |
| C5 团队题录库 | FastAPI 0.163.1 | MIT（[PyPI](https://pypi.org/project/fastapi/)） | 1.5 | 完成度 | 需鉴权/部署 |
| C5 团队题录库 | CSL styles（含 GB/T 7714） | CC BY-SA 3.0（[仓库](https://github.com/citation-style-language/styles)） | 1 | 完成度 | 字段映射调试 |
| C5 团队题录库 | ORCID 公共 API | 条款**未验证**（[expanded-search 端点](https://pub.orcid.org/v3.0/expanded-search/)） | 1 | 开放成果 | 需注册客户端；速率限制 |
| C5 团队题录库 | Zotero Web API v3 | API 条款**未验证**（[文档](https://www.zotero.org/support/dev/web_api/v3/start)）；代码 AGPL-3.0 不打包 | 1 | 完成度 | 代码许可与产品不兼容 |
| C6 数据集/API 服务 | FastAPI 0.163.1 | MIT（[PyPI](https://pypi.org/project/fastapi/)） | 1 | 开放成果 | 需托管 |
| C6 数据集/API 服务 | Zenodo | 平台条款（[terms](https://about.zenodo.org/terms/)）；每条记录许可由上传者选择 | 0.5 | 开放成果 | DOI 注册需审核 |
| C6 数据集/API 服务 | 自有 CiteBench-CN 500 / ClaimSupport-CN 300 | CC BY 4.0（见 `docs/licenses.md`） | 1 | 开放成果 | 构造标签，非人工金标 |
| C7 浏览器引用收集器 | Readability.js 0.6.0 | Apache-2.0（[npm](https://registry.npmjs.org/@mozilla/readability/latest)） | 0.5 | 易用性 | 页面结构差异 |
| C7 浏览器引用收集器 | citation-js 0.9.0 | MIT（[npm](https://registry.npmjs.org/citation-js/latest)） | 1 | 易用性 | GB/T 细节需 CSL |
| C7 浏览器引用收集器 | Crossref content negotiation | 开放（[文档](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)） | 0.5 | 完成度 | DOI 缺失时回退标题检索 |
| C7 浏览器引用收集器 | 扩展 v2（已有 MV3） | 自有代码 Apache-2.0 | 已具备 | 易用性 | 商店上架不做 |
| C8 Word/Office 审稿窗格 | Office Add-ins（平台） | 平台条款（[文档](https://learn.microsoft.com/en-us/office/dev/add-ins/)） | 3–4 | 易用性 | 需 HTTPS/侧载，Linux 不可用 |
| C8 Word/Office 审稿窗格 | python-docx 1.2.0 | MIT（[PyPI](https://pypi.org/project/python-docx/)） | 1.5 | 材料 | 批注/修订支持有限 |
| C8 Word/Office 审稿窗格 | mammoth 1.13.0 | BSD-2-Clause（[PyPI](https://pypi.org/project/mammoth/)） | 0.5 | 材料 | 只读转换 |
| C8 Word/Office 审稿窗格 | LibreOffice（官网 licenses 页） | MPL-2.0（[页面](https://www.libreoffice.org/about-us/licenses/)） | 1 | 材料 | 无头转换稳定性 |

## 2. 逐个候选

### C1 审稿辅助：把断言/图表/引用一致性打包成审稿单

- **用户问题**：审稿人/导师拿到 PDF，需要 10 分钟内判断“核心断言有没有证据、引用是否真实、图表和正文是否对得上”，现在只能人工翻。
- **资源**：GROBID 0.9.0（Apache-2.0，[仓库](https://github.com/grobidOrg/grobid)）抽头信息/参考文献；Docling 2.150.1（MIT，[PyPI](https://pypi.org/project/docling/)）抽版面；FActScore（MIT，[仓库](https://github.com/shmsw25/FActScore)）原子事实；RefChecker（Apache-2.0，[仓库](https://github.com/amazon-science/refchecker)）claim-evidence 三元组；SciFact（[LICENSE](https://github.com/allenai/scifact/blob/master/LICENSE.md)）做 stance 对照；python-docx 1.2.0（MIT，[PyPI](https://pypi.org/project/python-docx/)）导出审稿单。
- **成熟度**：GROBID 0.9.0（5,230★，pushed 2026-11-14 活跃）；Docling 2.150.1（70,611★，2026-11-15 活跃）；FActScore EMNLP 2023（462★）；RefChecker 2024。成熟度：**高**（解析）/ **中**（中文事实核查需实测）。
- **可复用现有资产**：`data/evidence_map/verification_packet.json`、`data/experiments/real_mutation_eval.json`、五维健康分、`data/evidence_map/verification.json`、页面证据视图（17/18）。
- **2–3 周 MVP**：输入 1 篇 PDF → 抽 20 条核心断言 → 每条给“有证据/部分/无证据/待核实”+ 证据引文 + 引用真实性（DOI/撤稿）→ 图表清单与图注计数（不做图像理解）→ 导出 DOCX 审稿单（红黄绿 + 页码）。
- **差异化/评分对应**：把“引用健康分”从工作台变成**可交付物**（审稿单），对应 20 创新 + 25 完成度；评委现场看一份带证据的 DOCX。
- **资源缺口**：图表语义一致性需要 VLM（未验证/未选型）；stance 无人工金标；中文 PDF 解析精度需实测。
- **go/no-go**：有条件 GO（8–10 人日）。
- **Kill criteria**：20 条人工断言抽取 precision <0.60；或 DOCX 审稿单流程 >8 人日；或中文 PDF 参考文献解析失败率 >40%。

### C2 表格与图表抽取（Docling/TableFormer 等）

- **用户问题**：中文论文的表格与图注是证据地图的关键，但现有页级证据只到段落；审稿单也需要“表 3 与正文数字是否一致”。
- **资源**：Docling 2.150.1（MIT，[PyPI](https://pypi.org/project/docling/)；内置 TableFormer，**模型权重许可未验证**）；pdfplumber 0.11.10（MIT，[PyPI](https://pypi.org/project/pdfplumber/)）；Camelot 2.0.0（MIT，[PyPI](https://pypi.org/project/camelot-py/)）；MinerU（Apache-2.0 + 附加条款，[仓库](https://github.com/opendatalab/MinerU)）；ChartCheck 数据（MIT，[数据仓库](https://github.com/mubasharaak/chartfc_dataset_wikicommons)）；CharXiv（[项目页](https://charxiv.github.io/)，许可未验证）。
- **成熟度**：Docling 2.150.1 活跃；MinerU 83,699★；pdfplumber 0.11.10、Camelot 2.0.0 长期维护；ChartCheck ACL 2024 Findings。成熟度：**中高**（英文表格）/ **中**（中文表格未验证）。
- **可复用现有资产**：`data/real_corpus` 22 篇 PDF、`data/experiments/refs_layout_pdfium_parity.json`、`refs_layout_selection.json`、页映射 17/18、`figure_prompt_eval*.json` 的图表评测口径。
- **2–3 周 MVP**：22 篇 PDF 批量抽表 → CSV/HTML + 表题绑定 → 20 张表人工抽检 cell 精度 → 正文数字与表格数字冲突检测（规则）→ 输出“表格证据卡”。
- **差异化/评分对应**：把证据从“句子”扩到“表格/图注”，对应 20 创新 + 15 问题场景；对中文期刊 PDF 有区分度。
- **资源缺口**：中文表格精度未知；ChartFormer/ChartCheck 只有英文；VLM 图表理解未选型（许可/算力）。
- **go/no-go**：有条件（6–8 人日，先做表格，不做图像理解）。
- **Kill criteria**：20 张表 cell F1 <0.60；或单篇解析耗时 >3× 现状；或表题绑定错误率 >30%。

### C3 引用推荐/替换（现有 replacement + 检索）

- **用户问题**：写作时“这句话该引哪篇”，或现有引用不相关需要替换；也是五维分里“相关性/覆盖”的直接修复动作。
- **资源**：OpenAlex（CC0，[FAQ](https://ourresearch.gitbook.io/help.openalex.org/faq)）、Crossref（开放，[文档](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)）、BGE-M3（MIT，[FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding)）、SPECTER2（Apache-2.0，[仓库](https://github.com/allenai/specter2)）、T2Retrieval（Apache-2.0，[任务页](https://leaderboard.mteb.org/tasks/T2Retrieval)）做外部 sanity。
- **成熟度**：OpenAlex 大型开放索引（CC0）；BGE-M3 已接入产品；SPECTER2 145★（2026-02-24）；T2Retrieval 为 MTEB 任务页维护中。成熟度：**高**（组件）/ **中**（中文论文候选池仅 477）。
- **可复用现有资产**：`data/experiments/replacement_eval_dataset.json`（438 查询/477 候选）、`replacement_eval.json`（BGE-M3 R@1/R@3/MRR 0.1986/0.3219/0.2948；BM25 0.1872/0.2580/0.2428；title 0.1712/0.2329/0.2245）、`scripts/eval_replacement.py`、`search_recall.json`、`discover_ndcg.json`。
- **2–3 周 MVP**：输入 claim/上下文 → 候选 top-5（标题/DOI/为什么：证据句）→ 一键替换并生成 GB/T 引用 → 在 438 条上回归（R@3、MRR、延迟）→ 页面展示“替换前后相关性分”。
- **差异化/评分对应**：复用度最高、数字现成；对应 25 完成度 + 15 问题场景；评委可现场点“换一篇”。
- **资源缺口**：477 条是小池子，不是生产索引；中文元数据覆盖低；无人工相关性金标（现为构造查询）。
- **go/no-go**：**GO（首选备份，4–6 人日）**。
- **Kill criteria**：438 条 R@3 <0.30；或较 BM25 R@3 增益 <+0.02；或单查询延迟 >2 s；或替换后引用格式错误率 >5%。

### C4 文献综述/带引用草稿（ALCE/AttributionBench 类）

- **用户问题**：给定主题生成一段“每句带引用”的综述初稿，减少编造引用；CiteMap 的自然延伸。
- **资源**：ALCE（MIT，[仓库](https://github.com/princeton-nlp/ALCE)）、PaperQA2（Apache-2.0，[仓库](https://github.com/Future-House/paper-qa)）、OpenScholar（Apache-2.0，[仓库](https://github.com/AkariAsai/OpenScholar)）、LongCite-45k（Apache-2.0，[仓库](https://github.com/THUDM/LongCite)）、AttributionBench（**许可未验证**，[仓库](https://github.com/osu-nlp-group/AttributionBench)）。
- **成熟度**：ALCE EMNLP 2023；PaperQA2 9,603★（2026-11-09 活跃）；OpenScholar 1,690★（NeurIPS 2024 D&B）；LongCite 523★。成熟度：**中**（研究原型，需自备 LLM/embedding）。
- **可复用现有资产**：CiteMap 的 2 主题 × 15 篇清单、claim/evidence 抽取、citation-js/CSL、本地题录库（408 条）。
- **2–3 周 MVP**：主题 → 大纲 → 每节 3–5 句带 [n] → 引用解析到本地元数据（不存在则拒绝输出）→ 导出 MD/DOCX；只做 2 个主题。
- **差异化/评分对应**：20 创新；但事实性风险高，容易变成“看起来像综述”。
- **资源缺口**：ALCE 是英文；中文长文事实性无金标；PaperQA2/OpenScholar 需 LLM/embedding，成本与稳定性未测；AttributionBench 许可不明。
- **go/no-go**：降级（6–8 人日，放在 C1/C3 之后）。
- **Kill criteria**：引用解析率 <95%（出现无法解析的 [n]）；30 句人工事实抽检错误 >10%；或生成 1 节耗时 >60 s 且不可缓存。

### C5 机构/团队题录库与投稿工作流

- **用户问题**：课题组共享题录、投稿前统一 GB/T 格式、批量查撤稿/重复；个人工具（EndNote/Zotero）不共享核验结果。
- **资源**：SQLite（Public Domain，[版权页](https://www.sqlite.org/copyright.html)）、FastAPI 0.163.1（MIT，[PyPI](https://pypi.org/project/fastapi/)）、CSL styles（CC BY-SA 3.0，[仓库](https://github.com/citation-style-language/styles)）、ORCID 公共 API（条款未验证，[expanded-search 端点](https://pub.orcid.org/v3.0/expanded-search/)）、Zotero Web API v3（条款未验证，[文档](https://www.zotero.org/support/dev/web_api/v3/start)；代码 AGPL-3.0，不打包）。
- **成熟度**：SQLite / FastAPI 生产级；CSL styles 社区长期维护；ORCID/Zotero API 接口稳定但条款未核。成熟度：**高**（基础件）/ **中**（多用户集成）。
- **可复用现有资产**：`data/experiments/library_real.json`（409 条题录，Exact 405、Minor 4、field mismatch 4）、`verify_real.json`（125/87/197/0 → 405/4/0/0）、GB/T 100 条真实参考文献（类型码 100/100、必备字段 98.4%）、`data/real_corpus`。
- **2–3 周 MVP**：团队库 CRUD（导入 DOI/PDF）→ 批量核验（题录库/Crossref/OpenAlex）→ 统一 GB/T 导出 DOCX → 撤稿/重复提醒；单团队、无 SSO。
- **差异化/评分对应**：易用性 + 完成度；不如 C1 亮眼，但落地稳。
- **资源缺口**：多用户鉴权/并发要新写；ORCID/Zotero 条款未核；CNKI/Wanfang 导入不可再分发。
- **go/no-go**：有条件（7–9 人日）。
- **Kill criteria**：导入→核验→导出闭环 >8 人日；或权限模型迫使重写；或 GB/T 导出字段错误率 >5%。

### C6 数据集/评测/API 开放服务

- **用户问题**：评委/社区要复现评测（CiteBench-CN 500、ClaimSupport-CN 300、Live 两套 30 句），现在只有仓库脚本；开放成果分需要“可获取、可复现”。
- **资源**：FastAPI 0.163.1（MIT，[PyPI](https://pypi.org/project/fastapi/)）、Zenodo（[terms](https://about.zenodo.org/terms/)，每条记录许可由上传者定）、自有数据 CC BY 4.0（见 `docs/licenses.md`）、`scripts/eval_live.py`/`scripts/eval_replacement.py`。
- **成熟度**：FastAPI 生产级；Zenodo 长期托管；自有数据已生成并本地可复现。成熟度：**高**（低风险加分项）。
- **可复用现有资产**：`data/citebench_cn`（500 条 8 类）、`data/claimsupport_cn`（300 条）、`data/live_eval`（两套 30 句 + pages）、`docs/model_card_support_lora.md`、`docs/research/ablation_matrix.md`。
- **2–3 周 MVP**：数据集卡 + 评测 CLI + 一个只读 FastAPI（`/health`、`/citebench/eval` 示例、`/live/eval` 示例），Docker Compose 一键起；不上公网也要能本地跑。
- **差异化/评分对应**：15 开放成果 + 5 材料；风险最低的“加分项”。
- **资源缺口**：无公网托管；Zenodo DOI 审核周期；派生数据的许可兼容要逐项核。
- **go/no-go**：**GO（3–5 人日）**。
- **Kill criteria**：数据卡/许可 3 天内定不下来；或必须依赖公网托管而无法提供；或评测 CLI 与现有脚本结果不一致。

### C7 浏览器引用收集器（Live 的窄版）

- **用户问题**：网页/PDF 看到文献，一键抓元数据入库并生成 GB/T 引用；比 Live 判定更窄、更容易做对。
- **资源**：Readability.js 0.6.0（Apache-2.0，[npm](https://registry.npmjs.org/@mozilla/readability/latest)）、citation-js 0.9.0（MIT，[npm](https://registry.npmjs.org/citation-js/latest)）、Crossref content negotiation（开放，[文档](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)）、扩展 v2（已有 MV3）。
- **成熟度**：Readability.js 11,547★（2026-08-04）；citation-js 214★（0.9.0）；扩展 v2 已实现 MV3。成熟度：**高**。
- **可复用现有资产**：`extension/` v2、`data/experiments/library_real.json`、`metadata_verify`、GB/T CSL。
- **2–3 周 MVP**：右键“收藏引用” → 从页面抽 DOI/标题 → Crossref/OpenAlex 补全 → 预览 GB/T → 存本地库 → 去重提示。
- **差异化/评分对应**：易用性；评委 30 秒能看懂。
- **资源缺口**：页面元数据质量参差；无云同步；重复检测规则要调。
- **go/no-go**：GO（备选，3–4 人日）。
- **Kill criteria**：20 页 DOI/标题抽取准确率 <70%；或 >4 人日；或与现有扩展消息通道冲突需重构。

### C8 Word/Office 审稿窗格

- **用户问题**：在 Word 里直接看引用健康分/证据，不切网页；投稿前最后一公里。
- **资源**：Office Add-ins 平台（[文档](https://learn.microsoft.com/en-us/office/dev/add-ins/)）、python-docx 1.2.0（MIT，[PyPI](https://pypi.org/project/python-docx/)）、mammoth 1.13.0（BSD-2-Clause，[PyPI](https://pypi.org/project/mammoth/)）、LibreOffice（MPL-2.0，[页面](https://www.libreoffice.org/about-us/licenses/)）。
- **成熟度**：Office Add-ins 平台成熟；python-docx 1.2.0；mammoth 1.13.0；LibreOffice 长期维护。成熟度：**中**（平台可用，侧载/托管条件未验证）。
- **可复用现有资产**：本地 FastAPI 服务、`check_claim`/健康分、DOCX 导出经验、`data/experiments/e7_usability.json`。
- **2–3 周 MVP（两条路）**：
  - A：Office.js 任务窗格 → 读选区 → 调本地 API → 显示 label/evidence；需 HTTPS/侧载。
  - B（降级）：上传 DOCX → 后端解析 → 返回带批注/高亮的 DOCX；不依赖 Office.js。
- **差异化/评分对应**：易用性（评委熟悉 Word）；但实现风险最高。
- **资源缺口**：Office.js 侧载/托管要求；Linux 无 Word；python-docx 批注支持有限；LibreOffice 转换稳定性未测。
- **go/no-go**：降级（6–8 人日；优先 B 路线）。
- **Kill criteria**：侧载必须云端托管且 3 天内搭不好；或 B 路线 DOCX 批注错位率 >10%；或 >6 人日。

## 3. 三个推荐备选（按 ROI）

### 3.1 第一备选：C3 引用推荐/替换（4–6 人日，GO）

- **为什么**：唯一有现成同集评测与基线（438 查询/477 候选；BGE-M3 R@3 0.3219 vs BM25 0.2580），改动小、收益直接（相关性/覆盖两维），演示动作清楚（“这句话换一篇更相关的”）。
- **2–3 周范围**：候选 top-5 + 证据句 + 一键替换 + GB/T 输出；不做生产级索引。
- **评分对应**：完成度 25 / 问题场景 15。
- **Kill**：R@3 <0.30；较 BM25 增益 <+0.02；单查询 >2 s；替换后格式错误 >5%。

### 3.2 第二备选：C1 审稿辅助（8–10 人日，有条件 GO）

- **为什么**：把已有的证据矩阵/五维分/verification_packet 打包成评委看得懂的 DOCX 审稿单，差异化强；不需要新模型（FActScore/RefChecker 可选）。
- **2–3 周范围**：1 篇 PDF → 20 条断言 → 证据/引用真实性 → DOCX 审稿单；图表只做清单与图注计数。
- **评分对应**：创新 20 / 完成度 25。
- **Kill**：断言抽取 P <0.60；DOCX 流程 >8 人日；中文参考文献解析失败率 >40%。

### 3.3 第三备选：C6 数据集/评测/API 开放服务（3–5 人日，GO）

- **为什么**：开放成果 15 分是“确定性加分”，现有数据已齐（CiteBench 500、ClaimSupport 300、Live 两套 30 句、t20 矩阵）；只需数据卡 + CLI + 最小 API。
- **2–3 周范围**：数据卡/许可、评测 CLI、只读 FastAPI、Docker Compose；不做公网多租户。
- **评分对应**：开放成果 15 / 材料 5。
- **Kill**：许可/数据卡 3 天定不下来；无稳定本地运行方式；CLI 与现有 JSON 结果不一致。

> 快速补位：若只剩 3–4 人日，做 **C7 浏览器引用收集器**（易用性），不要把 C8 放进来。

## 4. 许可证边界与拒绝项

| 资源 | 许可 | 处理 |
|---|---|---|
| GROBID / Docling / pdfplumber / Camelot / citation-js / Readability / python-docx / mammoth / FastAPI | Apache-2.0 / MIT / BSD-2 | 可进核心镜像，保留声明 |
| MinerU | Apache-2.0 + 附加条款 | 商用阈值 MAU 1 亿/月营收 2000 万美元；演示可用，商用需法务 |
| CSL styles | CC BY-SA 3.0 | 样式文件单独分发；不改产品代码 |
| SciFact / ChartCheck / 自有数据集 | CC BY 4.0 / ODC-By / CC BY 4.0 | 署名；构造标签要标注 |
| Zotero 代码 | AGPL-3.0 | **不打包**；只用 Web API（条款未验证） |
| refextract | GPL-2.0 | **不用** |
| PyMuPDF / SingleFile | AGPL-3.0 | **不用**（已隔离为可选） |
| AttributionBench | 无许可字段 | 只作阅读参考，不进产品/评测 |
| CharXiv / TableFormer 权重 / ORCID / Zenodo 记录许可 | 未验证 | 用前逐项核；未核不写进产品依赖 |

## 5. 未验证清单

1. Docling 内置 TableFormer 模型权重的许可（代码 MIT，权重卡未核）。
2. pdfplumber 仓库 LICENSE（PyPI 元数据 license 为空；本网络 GitHub 暂不可达）。
3. CharXiv 数据许可（项目页可开，许可未写）。
4. ALCE 底层数据集（ASQA/QAMPARI/ELI5）的许可。
5. AttributionBench 许可（仓库无 license 字段）。
6. ORCID 公共 API 条款/客户端注册要求。
7. Zotero Web API 条款与速率限制。
8. Zenodo 记录级许可与 DOI 审核周期。
9. Office Add-ins 侧载/托管的具体要求（企业租户策略）。
10. MinerU 版本号（仓库未打语义化 tag）。
11. SPECTER2 权重卡许可（代码 Apache-2.0，权重未核）。

## 6. 核实记录

- 日期：2026-11-16；方法：PyPI JSON（版本/许可字段）、npm registry、rubygems、官方页面（LibreOffice/Zenodo/ORCID/Zotero/CharXiv）、GitHub 仓库（此前已核）。
- 本网络限制：huggingface.co 不可达；github.com 时通时断（本次部分 000），故以 PyPI/npm/官方页为主，GitHub 仅作代码/许可指针，未逐行核 LICENSE 的项已写“未验证”。
- 本文件仅为调研；未下载模型、未跑 GPU、未改 `src/`/`web/`。

## 7. 文件

- 本文件：`docs/research/backup_features.md`
- 相关：`docs/research/feature_feasibility.md`（E4 主选型）、`docs/research/feature_radar.md`（E1 候选矩阵）、`docs/research/ablation_matrix.md`（t20 证据）
