# 开放数据集与技术雷达：CiteMap 与 CiteGuard Live

> 面向 CiteMap（B1，多篇论文 claim/evidence/stance/gap 证据地图）与 CiteGuard Live（B2，边读边核验）的开放数据与技术候选矩阵。
> 本页包含 37 个候选、6 个 decision=test 的 shortlist、3 个实验设计、3 个轻量试点、8 个拒绝项。
> 基线 v1.7.3（2026-11-13）。许可一律给出来源链接；无法核实的一律写“待核实”，不猜测。
> 本页只做技术选型与实验设计，**不调研底座模型/刷榜**，也不写产品代码。

## 0. 结论先行

### 0.1 六个 shortlist（decision=test，全部许可已核实）

| id | 名称 | 用户可见功能 | 验证方式 | 预计成本 |
|---|---|---|---|---|
| A05 | ChinaXiv | Map 里出现中文预印本节点，摘要级证据可点回 | 试点 P1（OAI 采集 15 篇） | 0.5 天，CPU |
| B02 | LongCite-45k | Live 判定旁高亮“支撑这句话的原句” | 实验 E1（中文 200 条） | 5–10 分钟 API |
| B03 | CFEVER | “这条中文断言是否有公开证据”压力测试，暴露构造集过拟合 | 实验 E2（dev 抽 300） | 10–20 分钟 API |
| B04 | RAGTruth | Live 把“没有证据支撑的句子”标红 | 试点 P2（英文 200 条迁移） | 5–10 分钟 API |
| C02 | T2Retrieval | 中文语义检索阈值有外部依据，不再只靠 438 条小池子 | 实验 E3（200 查询/5k 段落） | <0.5 天，单卡 |
| D01 | MinerU | 中文 PDF 的段落/参考文献解析更准，页级证据定位更稳 | 试点 P3（22 篇 PDF 对比） | 10–20 分钟，单卡 |

### 0.2 三个实验一句话

- **E1 claim/evidence 抽取**：LongCite-45k 中文 200 条 + 本地 22 篇 OA PDF 抽 50 段；指标 claim recall、句级 evidence P/R/F1；kill：evidence F1 < 0.60 或 claim recall < 0.70。
- **E2 stance/支持度**：ClaimSupport-CN 100 + V2 140 + CFEVER dev 抽 300（+ SciFact 300 英文对照）；指标 macro-F1/accuracy；kill：CFEVER 抽样 macro-F1 < 0.55 或 ClaimSupport-100 下降 > 3 pt。
- **E3 检索 hit@3**：现有 replacement eval 438 查询/477 候选 + T2Retrieval 固定子集 200 查询/5,000 段落；指标 R@3/MRR@10；kill：相对 BGE-M3 R@3 0.3219 增益 < +0.02 或低于 BM25 0.2580。

### 0.3 决策口径

| decision | 含义 |
|---|---|
| adopt | 许可与可得性已确认，直接采用/沿用，不需要实验 |
| test | 值得用现有测试集做一次对照实验；实验不达标就放弃 |
| hold | 有用但当前 3 周窗口不投入；写清触发条件，后续再评估 |
| reject | 许可、语言、可得性或集成成本不满足，不进路线图 |

## 1. 功能定义（本页假设，需队长确认）

- **Check**：现有五维健康分与 F1–F5 管线（真实性、支持度、相关性、覆盖、规范性）。
- **Map**：把 2 篇以上论文对齐成 `paper / claim / evidence / method / sample / stance / gap` 证据地图（与团队任务 t4 的 schema 字段一致）。
- **Live**：浏览器/编辑器内边读边核验。仓库现有 `extension/`（MV3 划词核验：选中文字 → 右键核验 → 弹窗贴证据 → 四档判定），本页按这个形态理解 Live。

> 说明：团队任务表里目前没有 B2 的独立定义。以上是按现有 extension 与 t4 schema 的推断；若队长口径不同，只需替换“功能”列，不影响候选与实验设计。

## 2. 候选矩阵（37 项）

### 2.1 元数据与引文网络（A01–A06）

#### A01 OpenAlex
- 类型：开放学术元数据（API + 快照）
- 功能：Check、Map
- 许可：CC0；来源 https://ourresearch.gitbook.io/help.openalex.org/faq
- 规模/语言：亿级作品；英文为主，中文社科覆盖弱（本地实测 12 个中文标题 0 命中，见 docs/chinese_sources.md）
- 可得性：公开 API（无需密钥）/ 快照，可立即使用
- 集成方式：Map 侧把 references / cited_by 落成图边；Check 侧沿用现状
- 用户可见功能：点开一条引用 → 展开“谁引用了它 / 它引用了谁”的证据卡，边可点回原文
- 预期收益：Map 引文网络零新增数据成本；与现有真实性核验同源
- 风险：中文覆盖弱（不能替代中文题录源）；API 限流；字段语义漂移
- 决策：adopt

#### A02 Crossref REST API
- 类型：注册机构元数据 API
- 功能：Check、Map
- 许可：开放（免费 API；Crossref 声明元数据对社区开放共享）；来源 https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- 规模/语言：DOI 级元数据（数量以官网为准）；中文社科期刊覆盖有限
- 可得性：公开 API，无需密钥
- 集成方式：沿用现有 DOI/撤稿/更新查询；Map 侧补 DOI 对齐
- 用户可见功能：引用卡显示“DOI 有效 / 已撤稿 / 版本更新”
- 预期收益：F3 撤稿与 DOI 交换检测的既有能力保持不变
- 风险：中文元数据少；速率限制；与 OpenAlex 重复
- 决策：adopt

#### A03 arXiv API
- 类型：预印本元数据 API
- 功能：Map
- 许可：元数据 CC0 1.0；来源 https://info.arxiv.org/help/api/tou.html
- 规模/语言：百万级预印本（具体数量以官网为准）；英文
- 可得性：公开 API，无需密钥，建议限速
- 集成方式：Map 侧补预印本节点与版本关系
- 用户可见功能：预印本论文也能进证据地图，并标出“预印本/正式发表”状态
- 预期收益：扩大 Map 的开放论文池（t4 要求 15 篇开放论文）
- 风险：仅英文预印本；元数据字段有限
- 决策：adopt

#### A04 OpenCitations COCI
- 类型：开放引文网络数据集
- 功能：Map
- 许可：数据 CC0，软件 ISC；来源 https://opencitations.net/
- 规模/语言：COCI 收录 1,186,958,898 条引文链接（站点口径，截至 2021-09-10）；跨语言但中文少
- 可得性：公开 dump / API
- 集成方式：需要时补 Crossref 之外的引文边
- 用户可见功能：Map 中显示“非 Crossref 收录”的引用关系
- 预期收益：引文边覆盖比单用 Crossref 更全
- 风险：数据量大；与 OpenAlex 去重成本；中文几乎没有
- 决策：hold

#### A05 ChinaXiv
- 类型：中文预印本平台（OAI-PMH）
- 功能：Map
- 许可：OAI-PMH 元数据 CC BY 3.0（全文/完整元数据仅对合作方开放；作者可选 CC0/CC BY/CC BY-SA/CC BY-NC-SA）；来源 https://chinaxiv.org/user/help.htm
- 规模/语言：中文预印本；具体规模待核实
- 可得性：OAI-PMH 可公开采集元数据；全文获取条件待核实
- 集成方式：采集标题/作者/摘要/URL，作为 Map 的 paper 节点；全文只在许可允许时使用
- 用户可见功能：Map 中出现中文预印本论文，摘要级证据可点回原文页
- 预期收益：补中文开放论文（现有中文题录可确认率 51.8%，Wanfang 可到 79.0% 但不可用，见 docs/chinese_sources.md）
- 风险：全文受限 → 只能做摘要级证据；元数据字段少；OAI 稳定性
- 决策：test（试点 P1）

#### A06 Crossref Retraction Watch
- 类型：撤稿记录数据库（经 Crossref 分发）
- 功能：Check
- 许可：CC BY 4.0（页面版权声明）；来源 https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/
- 规模/语言：撤稿记录库（数量以页面为准）；跨语言，中文撤稿记录少
- 可得性：公开数据（页面注明 2025-01-19 最后更新）
- 集成方式：补现有 F3 撤稿库，按 DOI 对齐
- 用户可见功能：引用卡出现“撤稿”红色标记，并给出撤稿声明链接
- 预期收益：提高撤稿召回（现有 100/100 已是构造集上限，外部库能防漏）
- 风险：中文撤稿少；DOI 缺失的中文文献匹配不上
- 决策：hold

### 2.2 声明-证据、支持度与归因（B01–B14）

#### B01 SciFact
- 类型：科学声明-证据数据集
- 功能：Check
- 许可：claims/evidence CC BY 4.0，corpus ODC-By 1.0，代码 Apache-2.0；来源 https://github.com/allenai/scifact/blob/master/LICENSE.md
- 规模/语言：千级 claims（英文；规模以论文为准）
- 可得性：公开下载
- 集成方式：已在外部评测中使用；继续作为英文零样本对照
- 用户可见功能：说明“支持/反驳”能力不是只对中文构造集有效
- 预期收益：英文对照基线（现有 300 条零样本记录可复用）
- 风险：英文；标注是专家构造，与中文论文语境有域差
- 决策：adopt

#### B02 LongCite-45k
- 类型：长上下文带句级引用的问答数据
- 功能：Live、Map
- 许可：Apache-2.0（数据集卡片；代码仓库同为 Apache-2.0）；来源 https://github.com/THUDM/LongCite
- 规模/语言：44,600 条长上下文问答，句级引用标注，中英双语，上下文可达 128k 词（论文 arXiv:2409.02897）
- 可得性：公开下载（HF 托管；本机网络对 huggingface.co 不通，见第 6 节）
- 集成方式：作为 E1 的句级监督与提示词参考，不进产品运行时
- 用户可见功能：Live 判定旁直接高亮“支撑这句话的原句”，而不是只给整段
- 预期收益：把支持度从“整段判定”升级为“句级证据定位”
- 风险：长上下文推理成本；中文样本占比需统计；许可需随模型卡复核
- 决策：test（实验 E1）

#### B03 CFEVER
- 类型：中文事实抽取与核验数据集（AAAI-24）
- 功能：Check、Live
- 许可：Apache-2.0；来源 https://github.com/IKMLab/CFEVER-data
- 规模/语言：train 24,012 条 / dev 3,000 条（test 无标签）；中文
- 可得性：公开下载（jsonl）
- 集成方式：只在评测脚本里读 dev.jsonl，作为 E2 外部集；不训练
- 用户可见功能：证明“中文断言核验”不是只在自构造集上有效
- 预期收益：暴露构造集过拟合（现 ClaimSupport-100 macro-F1 0.9597）；给四档映射提供外部检验
- 风险：三分类（support/refute/no-info）需映射到四档；领域偏新闻/百科；test 无标签
- 决策：test（实验 E2）

#### B04 RAGTruth
- 类型：RAG 幻觉片段标注数据集
- 功能：Live
- 许可：MIT；来源 https://github.com/ParticleMedia/RAGTruth
- 规模/语言：约 18,000 条生成回答，词级人工幻觉标注；英文
- 可得性：公开下载
- 集成方式：P2 迁移实验；有效则作为 Live 标红规则的特征参考
- 用户可见功能：Live 把“句子里没有证据支撑的部分”标红，并提示“请补证据或删改”
- 预期收益：补现有 Unknown 19.87% 的“无依据句”粒度
- 风险：英文；RAG 场景与论文引用场景有域差；词级标注迁移到中文需重标
- 决策：test（试点 P2）

#### B05 SciCite
- 类型：引用意图数据集（背景/方法/结果）
- 功能：Map
- 许可：数据许可待核实（代码 Apache-2.0）；来源 https://github.com/allenai/scicite
- 规模/语言：千级引用上下文（英文；规模以论文为准）
- 可得性：公开下载
- 集成方式：Map 边语义（这条引用是背景还是方法对比）
- 用户可见功能：Map 中每条边标注“支持 / 对比 / 背景”
- 预期收益：让证据地图的边有语义，而不是只有连线
- 风险：数据许可未核实（集成前必须确认）；英文；三分类粒度粗
- 决策：hold（许可确认后再评估）

#### B06 ALCE
- 类型：带引用生成的评测基准与代码
- 功能：Live
- 许可：MIT；来源 https://github.com/princeton-nlp/ALCE
- 规模/语言：ASQA / QAMPARI / ELI5（英文）
- 可得性：公开
- 集成方式：借鉴其“引用质量”自动评测协议（fluency/correctness/citation quality）
- 用户可见功能：Live 的“证据是否真的支撑”有可复现的评测口径
- 预期收益：评测协议可直接裁剪成中文版
- 风险：英文；任务是生成而非核验，指标不能照搬
- 决策：hold

#### B07 RAGChecker
- 类型：RAG 细粒度诊断工具
- 功能：Check
- 许可：Apache-2.0；来源 https://github.com/amazon-science/ragchecker
- 规模/语言：claim 级 precision/recall 指标（英文）
- 可得性：公开
- 集成方式：离线诊断支持度误差来源（检索错 vs 判定错）
- 用户可见功能：后台质量报表能说清“错在检索还是错在判定”
- 预期收益：给 E1/E2 的误差分析提供现成指标
- 风险：依赖 claim 抽取器；英文提示词需重写
- 决策：hold

#### B08 RefChecker
- 类型：claim-evidence 三元组核验工具
- 功能：Check
- 许可：Apache-2.0；来源 https://github.com/amazon-science/refchecker
- 规模/语言：claim/evidence 三元组（英文）
- 可得性：公开
- 集成方式：参考其“抽取→核验”两段式设计
- 用户可见功能：支持度判定附带结构化证据三元组
- 预期收益：与 t4 的 claim/evidence/stance 字段天然对齐
- 风险：英文；需替换中文抽取器
- 决策：hold

#### B09 FActScore
- 类型：原子事实分解与核验工具
- 功能：Live
- 许可：MIT；来源 https://github.com/shmsw25/FActScore
- 规模/语言：传记类原子事实（英文）
- 可得性：公开
- 集成方式：参考“把长句拆成原子事实再核验”的流程
- 用户可见功能：Live 给出“这句话里有 3 个事实，2 个有证据”
- 预期收益：比整句判定更可解释
- 风险：英文知识源；中文事实拆解需重做
- 决策：hold

#### B10 ContextCite
- 类型：上下文片段归因工具
- 功能：Live
- 许可：MIT；来源 https://github.com/MadryLab/context-cite
- 规模/语言：把生成语句归因到上下文片段（英文）
- 可得性：公开
- 集成方式：参考其“句子→片段”归因思路，做证据高亮
- 用户可见功能：鼠标悬停一句话，显示它依赖了原文哪几句
- 预期收益：Live 高亮的可解释性
- 风险：需要白盒/代理模型；中文适配成本
- 决策：hold

#### B11 CiteBench
- 类型：科学引用文本生成基准
- 功能：Check
- 许可：Apache-2.0；来源 https://github.com/UKPLab/citebench
- 规模/语言：多领域引用生成；CHEN 子集因许可原因未纳入
- 可得性：公开
- 集成方式：只作为“引用文本生成”任务的参考，不用于核验
- 用户可见功能：无直接功能（避免误用为核验基准）
- 预期收益：明确边界：生成质量 ≠ 引用真实性
- 风险：任务错配，容易被误当成核验集
- 决策：hold

#### B12 CRAG
- 类型：RAG 综合基准（网页检索 + 问答）
- 功能：Check
- 许可：CC BY-NC 4.0（非商用）；来源 https://github.com/facebookresearch/CRAG
- 规模/语言：英文网页问答基准（规模以仓库为准）
- 可得性：公开，但非商用
- 集成方式：不集成；只作方法阅读
- 用户可见功能：无（许可不允许商用产品集成）
- 预期收益：了解外部检索增强的评测设计
- 风险：非商用许可与产品化冲突；英文
- 决策：reject（许可证）

#### B13 CiteME
- 类型：引用核验基准（幻灯片式）
- 功能：Check
- 许可：待核实（仓库 license 未声明）；来源 https://github.com/bethgelab/CiteME
- 规模/语言：130 题；英文
- 可得性：公开（数据集站点点对点下载）
- 集成方式：不集成；仅作英文评测参考
- 用户可见功能：无（无中文）
- 预期收益：了解“给主张找正确引用”的任务定义（人类 69.7%）
- 风险：无中文；许可未声明
- 决策：reject（无中文 + 许可待核实）

#### B14 ChartCheck
- 类型：图表事实核验基准
- 功能：Check
- 许可：数据集 MIT；来源 https://github.com/mubasharaak/chartfc_dataset_wikicommons
- 规模/语言：1.7k 人工撰写的图表 claim；英文
- 可得性：公开
- 集成方式：不集成；仓库已在图表核验评测中使用过（见 docs/figure_check.md）
- 用户可见功能：无（场景窄、无中文）
- 预期收益：图表场景的评测经验
- 风险：场景窄；英文
- 决策：reject（无中文/场景不匹配）

### 2.3 检索（C01–C03）

#### C01 BGE-M3
- 类型：多语检索/embedding 模型
- 功能：Check
- 许可：MIT；来源 https://github.com/FlagOpen/FlagEmbedding
- 规模/语言：多语（含中文），支持稠密/稀疏/多向量
- 可得性：公开权重，可离线部署
- 集成方式：已在替换检索评测中使用（docs/embeddings.md）
- 用户可见功能：修复建议里“换成这篇更合适”的候选排序
- 预期收益：现有 R@3 0.3219 的基线保持
- 风险：显存；长文本截断；小池子（477 候选）指标偏乐观
- 决策：adopt

#### C02 T2Ranking / T2Retrieval
- 类型：中文段落检索数据集（C-MTEB 任务）
- 功能：Check
- 许可：Apache-2.0（MTEB 任务页）；来源 https://leaderboard.mteb.org/tasks/T2Retrieval
- 规模/语言：300K+ 查询、2M+ 段落；中文，人工标注
- 可得性：公开（数据集仓库 https://github.com/THUIR/T2Ranking）
- 集成方式：E3 取固定子集（200 查询/5,000 段落），不改产品检索器
- 用户可见功能：检索命中率有外部依据，阈值更可信
- 预期收益：校准“R@3 多少算可用”，避免 438 查询小池子的乐观偏差
- 风险：段落级检索与“引用上下文→参考文献”任务分布不同；子集抽样需固定种子
- 决策：test（实验 E3）

#### C03 DuReader-Retrieval
- 类型：中文检索数据集
- 功能：Check
- 许可：Apache-2.0；来源 https://github.com/baidu/DuReader
- 规模/语言：90K+ 查询、8M+ 段落；中文
- 可得性：公开，但体量大
- 集成方式：不落地；只参考其难负例构造方法
- 用户可见功能：无（不为 3 周窗口引入 8M 段落索引）
- 预期收益：难负例思路可借鉴
- 风险：体量与场景（搜索问答）不匹配；索引/存储成本远超收益
- 决策：reject（集成成本过高）

### 2.4 PDF/浏览器/文本工具（D01–D12）

#### D01 MinerU
- 类型：PDF 版面解析工具
- 功能：Map、Check
- 许可：Apache-2.0 + 附加条款（商用允许；MAU > 1 亿或月收入 > 2000 万美元需单独商业许可；需保留归属）；来源 https://github.com/opendatalab/MinerU
- 规模/语言：中英文 PDF，版面/表格/公式解析；中文版式支持较强
- 可得性：公开，可离线部署
- 集成方式：P3 离线批量解析 22 篇 OA PDF 做对比；优于现状再考虑替换可选依赖（不进核心镜像的许可红线）
- 用户可见功能：中文论文的段落/参考文献切分更准，页级证据定位更稳
- 预期收益：现有页映射 17/18；中文双栏/表格是主要误差源
- 风险：附加条款（商用阈值）；模型依赖重；与现有 PyMuPDF 路径的迁移成本
- 决策：test（试点 P3）

#### D02 GROBID
- 类型：PDF→TEI 结构化工具
- 功能：Check
- 许可：Apache-2.0；来源 https://github.com/kermitt2/grobid
- 规模/语言：英文/欧洲语言强，中文 PDF 弱
- 可得性：公开，可离线部署（Java 服务）
- 集成方式：仓库已有 ocr/grobid 评测（docs/ocr_grobid_eval.md）；继续作为英文结构化路径
- 用户可见功能：英文参考文献字段更完整
- 预期收益：英文引文解析质量
- 风险：中文 PDF 效果差；服务化部署成本
- 决策：adopt

#### D03 Docling
- 类型：文档解析工具（IBM）
- 功能：Map
- 许可：MIT；来源 https://github.com/docling-project/docling
- 规模/语言：多格式（PDF/DOCX/PPTX/HTML）；中英文
- 可得性：公开
- 集成方式：作为 MinerU 的备选；暂不落地
- 用户可见功能：若 MinerU 不稳，可作为中文 PDF 解析备胎
- 预期收益：MIT 许可最干净，降低许可风险
- 风险：中文版式效果待评；依赖较多
- 决策：hold

#### D04 marker
- 类型：PDF→Markdown 工具
- 功能：Map
- 许可：Apache-2.0；来源 https://github.com/VikParuchuri/marker
- 规模/语言：多语 PDF；中文效果待评
- 可得性：公开
- 集成方式：备选；不落地
- 用户可见功能：无（仅作技术备选）
- 预期收益：速度/质量平衡的参考
- 风险：模型下载大；中文表格弱
- 决策：hold

#### D05 PyMuPDF
- 类型：PDF 解析库（现状）
- 功能：Check
- 许可：AGPL-3.0；来源 https://github.com/pymupdf/PyMuPDF
- 规模/语言：通用 PDF；中文可用
- 可得性：公开
- 集成方式：仓库已按 docs/licenses.md 把它隔离为可选依赖，不进核心镜像
- 用户可见功能：现有页级定位能力
- 预期收益：无新增（保持现状）
- 风险：AGPL 传染性，不能进核心 Docker
- 决策：reject（许可证）

#### D06 SingleFile
- 类型：网页单文件归档工具
- 功能：Live
- 许可：AGPL-3.0；来源 https://github.com/gildas-lormeau/SingleFile
- 规模/语言：通用网页
- 可得性：公开（浏览器扩展/CLI）
- 集成方式：不集成；Live 证据留存改用截图 + 原文链接
- 用户可见功能：无（许可不允许进产品核心）
- 预期收益：网页快照归档
- 风险：AGPL
- 决策：reject（许可证）

#### D07 Readability.js
- 类型：网页正文抽取库
- 功能：Live
- 许可：Apache-2.0；来源 https://github.com/mozilla/readability
- 规模/语言：通用网页；中英文
- 可得性：公开（JS）
- 集成方式：Live 扩展的正文抽取直接选用
- 用户可见功能：在网页上划词后，只把正文段落当证据，过滤导航/广告
- 预期收益：降低 Live 的噪声证据
- 风险：动态渲染页需兜底；单页应用可能抽不到
- 决策：adopt

#### D08 PDF.js
- 类型：浏览器 PDF 渲染库
- 功能：Live
- 许可：Apache-2.0；来源 https://github.com/mozilla/pdf.js
- 规模/语言：通用 PDF；中英文
- 可得性：公开（JS）
- 集成方式：Live 扩展在浏览器内定位 PDF 页码/文本层
- 用户可见功能：在 PDF 阅读器里点证据直接跳到对应页
- 预期收益：Live 的页级证据定位复用现有 17/18 页映射能力
- 风险：大文件性能；扫描版无文本层
- 决策：adopt

#### D09 jieba
- 类型：中文分词库
- 功能：Check
- 许可：MIT；来源 https://github.com/fxsjy/jieba
- 规模/语言：中文；通用词典
- 可得性：公开（Python）
- 集成方式：BM25/关键词覆盖的确定性分词路径
- 用户可见功能：关键词覆盖与“规范性”检查的中文切分更稳
- 预期收益：零许可风险、零模型依赖
- 风险：新词/专业术语弱；与现有分词器可能不一致
- 决策：adopt

#### D10 PaperQA2
- 类型：科学文献 RAG 工具
- 功能：Map
- 许可：Apache-2.0；来源 https://github.com/Future-House/paper-qa
- 规模/语言：英文学术文献；多论文问答与引用
- 可得性：公开，活跃（9.6k stars，2026-11-09 有提交）
- 集成方式：参考其“检索→证据→带引用回答”的管线设计；不直接部署
- 用户可见功能：Map 的“跨论文综述”交互参考
- 预期收益：证据链设计的成熟范式
- 风险：英文；集成重；LLM 成本
- 决策：hold

#### D11 OpenScholar
- 类型：科学综述生成系统（8B）
- 功能：Map
- 许可：Apache-2.0；来源 https://github.com/AkariAsai/OpenScholar
- 规模/语言：英文文献；检索增强综述 + 引用
- 可得性：公开（代码+模型）
- 集成方式：参考其检索-综合-引用管线；不直接部署
- 用户可见功能：Map 的“按主题生成带引用的综述”参考
- 预期收益：综述式交互的设计参考
- 风险：8B 依赖；英文；与 3 周窗口不匹配
- 决策：hold

#### D12 CSL styles
- 类型：引用样式仓库
- 功能：Live
- 许可：CC BY-SA 3.0（README 明确）；来源 https://github.com/citation-style-language/styles
- 规模/语言：GB/T 7714-2015 数字制样式文件存在（china-national-standard-gb-t-7714-2015-numeric.csl）；中英文
- 可得性：公开
- 集成方式：仅在“导出/复制参考文献”时使用；因 share-alike 需与核心代码隔离
- 用户可见功能：导出 GB/T 7714 格式的参考文献
- 预期收益：格式导出少写一套渲染器
- 风险：CC BY-SA 传染性；需法务确认隔离方式
- 决策：hold

### 2.5 中文商业/不可得（E01–E02）

#### E01 CNKI
- 类型：中文全文数据库
- 功能：Check
- 许可：商业订阅（无公开数据许可）；来源 https://www.cnki.net/
- 规模/语言：中文期刊/学位论文全文；规模最大
- 可得性：不可得（机构订阅，导出数据不能入库再分发）
- 集成方式：不集成；只在本地人工核验时按订阅使用
- 用户可见功能：无（合规上不能做产品数据源）
- 预期收益：中文覆盖最全，但不可产品化
- 风险：无 API；许可与再分发风险
- 决策：reject（不可得）

#### E02 Wanfang
- 类型：中文题录/全文平台
- 功能：Check
- 许可：商业服务条款（开放平台免费 100 次/日、4 req/s，需 X-App-Key）；来源 https://www.wanfangdata.com.cn/
- 规模/语言：中文期刊题录/全文
- 可得性：受限（配额 + ToS；数据不可再分发）
- 集成方式：不集成；本地试点显示中文可确认率 51.8% → 79.0%（见 docs/chinese_sources.md），但只能作为人工核验辅助
- 用户可见功能：无（不能做成产品内置数据源）
- 预期收益：中文题录命中显著提升（试点 26/210 → 137/210）
- 风险：ToS/配额；不可再分发；服务稳定性
- 决策：reject（不可得）

## 3. 六个 shortlist 与实验/试点映射

| id | 名称 | 对应实验/试点 | 失败即放弃的方式 |
|---|---|---|---|
| A05 | ChinaXiv | P1：OAI 采集 15 篇 | 可获取 < 12 篇或字段完整率 < 70% |
| B02 | LongCite-45k | E1：句级 evidence | evidence F1 < 0.60 或 claim recall < 0.70 |
| B03 | CFEVER | E2：外部中文核验 | CFEVER 300 macro-F1 < 0.55 或 ClaimSupport 降 > 3 pt |
| B04 | RAGTruth | P2：无依据句标红 | 英文迁移 span F1 < 0.40 |
| C02 | T2Retrieval | E3：中文检索阈值 | R@3 增益 < +0.02 或低于 BM25 |
| D01 | MinerU | P3：中文 PDF 解析 | 解析 F1 低于现状或耗时 > 3× |

## 4. 三个实验设计

> 成本口径：API 按 DeepSeek 1–2 s/条估；GPU 按单张 RTX 4090 24GB bf16 估；标注成本按 1 人 1.5 h/50 段估。除注明“已实测”外，均为估算，不是承诺。

### E1 claim/evidence 抽取

- **目标**：从中文论文里抽出 claim（可核验的断言）和句级 evidence（支撑它的原句），支撑 Live 的“句级证据高亮”和 Map 的 evidence 卡。
- **用哪个现有测试集**：
  - 本地 `data/real_corpus/`：22 篇 OA PDF（543 条引文，21/22 篇含引文）；抽 50 段做人工 claim/evidence 标注（约 1.5 h）。
  - 公开 LongCite-45k 中文子集：抽 200 条（有句级引用标注，可直接算句级指标）。
- **指标**：
  - claim recall = 抽出的 claim 覆盖人工标注 claim 的比例；
  - evidence sentence P/R/F1（句级，按字符重叠 ≥ 0.5 判对）；
  - 端到端“证据定位正确率”（给出的句子确实是支撑句）。
- **kill 条件**：evidence F1 < 0.60，或 claim recall < 0.70 → 不投入 Live 高亮，退回“整段引用 + 原文链接”。
- **预计 GPU/时间**：250 条 × 1–2 s ≈ 5–10 分钟 API，0 GPU；若走本地 Qwen3-1.7B LoRA（已实测 109.2 s / 3 epoch / 30 step，单卡 4090），推理 < 1 s/条。
- **产出**：`docs/research/e1_extraction.md`（表 + 错例 10 条）。

### E2 stance/支持度

- **目标**：判定 claim 与 evidence 的四档关系（support/partial/contradict/no_evidence），对应 Live 弹窗四档和 Map 的 stance 字段。
- **用哪个现有测试集**：
  - ClaimSupport-CN 100（dev 40 + test 60）；V2 140；
  - CFEVER dev 3,000 中分层抽 300（中文事实核验，含 REFUTES）；
  - SciFact 300（英文零样本对照）。
- **指标**：macro-F1、accuracy、Unknown 比例；三分类需先做映射表（SUPPORTS→support，REFUTES→contradict，NOT ENOUGH INFO→no_evidence；partial 仅 ClaimSupport 有），映射表随结果一起报告。
- **基线**：ClaimSupport-100 macro-F1 0.9597 / acc 0.9500；V2 140：0.977 / 0.979（同分布构造集）。
- **kill 条件**：CFEVER 抽样 macro-F1 < 0.55（说明只在构造集有效），或 ClaimSupport-100 比基线下降 > 3 pt。
- **预计 GPU/时间**：约 600 条 × 1–2 s ≈ 10–20 分钟 API；本地 4B LoRA 训练归 t3，不在本实验重复。
- **产出**：`docs/research/e2_stance.md`（混淆矩阵 + 映射表 + 错例）。

### E3 检索 hit@3

- **目标**：给“替换建议/证据检索”的命中率一个外部刻度，避免只在小池子上调阈值。
- **用哪个现有测试集**：
  - 现有 replacement eval：438 查询、477 候选（scripts/build_replacement_eval.py、scripts/eval_replacement.py，数据 data/experiments/replacement_eval_dataset.json）；
  - T2Retrieval 固定子集：200 查询 / 5,000 段落（按 qid 哈希 + 固定种子抽样，脚本落盘，保证可复现）。
- **指标**：R@3、MRR@10；分中文/英文、分查询类型。
- **基线**：BGE-M3 R@1 0.1986 / R@3 0.3219 / MRR 0.2948；BM25 0.1872 / 0.2580 / 0.2428；标题重叠 0.1712 / 0.2329 / 0.2245。
- **kill 条件**：相对 BGE-M3 的 R@3 增益 < +0.02，或低于 BM25 → 不换检索器；T2Retrieval 子集 R@3 < 0.60（阈值先用 20 条 pilot 校准，再冻结）。
- **预计 GPU/时间**：约 5,500 段落 + 638 查询，4090 上 embedding < 30 分钟；无 API 成本。
- **产出**：`docs/research/e3_retrieval.md`（表 + 子集抽样脚本说明）。

## 5. 三个轻量试点（各 ≤ 0.5 天）

### P1 ChinaXiv 可采集性

- **做法**：用 OAI-PMH 按 2 个主题各采集 15 篇（对应 t4 的 2 topics × 15 open papers 需求），统计标题/作者/摘要/URL/日期完整率。
- **指标**：可获取率、字段完整率、摘要级 evidence 可用率。
- **kill**：15 篇里可获取 < 12 篇，或字段完整率 < 70% → 退回 arXiv/OpenAlex 开放池，Map 不承诺中文预印本。
- **成本**：0.5 天，CPU。

### P2 RAGTruth 迁移

- **做法**：英文 200 条上跑“无依据句检测”，再看中文 ClaimSupport 里能否复用同一套特征。
- **指标**：span 级 P/R/F1。
- **kill**：英文 span F1 < 0.40 → 不做中文迁移。
- **成本**：200 条 ≈ 5–10 分钟 API。

### P3 MinerU vs 现有解析

- **做法**：22 篇 OA PDF 上对比 MinerU 与现有 PyMuPDF 路径：段落切分、参考文献字段、页映射。
- **指标**：参考文献字段 F1、页映射正确率（现状 17/18）。
- **kill**：解析 F1 低于现状，或单篇耗时 > 3× → 维持现状。
- **成本**：4090 上约 10–20 分钟（估）。

## 6. 拒绝清单（8 项，含理由与重新评估条件）

| id | 名称 | 理由类别 | 具体理由 | 什么情况下重新评估 |
|---|---|---|---|---|
| B12 | CRAG | 许可证 | CC BY-NC 4.0，非商用，与产品化冲突 | 拿到商用授权 |
| D05 | PyMuPDF | 许可证 | AGPL-3.0，不能进核心镜像（已隔离为可选） | 换成 MIT/Apache 替代或取得商业许可 |
| D06 | SingleFile | 许可证 | AGPL-3.0，浏览器扩展不能捆绑 | 自研等价归档或换 MIT 工具 |
| B13 | CiteME | 无中文 + 许可待核实 | 130 题全英文，仓库未声明数据许可 | 有中文版且许可明确 |
| B14 | ChartCheck | 无中文/场景窄 | 只有英文图表 claim，与中文引用核验主路径不符 | 做中文图表核验需求时 |
| E01 | CNKI | 不可得 | 商业订阅，无公开 API，导出数据不可再分发 | 获得可再分发授权 |
| E02 | Wanfang | 不可得 | 商业 ToS，免费 100 次/日，数据不可再分发 | 获得产品化授权 |
| C03 | DuReader-Retrieval | 集成成本过高 | 8M+ 段落，索引/存储成本远超 3 周窗口收益 | 需要大规模中文检索训练时 |

## 7. 与现有文档/任务的衔接

- **docs/licenses.md**：核心 Docker 不含 AGPL/GPL。本页 D05 PyMuPDF、D06 SingleFile 的 reject 正是执行这条规则；D01 MinerU 的附加条款（商用阈值）需在引入前复核。
- **docs/chinese_sources.md**：中文题录没有免费程序化 API；Wanfang 试点把可确认率从 51.8% 提到 79.0%，但 ToS 不允许产品化 → 本页只保留 A05 ChinaXiv 这一条“可公开采集”的中文补充。
- **docs/methods_sources.md**：SciFact / ChartCheck / CiteME 已引用；本页新增 CFEVER、LongCite-45k、RAGTruth、SciCite、T2Retrieval 的出处，合并文档更新属队长范围（本页不改 docs/methods_sources.md）。
- **t4（B1a）**：Map schema 的 `paper/claim/evidence/method/sample/stance/gap` 与本页 E1/E2 的产出直接对齐；A05 的 2 topics × 15 篇可作为 t4 manifest 的候选来源。
- **t2/t3**：A3a SFT 与 A3b LoRA 的数据标注/训练不在本页重复；E1/E2 只做评测设计，训练仍归 t2/t3。

## 8. 许可与链接核实记录（2026-11-14）

**方法**：
1. GitHub 仓库许可：`api.github.com/repos/<owner>/<repo>` 的 `license.spdx_id`；必要时用 contents API 读 `LICENSE` / `LICENSE.md` / `README` 原文。
2. 平台/数据许可：抓取官方页面正文（OpenAlex FAQ、arXiv ToU、DOAJ 博客、Crossref 文档、OpenCitations、ChinaXiv 帮助页）。
3. 链接可用性：HEAD 优先、GET 兜底，12–15 s 超时，UA 为 Mozilla/5.0；本页 38 个唯一链接全部返回 200（HF 域名除外，见下）。

**已核实（原文口径）**：
- OpenAlex：CC0；arXiv API 元数据：CC0 1.0；DOAJ：期刊元数据 CC BY-SA、文章元数据 CC0 waiver；Crossref API：免费开放共享（未写 CC0，故本页不写 CC0）；Crossref Retraction Watch：页面版权声明 CC BY 4.0；OpenCitations：数据 CC0、软件 ISC；ChinaXiv：OAI-PMH 元数据 CC BY 3.0、全文限合作方。
- SciFact：claims/evidence CC BY 4.0、corpus ODC-By 1.0、代码 Apache-2.0（LICENSE.md 原文）。
- LongCite：数据集卡片 Apache-2.0、仓库 Apache-2.0；CFEVER：Apache-2.0（train 24,012 / dev 3,000 行）；RAGTruth：MIT（约 18,000 条）；SciCite：代码 Apache-2.0；ALCE：MIT；RAGChecker/RefChecker：Apache-2.0；FActScore/ContextCite：MIT；CiteBench：Apache-2.0；CRAG：CC BY-NC 4.0（LICENSE 原文“Attribution-NonCommercial 4.0 International”）。
- ChartCheck：数据集仓库 MIT；CiteME：仓库 license 未声明。
- MinerU：Apache-2.0 + 附加条款（商用阈值）；GROBID/marker/Docling：Apache-2.0 / Apache-2.0 / MIT；PyMuPDF、SingleFile：AGPL-3.0；Readability、PDF.js：Apache-2.0；jieba：MIT；BGE-M3：MIT；PaperQA2、OpenScholar：Apache-2.0；CSL styles：CC BY-SA 3.0（README 原文），GB/T 7714-2015 数字制样式文件存在。
- CNKI/Wanfang：商业服务；Wanfang 开放平台配额与 ToS 见 docs/chinese_sources.md 本地试点记录。

**待核实（不在本页下结论）**：
- SciCite **数据**许可（代码 Apache-2.0 已确认；数据许可未读，故 B05 只到 hold）。
- CiteME 数据许可（仓库 NOASSERTION）。
- ChinaXiv 全文获取条件与平台规模。
- 各数据集“精确数量”：未逐条打开的，只写“以论文/官网为准”。
- Unpaywall 未进入矩阵（页面无许可声明）。

**网络限制**：本机访问 huggingface.co（含 raw/API）超时，因此 HF 不作为任何许可的唯一来源；LongCite 的许可以 GitHub 仓库与数据集卡片的 Apache-2.0 文本为准，下载链接仅作补充。

**复核提示**：许可会变。集成前在 PR 描述里附“许可快照日期 + 链接”，尤其是 MinerU 附加条款与 CRAG/ChartCheck 的非商用/第三方条款。

**抽查清单（给队长，均为本次实测）**：
- 链接 1：[LongCite 仓库](https://github.com/THUDM/LongCite)（B02 来源，HTTP 200）
- 链接 2：[CFEVER 仓库](https://github.com/IKMLab/CFEVER-data)（B03 来源，HTTP 200）
- 链接 3：[T2Retrieval 任务页](https://leaderboard.mteb.org/tasks/T2Retrieval)（C02 许可来源，HTTP 200）
- 许可 1：CFEVER = Apache-2.0（仓库 LICENSE；dev 3,000 行 / train 24,012 行按文件行数核对）
- 许可 2：MinerU = Apache-2.0 + 附加条款（LICENSE.md；商用阈值 MAU 1 亿 / 月收入 2,000 万美元）
