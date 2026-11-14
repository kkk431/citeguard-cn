# CiteMap 证据地图

CiteMap 把「一篇论文说了什么」从自由文本变成**可校验、可对照、可展示**的结构化证据：先定义主题与待检验断言（claim），再为每篇开放论文记录一条带立场的证据（evidence），并显式标注方法、样本、原文定位、置信度与证据缺口（gap）。

它回答的问题是：

- 某个断言（如「生成式 AI 能提升学习成效」）目前有哪些**支持 / 反驳 / 中立**证据？
- 这些证据来自什么设计、多大样本、哪个人群，能否外推？
- 哪些结论被反复声称、却缺少对应设计或样本（gap）？
- 每条证据的原文能否定位、许可是否允许引用？

它**不**回答：论文本身是否真实存在（由引文真实性核验负责）、格式是否合规（由 GB/T 7714 检查负责）、或某个模型是否优于另一个模型。

实现：`src/citeguard/evidence_map.py`（纯标准库，`dataclasses` + `enum`，无 pydantic / 无网络依赖）；数据：`data/evidence_map/`；测试：`tests/test_evidence_map.py`。

## 快速开始

```bash
# 全量 schema 校验（两个主题）
PYTHONPATH=src python -m citeguard.evidence_map --check

# 查看某一主题的统计与逐篇校验
PYTHONPATH=src python -m citeguard.evidence_map --topic ai_education

# 指定数据目录（默认仓库 data/evidence_map）
PYTHONPATH=src python -m citeguard.evidence_map --check --data-dir data/evidence_map

# 测试
pytest tests/test_evidence_map.py -q
```

> Windows PowerShell 用 `$env:PYTHONPATH='src'; python -m citeguard.evidence_map --check`。仓库是 `src/` 布局且未打包安装，因此直接运行模块需要 `PYTHONPATH=src`。

`--check` 成功时向 stdout 输出 `{"ok": true, "topics": [...], "totals": {...}}`，退出码 0；schema 错误时向 stderr 输出 `{"ok": false, "error": "..."}`，退出码 2。

## 数据布局

```text
data/evidence_map/
├── index.json                  # 主题索引：顺序、名称、文件指针
├── verification.json           # DOI 双通道校验 + 许可一致性
├── README.md                   # 数据层说明
├── abstracts.json              # OpenAlex 摘要（inverted index 还原）
├── corpus/
│   ├── ai_education.json       # Topic + 15 篇 Paper（manifest）
│   └── medical_imaging.json
├── extractions/
│   ├── ai_education.json       # 人工示例：4 Claim + 5 Evidence + 3 Gap
│   └── medical_imaging.json
├── extractions_auto/           # 机器抽取（仅摘要，见下文）
│   ├── ai_education.json
│   └── medical_imaging.json
└── verification_packet.json    # 60 格人工核对抽样（每主题 30 格）
```

- `corpus/*.json` 只存元数据与开放获取链接，**不存 PDF 全文**；测试会断言 `data/evidence_map/` 下不存在 `.pdf` 文件。
- `extractions/*.json` 是 10 条人工示例抽取，用于校验 schema、展示抽取字段与置信度，不声称覆盖全部文献。
- `extractions_auto/*.json` 是机器抽取结果（摘要级）；与人工示例分文件存放，避免把机器输出混入人工金标。
- `index.json` 是唯一入口；`list_topics()` 会从 corpus/extractions 重新计算计数，索引中的计数不是可信来源，校验会交叉核对。

## 语料规模

| 主题 | topic_id | 论文 | 中国机构参与 | 许可分布 | OA 状态 | 全文可直链 | Claim | Evidence | Gap |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |
| 人工智能教育 | `ai_education` | 15 | 11 | cc-by 8、cc-by-nc-nd 5、cc-by-sa 1、cc-by-nc-sa 1 | gold 8、hybrid 4、diamond 2、green 1 | 14 | 4 | 5 | 3 |
| 医学影像 AI | `medical_imaging` | 15 | 13 | cc-by 12、cc-by-nc-nd 2、cc-by-nc 1 | gold 13、hybrid 1、diamond 1 | 13 | 3 | 5 | 3 |

选文规则：OpenAlex `is_oa:true` + `has_doi:true` + `type:article`，优先中国机构参与、有可直链 PDF、被引较高；剔除许可为空或 `other-oa` 的记录。各主题的 `question` 与 `selection` 字段记录了检索意图，逐篇来源与 DOI 见 manifest 与 `verification.json`。

## 机器抽取（摘要级，2026-11-14）

人工示例只有 10 条，无法覆盖 30 篇。为避免把「10 条示例」说成「全量抽取」，CiteMap 增加了一层**摘要级机器抽取**，并把人工核对显式抽成 60 格：

1. **摘要**：`scripts/fetch_citemap_abstracts.py` 按 `openalex_id` 取 OpenAlex `abstract_inverted_index` 并还原为文本；30 篇中 29 篇有摘要（48,177 字符），1 篇无摘要，不补造。
2. **抽取**：`scripts/extract_citemap_auto.py` 每篇摘要 + 主题 claims 调一次本地模型，只接受 `support / contradict`；`quote` 必须是摘要的逐字子串，否则丢弃；输出 `extractor="auto:abstract-only"`、`verified=false`，不写回人工文件。
3. **结果**：两个主题共 **42 条机器证据、覆盖 25/30 篇**（ai_education 25 条/11 篇；medical_imaging 17 条/14 篇），逐字引用不合格 **0**。
4. **对人工示例的检查**：10 条人工示例中机器覆盖 6 条（coverage 0.60）；这 6 条 stance 与人工一致 6/6（1.0）。**这只说明在这 10 对上一致，不是全量准确率**，也不能外推为「机器抽取准确率 60%」。
5. **60 格人工核对**：`scripts/build_citemap_verification.py` 每主题抽 30 格（证据格优先，另含无证据格），共 60 格，seed 20261114，写入 `verification_packet.json`。产品页的「核对模式」逐格记录 `ok / issue / skip` 到 `verification_state.json`；**只有人实际点击后才计数**，脚本与演示不预填。

复现命令：

```bash
PYTHONPATH=src python scripts/fetch_citemap_abstracts.py
PYTHONPATH=src python scripts/extract_citemap_auto.py --topic ai_education --workers 3
PYTHONPATH=src python scripts/eval_citemap_auto.py
PYTHONPATH=src python scripts/build_citemap_verification.py
```

边界：只读摘要，不读全文/图表；一篇摘要可能对应多条 claim，模型只返回它认为有证据的条目；42 条不是「全部证据」，25/30 篇也不是「30 篇都有结论」；机器证据在 UI 上单独标注，不与人工示例混排；60 格核对未完成前，页面不得显示「已验证」。

## 布局与去重（1.7.13）

桌面端（≥961px）的 CiteMap 采用**固定高度两栏**：`.ctm-layout` 高度 `clamp(680px, 100vh - 220px, 920px)`，左列论文清单与右列详情各自独立滚动，详情标题吸顶。详情按**断言分组**：每组先显示断言正文、方向、人工/机器证据数，再铺全宽证据卡（人工在前、机器虚线在后）；空分组有说明。切换论文时详情自动回到顶部；窄屏（≤960px）保持单列自然流。

人工示例与机器抽取会在同一 `claim_id` 下重复。前端按归一化（全半角/空白）后的**逐字包含**判断：较短引用 ≥40 字符且被较长引用包含时视为同一条，合并到人工卡片；机器区只显示未重复证据，主题统计显示“已合并重合”。当前 AI 教育合并 7 条、医学影像 1 条，AI 教育机器证据 25→18。被合并的抽样格仍渲染在人工卡片上，60 格核对按钮不会丢失。

这不是“自动验证”：`verified` 仍为 `false`，60 格仍需真人点击；AI 预核对只能在备注中说明。

## Schema 总览

所有实体都是 frozen dataclass，JSON 字段名与 dataclass 字段一一对应。加载器拒绝未知字段与缺失必填字段，因此 JSON 是 schema 的**严格**表示。

### Topic

| 字段 | 类型 | 必填 | 约束 / 说明 |
| --- | --- | --- | --- |
| `topic_id` | string | 是 | `^[a-z][a-z0-9_]{1,39}$`，全仓库唯一 |
| `name_zh` | string | 是 | 中文名，≤120 字符 |
| `name_en` | string | 是 | 英文名，≤160 字符 |
| `question` | string | 是 | 该主题要回答的总问题，≤600 字符 |
| `description` | string | 否 | 默认 `""`，≤2000 字符 |

同一主题的 `Topic` 必须同时出现在 corpus 与 extractions 中，且**逐字段完全一致**；不一致会报「主题元数据不一致」。

### Paper

| 字段 | 类型 | 必填 | 约束 / 说明 |
| --- | --- | --- | --- |
| `paper_id` | string | 是 | 主题内唯一，如 `edu-001`；正则见 `_record_id` |
| `title` | string | 是 | 原文标题，≤1200 字符 |
| `authors` | string[] | 是 | 至少 1 位，按原文顺序 |
| `year` | int | 是 | 1900–2100 |
| `venue` | string | 是 | 期刊/会议名 |
| `doi` | string | 是 | 规范化为裸 DOI；主题内大小写不敏感唯一 |
| `openalex_id` | string | 是 | `^W\d{6,}$`，主题内唯一 |
| `url` | string | 是 | `https?://`，通常为 `https://doi.org/<doi>` |
| `license` | string | 是 | 非空、小写；`is_oa=true` 时不得为 `unknown` / `closed` |
| `is_oa` | bool | 是 | 是否开放获取 |
| `fulltext_available` | bool | 是 | `true` 时必须 `is_oa=true` 且 `oa_url` 非空 |
| `oa_url` | string | 否 | 默认 `""`；出版社/arXiv 的开放获取直链 |
| `oa_status` | enum | 否 | `gold / hybrid / green / bronze / diamond / closed / unknown`，默认 `unknown` |
| `language` | string | 否 | 默认 `en`，小写 |
| `topic_id` | string | 否 | 默认 `""`；如填写必须等于所属主题 |
| `cn_affiliated` | bool | 否 | 默认 `false`；是否含中国机构作者 |
| `cited_by` | int | 否 | 默认 0，非负；OpenAlex 快照值 |
| `source` | string | 否 | 默认 `openalex` |
| `notes` | string | 否 | 默认 `""`；例外、许可差异等说明 |

### Claim

| 字段 | 类型 | 必填 | 约束 / 说明 |
| --- | --- | --- | --- |
| `claim_id` | string | 是 | 主题内唯一，如 `edu-c1` |
| `topic_id` | string | 是 | 必须等于所属主题 |
| `text` | string | 是 | 待检验断言，一条只表达一个可证伪命题 |
| `population` | string | 否 | 断言适用人群/对象 |
| `outcome` | string | 否 | 结果变量 |
| `direction` | enum | 否 | `"" / positive / negative / no_effect / mixed / unclear`，默认 `""` |
| `notes` | string | 否 | 默认 `""` |

### Method

| 字段 | 类型 | 必填 | 约束 / 说明 |
| --- | --- | --- | --- |
| `method_id` | string | 是 | 如 `edu-m01` |
| `design` | string | 是 | 研究设计（RCT、横断面问卷、回顾性多中心等） |
| `sample_size` | int \| null | 否 | 若填写须 ≥1，且与同条证据的 `Sample.size` 一致 |
| `population` | string | 否 | 研究总体 |
| `setting` | string | 否 | 场景/机构 |
| `instruments` | string[] | 否 | 量表、设备、数据集等 |
| `analysis` | string | 否 | 统计/建模方法 |
| `risk_of_bias` | enum | 否 | `low / some / high / unclear`，默认 `unclear` |

### Sample

| 字段 | 类型 | 必填 | 约束 / 说明 |
| --- | --- | --- | --- |
| `sample_id` | string | 是 | 如 `edu-s01` |
| `size` | int | 是 | ≥1 |
| `unit` | string | 是 | 人、患者、影像、数据集等 |
| `population` | string | 是 | 抽样总体 |
| `setting` | string | 否 | 机构/地区/时间 |
| `country` | string | 否 | ISO 名称或常用名 |
| `recruitment` | string | 否 | 招募/纳排方式 |

### Evidence

| 字段 | 类型 | 必填 | 约束 / 说明 |
| --- | --- | --- | --- |
| `evidence_id` | string | 是 | 如 `edu-e01` |
| `claim_id` | string | 是 | 必须引用本主题内存在的 Claim |
| `paper_id` | string | 是 | 必须引用本主题 manifest 中存在的 Paper |
| `stance` | enum | 是 | `support / contradict / neutral` |
| `summary` | string | 是 | 中文要点，≤2000 字符；写清方向、对象、幅度 |
| `quote` | string | 否 | 原文逐字摘录；有 `quote` 必须有 `locator` |
| `quote_lang` | string | 否 | 默认 `en`，小写 |
| `locator` | string | 否 | 如 `Abstract`、`Abstract (arXiv:2305.01185)`、页码/章节 |
| `method` | Method \| null | 否 | 默认 `null` |
| `sample` | Sample \| null | 否 | 默认 `null` |
| `confidence` | float | 否 | 0.0–1.0，默认 0.5，见下节 |
| `extracted_by` | string | 否 | 默认 `human` |
| `verified` | bool | 否 | 默认 `false`；`true` 时必须有 `locator` |
| `notes` | string | 否 | 默认 `""`；抽取限制（如「仅读摘要」） |

### Gap

| 字段 | 类型 | 必填 | 约束 / 说明 |
| --- | --- | --- | --- |
| `gap_id` | string | 是 | 如 `edu-g1` |
| `topic_id` | string | 是 | 必须等于所属主题 |
| `kind` | enum | 是 | `evidence / method / sample / outcome / theory` |
| `description` | string | 是 | 缺什么、为什么重要，≤2000 字符 |
| `related_claim_ids` | string[] | 否 | 默认 `[]`；引用的 Claim 必须存在 |
| `severity` | enum | 否 | `low / medium / high`，默认 `medium` |
| `rationale` | string | 否 | 严重性判断依据 |

### 文件级包装

`corpus/<topic>.json` → `CorpusManifest`：

```json
{
  "schema_version": "1.0",
  "topic": {"topic_id": "ai_education", "name_zh": "人工智能教育",
            "name_en": "AI in Education", "question": "..."},
  "papers": ["...15 个 Paper..."],
  "generated_at": "2026-11-14",
  "source": "OpenAlex works API ...",
  "selection": "检索式与筛选规则 ...",
  "notes": "..."
}
```

`extractions/<topic>.json` → `EvidenceMap`：

```json
{
  "schema_version": "1.0",
  "topic": {"...与 corpus 完全一致..."},
  "claims": ["..."],
  "evidence": ["..."],
  "gaps": ["..."],
  "extractor": "boundary（人工示例抽取）",
  "extracted_at": "2026-11-14",
  "protocol": "抽取与置信度协议 ...",
  "notes": "..."
}
```

## Stance：立场判定

立场是**证据相对于某条 claim** 的关系，不是论文的整体态度。同一篇论文可以支持 claim A、反驳 claim B。

| stance | 判定标准 | 例 |
| --- | --- | --- |
| `support` | 原文结果的方向与 claim 一致，且能定位到具体结果 | 多中心研究报告模型辅助使医生准确率 +8.3%，支持「DL 接近专科医生水平」 |
| `contradict` | 原文结果的方向与 claim 相反，或直接否定 claim 的前提 | 调查显示多数参与者认为教师不可替代，反驳「GenAI 将取代教师」 |
| `neutral` | 原文报告了相关结果，但方向不明、混合或不足以判定（含仅报告可行性/一致性） | 只说「模型可用」，未报告相对医生的性能 |

判定的四条硬规则：

1. **一条 evidence 只对应一条 claim、一篇 paper**；同一对 claim/paper 不重复建条目。
2. 立场必须由**原文结果**支撑，不能由论文标题、摘要中的主观措辞或二手综述推断；`summary` 与 `quote` 冲突时以 `quote` 为准。
3. 方向一致但**人群/场景不可比**时，不升格为 support/contradict，应记 `neutral` 并在 gap 中说明外推限制。
4. 仅「论文提到该主题」不构成证据；必须有可定位的结果句。

## Confidence：置信度协议

`confidence` 表示「该条抽取作为这条 claim 的证据有多可靠」，不是论文质量分。评分只取决于可核实的抽取质量：

| 区间 | 含义 | 典型情形 |
| --- | --- | --- |
| 0.80–1.00 | 强 | 已读全文/结果表，样本、设计、效应量、定位均可核对 |
| 0.65–0.79 | 中 | 读摘要 + 可定位结果句，关键数字与设计清楚，但未核全文 |
| 0.50–0.64 | 弱 | 仅摘要、结果为自评/相关性、方向清楚但证据强度有限 |
| < 0.50 | 存疑 | 摘要信息不足、结论模糊，仅作占位，需人工复核 |

当前 10 条示例的约束：

- 全部 `extracted_by = "human"`，但 `verified = false`：只核到摘要，未逐页核全文。
- 摘要级抽取的 `confidence` 上限为 0.75；`notes` 明确写「仅读摘要，未读全文」。
- `quote` 必须逐字出现在 OpenAlex 摘要（或 arXiv 摘要）中；构建时有断言，测试只校验 `quote ⇒ locator` 的结构约束（不重新抓取原文）。
- 修改 `confidence` 或 `verified` 不改变 stance；若核全文后发现方向变化，应新增/修订 evidence 并记录 `notes`，而不是静默改分。

## Gap：证据缺口

`gap` 不是「未来工作」，而是**当前 claim–evidence 集合中缺失的证据类型**，用于指导下一轮检索/实验。

| kind | 含义 | 示例 |
| --- | --- | --- |
| `evidence` | 缺少能直接检验 claim 的研究 | 缺少以客观成绩为终点、含对照组的因果设计 |
| `method` | 现有研究设计不足以支撑因果/泛化 | 多中心仍为回顾性，缺少前瞻性试验与多读者研究 |
| `sample` | 样本量、抽样框或人群覆盖不足 | 不平等证据仅 3 所小学、25 名参与者 |
| `outcome` | 结果变量缺失或过于单一 | 只测自评收益，未测学习迁移/教学任务质量 |
| `theory` | 机制解释或理论框架缺失 | 未解释为何 AI 素养调节收益 |

严重性：`high` = 直接影响 claim 能否成立；`medium` = 限制外推但方向仍可讨论；`low` = 完备性改进。每条 gap 应尽量用 `related_claim_ids` 绑定受影响断言。

当前语料共 6 条 gap：教育 3 条（evidence/high、sample/medium、outcome/medium），医学影像 3 条（evidence、method、outcome，均 high）。

## 许可、版权与 DOI 核验

- 30 篇论文均为开放获取，`license` 无空值；仓库**不提交任何 PDF 全文**，`oa_url` 仅指向出版社/arXiv 的开放获取链接。
- `fulltext_available=false` 表示 OpenAlex 未给出可直接下载的 PDF（只有 landing page），不代表论文不开放：`ai_education` 为 edu-011，`medical_imaging` 为 med-012、med-013。
- CC BY-NC-ND / CC BY-NC-SA 材料仅用于非商业研究引用；引用原文时保留出处，不衍生改写。
- `verification.json` 记录每篇论文的双通道核验：Crossref works API（`status`、题名相似度、许可）与 doi.org handle API（`responseCode`）。

核验结果（2026-11-14）：

| 指标 | 结果 |
| --- | --- |
| 论文数 | 30 |
| Crossref 解析成功 | 30 / 30 |
| doi.org handle 成功 | 30 / 30 |
| 题名完全一致 | 29 |
| 题名前缀一致 | 1 |
| 题名不一致 | 0 |
| 许可与 Crossref 一致 | 28 |
| 许可无法核验 | 2 |
| 许可冲突 | 0 |

已知例外（均写入 `verification.json` 的 `note`，不是数据错误）：

1. `edu-010`（`10.25159/1947-9417/18869`）：Crossref 题名截断为 “Revisiting Techno-Optimism”，相似度 0.188；完整 OpenAlex 题名为 “Revisiting Techno-Optimism: Multidimensional Inequalities in AI Education across Urban, Suburban, and Rural Primary Schools in China”，前缀匹配确认同一作品。
2. `edu-014`（`10.1016/j.stueduc.2024.101395`）：期刊 Crossref 仅给 Elsevier TDM 链接，绿色 OA 版本在 arXiv（`2305.01185`，cc-by-nc-sa）；`license_consistent=null`，manifest 许可按 arXiv 记录。
3. `med-009`（`10.2196/85538`）：Crossref `license` 数组为空，`license_consistent=null`；OpenAlex 记录为 cc-by。

复现核验时，请同步更新 `checked_at` 与逐篇记录，不要只改汇总计数。

## Python API

```python
from citeguard import evidence_map as em

topics = em.list_topics()                 # 主题摘要列表（计数从文件重算）
base = em.DEFAULT_DATA_DIR
corpus = em.load_corpus(base / "corpus" / "ai_education.json", expected_papers=15)
emap = em.load_map(base / "extractions" / "ai_education.json",
                   corpus=corpus, expected_evidence=5)
payload = em.topic_payload("ai_education")  # JSON-ready dict，供 Web 层直接返回
```

`load_corpus()` / `load_map()` 接收**文件路径**并按需校验论文数、证据数；`topic_payload()` 走 `index.json` 指针，是 Web 层最省事的入口。

关键类：`Topic`、`Paper`、`Claim`、`Method`、`Sample`、`Evidence`、`Gap`、`CorpusManifest`、`EvidenceMap`；枚举：`Stance`；异常：`EvidenceMapError`（基类）、`UnknownTopicError`（未知主题，带 `.topic_id` / `.known`）。

`topic_payload()` 的返回结构：

```json
{
  "schema_version": "1.0",
  "topic": {"topic_id": "...", "name_zh": "...", "name_en": "...", "question": "..."},
  "papers": [...],
  "claims": [{"claim_id": "...", "text": "...", "evidence_ids": ["..."], "stance_counts": {"support": 1, "contradict": 0, "neutral": 0}}],
  "evidence": [...],
  "gaps": [...],
  "counts": {"papers": 15, "claims": 4, "evidence": 5, "gaps": 3, "stances": {...}},
  "provenance": {"corpus": "corpus/ai_education.json", "extractions": "extractions/ai_education.json",
                 "generated_at": "...", "extracted_at": "...", "extractor": "...",
                 "corpus_source": "..."},
  "verification": {"checked_at": "...", "method": "...", "summary": {...}}
}
```

`verification` 键仅在 `verification.json` 存在时出现；Web 层可原样透传，不必二次解析。

## Web 接口契约（供队长接入）

本任务只负责模块与数据，**不修改** `web/app.py`、`web/templates`、`web/static`。如要接入现有 FastAPI + Jinja2 应用，建议契约如下：

| 方法与路径 | 入参 | 成功响应 | 错误 |
| --- | --- | --- | --- |
| `GET /api/citemap/topics` | 无 | `200 {"schema_version": "1.0", "topics": [主题摘要]}` | `500 {"ok": false, "error": "..."}` |
| `GET /api/citemap/{topic_id}` | 路径参数 `topic_id` | `200` + `topic_payload(topic_id)` 原样 JSON | 未知主题 `404 {"ok": false, "error": "unknown topic", "known_topics": [...]}`；schema/IO 错误 `500 {"ok": false, "error": "..."}` |
| `GET /citemap` | 查询参数 `topic`（可选） | `200` HTML；默认展示 `index.json` 首个主题；段落含 claim 卡片、stance 徽标、evidence（summary/quote/locator/confidence）、gap 列表 | 未知 `topic` → `404` HTML/JSON 均可，但不得 500 |

实现要点：

- 捕获 `em.UnknownTopicError` → 404（`exc.known` 可直接作为 `known_topics`）；其余 `em.EvidenceMapError` → 500，错误信息含字段名，便于排查。
- 数据为仓库内静态 JSON，可按需加 `Cache-Control: public, max-age=300`；`--check` 适合放在启动自检或 CI，而不是每个请求。
- 页面不加载 PDF、不内嵌全文；quote 以文本展示并附 DOI 链接。
- 当前 `mkdocs.yml` 的 nav 未包含本页（该文件不在本任务写权限内），需要时请队长补 `- CiteMap 证据地图: evidence_map.md`。

## 新增主题

1. 在 `corpus/` 与 `extractions/` 新增 `<topic_id>.json`，`Topic` 两处完全一致。
2. 在 `index.json` 的 `topics` 中加入 `{topic_id, name_zh, name_en, question, corpus, extractions}`；路径必须是相对数据目录、且不能越界。
3. 运行 `python -m citeguard.evidence_map --check`；计数会自动重算。
4. 若抓取了新 DOI 核验，更新 `verification.json`（逐篇记录 + 汇总）。
5. 跑 `pytest tests/test_evidence_map.py -q`；若新增主题改变了示例总数断言，请同步调整测试中的 `EXPECTED_TOPICS`/`EXPECTED_EVIDENCE` 常量，而不是放宽断言。

## 设计决策与限制

- **零重依赖**：只用标准库，避免为 schema 引入 pydantic；代价是校验器需手写，但可精确控制中文错误信息与严格字段检查。
- **严格 JSON**：未知字段直接报错，防止「拼错字段名被静默忽略」；重复键由 `read_json` 拒绝，避免后值覆盖前值。
- **人工示例而非自动抽取**：10 条 evidence 用于打通 schema → API → 页面链路并校准置信度，不冒充系统综述；自动抽取是后续 B2/Live 的工作。
- **只读摘要**：当前 `verified=false`，`confidence ≤ 0.75`；任何对外展示应同时显示该限制，避免被误读为全文核验。
- **许可保守**：不提交 PDF；NC/ND 条款在文档中显式提示，避免下游误用。
- **不做跨主题推断**：每个主题独立索引、独立校验；跨主题共享的只有代码与协议。

## 验收对照（B1a）

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 2 主题 × 15 篇 manifest | ✅ | `corpus/ai_education.json`、`corpus/medical_imaging.json`，各 15 篇 |
| 许可字段无空 | ✅ | 30 篇 `license` 均为 CC 系列；测试 `test_every_paper_has_open_license_and_bibliographic_metadata` |
| 10 条人工示例抽取 | ✅ | 每个主题 5 条，共 10 条；含 quote/locator/method/sample/confidence |
| schema 校验 / manifest 唯一性 / 抽取可解析 | ✅ | `pytest tests/test_evidence_map.py -q` → 87 passed |
| DOI 可解析（队长抽查 5 篇） | ✅（30/30 已预核验） | `verification.json`：Crossref 30/30、handle 30/30 |
