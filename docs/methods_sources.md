# 方法与论文来源对照（答辩备用）

> 一句话：CiteGuard-CN 不是复现某一篇论文，也不是提出新算法；它把「引文真实性核验」「claim 支撑判定」
> 「图表结论核验」几条已有研究线，和书目数据源、国家标准、开源模型拼成一个可运行的中文工作台，
> 并补了中文真实语料与系统化评测。下表写清每个模块的依据，以及我们改了什么、没改什么。

## 1. 引文真实性核验（题录比对）

| 依据 | 类型 | 我们怎么用 |
|---|---|---|
| OpenAlex（Priem, Piwowar & Orr, arXiv:2205.01833） | 开放书目索引（CC0） | 主检索源：标题/DOI 检索、作者/年份/卷期页码比对 |
| Crossref REST API（Hendricks et al., *Quantitative Science Studies*, 2020） | 开放元数据 | 补充检索与 DOI 元数据 |
| arXiv API（Atom） | 开放预印本元数据 | 条目里带 `arXiv:2205.14135` / `arxiv.org/abs/...` / `10.48550/arXiv.*` 时，用 arXiv ID 做**第二锚点**直接取题录，不再只靠标题模糊检索 |
| Semantic Scholar Graph API | 开放学术图谱 | **可选**补充源（`CITEGUARD_S2=1` 才启用）；免 key 限流很严，默认关闭，429 后自动休眠 2 分钟 |
| DataCite / DOI Handbook（ISO 26324） | DOI 注册与解析规范 | DOI 解析到落地页；中国 DOI 平台同样按 handle 解析 |
| GB/T 7714—2015 / 2025 | 国家标准（非论文） | 参考文献表格式与顺序编码制规则 |

我们的改动（工程实现，非论文贡献）：`Exact / Minor / Major / Unverified / Unknown` 五态设计；
作者姓氏与顺序比对；URL 型条目的链接活性检查（含 SSRF 防护、缓存、403/401 视为"受限"而非"造假"）；
会议/期刊缩写归一（`ACL` / `NeurIPS` / `CVPR` 等映射到全称后再比对，避免"同一会议两种写法被误判"）；
arXiv ID 第二锚点；中文题录缺口显式标注（free 源覆盖不到时给「未验证 + 人工复核入口」，而不是猜）。
DBLP 的公开 API 现在对脚本返回 Cloudflare 挑战页（HTTP 202），所以没有接入；不绕过反爬。

## 2. 引文支持度（claim–evidence）

| 依据 | 类型 | 我们怎么用 |
|---|---|---|
| SciFact（Wadden et al., EMNLP 2020） | 科学 claim 核验数据集（CC BY 4.0） | 外部零样本评测；support / contradict / no-evidence 三分类的思想来源 |
| CiteME（Press et al., NeurIPS 2024 D&B, arXiv:2407.12888） | 引文准确性基准 | "不要只查存在，还要查是否支持"的问题设定 |
| RefChecker（Zhang et al., arXiv:2405.14486；仓库 MIT/Apache） | 细粒度引用核验框架 | 外部同协议对比（SciFact 300 条）；上游提交过 1 个 PR（已关闭未合并，如实记录） |
| LLM-as-a-judge（Zheng et al., NeurIPS 2023） | 评测方法 | 用同一 OpenAI 兼容接口做判定；用多模型盲标做标注审计 |
| Self-Consistency（Wang et al., ICLR 2023） | 解码策略 | 试过 3 票投票，本任务无提升，未采用（结果如实保留） |

我们的改动：在 support / partial / contradict / no-evidence **四分类**下做两段式判定（先判定，再做覆盖审计），
并用「盲标 + 三模型多数票」检验自建标签；**partial 类别和中文 ClaimSupport-CN 是我们的构造，不是论文原有定义**。

## 3. 图表结论核验

| 依据 | 类型 | 我们怎么用 |
|---|---|---|
| ChartCheck（Akhtar et al., Findings of ACL 2024） | 真实图表 claim 核验基准 | 外部零样本压力测试（60 条分层样本） |
| CharXiv（arXiv:2406.18521） | 图表理解基准（CC BY-SA 4.0） | 调研后未采用（图表版权随 arXiv 原文，且任务偏问答） |
| Qwen2.5-VL（arXiv:2502.13923） / Qwen3-VL（2025 技术报告） | 开源视觉语言模型（Apache-2.0） | 自托管推理：图 + 图注/正文 → supported/contradicted/insufficient；产品默认 7B，v0.9.14 起加测 8B |

我们的改动：**把"图注/正文上下文"显式作为可选输入**，并测了上下文消融（7B 50 条：仅图 0.90 → 带上下文 0.94）；
多 claim（一图最多 5 条）与 PDF 指定页取上下文是产品工程，不是论文结论。

## 4. 其他工程依据

| 依据 | 类型 | 说明 |
|---|---|---|
| mutation testing（DeMillo, Lipton & Sayward, 1978） | 软件测试思想 | E8「真实参考文献变异检测」把变异测试思路用到核验器评测（支持度/真实性边界） |
| PaddleOCR / RapidOCR（PP-OCR, arXiv:2009.09941） | OCR | 扫描版 PDF 的可选回退；图片文字层损坏时用 |
| pdfplumber / pypdfium2 | 解析库 | 版面/双栏启发式；无对应论文 |
| BM25（Robertson & Zaragoza, 2009） | 检索排序 | 选题发现的词面重叠排序受其思路影响，但未实现完整 BM25 |

## 5. 明确不是论文来源的部分

- 中文真实语料（22 篇 / 409 条引文）与中文图表集（13 图 / 26 条）是我们自己收集、人工挑图写 claim 的；
- GB/T 7714-2025 规则引擎是按标准条文实现的，不是论文；
- 产品形态（报告、导出、题录库、一键补录）是工程；
- E8 变异基准、四分类 partial、两段式审计中的"覆盖审计"提示词，都是我们的设计选择，没有论文背书，
  因此对外只说"工程实现 + 自建评测"，不宣称算法创新。
