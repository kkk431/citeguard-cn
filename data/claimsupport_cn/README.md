# ClaimSupport-CN 数据卡

**ClaimSupport-CN** 是 CITEGUARD-CN 项目自建的**中文引文支持度（claim-level citation support）评测集**：每条样本给出一句中文 claim 和一段被引论文摘要片段（evidence），要求判定 `support / partial / contradict / no_evidence` 四分类。样本由 OpenAlex 的 CC0 元数据**程序化构造**，标签完全由构造规则决定——**不是人工标注，也没有双人标注或 κ**。

## 1. 概览

| 项 | 值 |
|---|---|
| 数据集 | ClaimSupport-CN |
| 版本 | v1（2026-10-22） |
| 规模 | 100 条（support 40 / partial 25 / contradict 15 / no_evidence 20） |
| 文件格式 | JSONL，UTF-8，LF 换行 |
| JSONL SHA-256 | `4820014a741cd8148182cc1035d5a605c16280813999dcfc15fb9a3b27c4d4a3` |
| 随机种子 | `20261022`（重建 SHA 一致） |
| 上游数据 | OpenAlex `https://api.openalex.org/works`，`filter=language:zh,has_abstract:true,type:article`（元数据 CC0 1.0） |
| 许可证 | 数据卡与数据集 **CC-BY-4.0**；上游元数据 CC0 1.0；**不 re-host 全文或完整摘要** |
| 评测对象 | `citeguard.support.judge_support`（DeepSeek `deepseek-chat`，temperature 0） |

## 2. 标签口径（构造规则，写死）

| 标签 | 数量 | 构造规则 |
|---|---|---|
| `support` | 40 | claim = 摘要中的核心句；evidence = 该句所在的摘要片段（含该句）→ evidence 直接支持 claim |
| `partial` | 25 | claim = 完整核心句；evidence = 该句中**一个承载主要论断的分句**（只支持 claim 的一部分） |
| `contradict` | 15 | claim = 把原句中一处论断换成反义词（提高↔降低、增加↔减少、正相关↔负相关、有效↔无效 等）；evidence = 原句 |
| `no_evidence` | 20 | claim = 论文 B 的核心句；evidence = **另一篇主题无关论文 A** 的摘要片段（标题/片段相似度与 CJK bigram 重叠均低于阈值） |

构造自检（`scripts/build_claimsupport.py` 内置）逐条重新推导上述规则：100/100 通过；此外对 20 条（20%）做抽样规则复核（`claimsupport_cn.spot_check.json`，0 失败）。抽样为**单标注者复核**，不构成双人标注，因此**不计算 κ**。

> 与 v1.1 支持度模块的口径一致：结果只反映 `judge_support` 的四分类判定能力，不代表人工标注一致性。

## 3. 构造方法

1. **抓取**：OpenAlex `filter=language:zh,has_abstract:true,type=article`，重建 `abstract_inverted_index` 为摘要文本（12 页 / 1425 条可用的中文摘要单元）。
2. **清洗**：NFKC；去掉 CJK 字符之间的空格（OpenAlex 按 token 拼接）；把紧邻中文的 ASCII 标点规范为全角；剥离结构化摘要标签（「目的/方法/结果/结论：」等）。
3. **取句**：按 `。！？；` 切句，每篇论文保留 1–2 个满足长度/中文占比要求的句子片段（**仅片段**）。
4. **构造**：按上表规则生成 100 条；标签由规则唯一决定。
5. **缓存**：`claimsupport_cn.sources.json` 只存每篇论文 1–2 个**句子片段**（不含完整摘要）；在缓存存在时离线重建得到字节一致的 JSONL。
6. **抽检**：20 条（20%）按构造规则逐条复核，记录在 `claimsupport_cn.spot_check.json`；0 失败。

> 说明：OpenAlex 的中文摘要字段有相当比例是**自动翻译文本**（机器翻译腔明显）。本集只用其中的句子片段做构造，claim/evidence 都来自同一段文本或明确无关的另一篇，因此逻辑关系由构造保证；但文本自然度不代表真实中文写作分布，这是已知局限。

## 4. JSONL 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `cs-0001` … `cs-0100`（打乱后编号） |
| `claim` | string | 待判定支持度的中文 claim |
| `evidence` | string | 被引论文的摘要片段（1–2 句，短片段） |
| `label` | string | `support` / `partial` / `contradict` / `no_evidence` |
| `construction` | string | 构造标记，如 `support:core_sentence`、`contradict:antonym 提高->降低` |
| `claim_source` | object | claim 来源论文：`openalex_id / title / doi / year` |
| `evidence_source` | object | evidence 来源论文（no_evidence 时与 claim_source 不同） |

示例（partial）：

```json
{"id": "cs-0004", "claim": "分析影响老年人老年护理服务的因素，并提出有效措施进行探究。", "evidence": "分析影响老年人老年护理服务的因素。", "label": "partial", "construction": "partial:evidence_is_one_assertion_clause", "claim_source": {"openalex_id": "https://openalex.org/W…", "title": "……", "doi": "10.…", "year": 2024}, "evidence_source": {"openalex_id": "https://openalex.org/W…", "title": "……", "doi": "10.…", "year": 2024}}
```

## 5. 评测结果（`results.json`）

> 当前为**两段式 judge**（v10 少样本判定 + 托管覆盖审计 v1）的正式结果；v4/v7/v8 历史结果见本节末尾。

| 项 | 值 |
|---|---|
| judge | `citeguard.support.judge_support`（两段式），`deepseek-chat`，temperature 0 |
| judge prompt | `scripts/support_prompt_v10.txt`（SHA-256 `fe9d721cfc211fb1…`） |
| 覆盖审计 prompt | `scripts/support_prompt_audit.txt`（托管端点 v1；自托管自动切 v2） |
| macro-F1 | **0.9597** |
| accuracy | **0.9500** |
| failures | 0（100/100 成功；失败会映射为 `no_evidence` 并计数） |

Per-class：

| 类别 | Precision | Recall | F1 | 支持数 | 预测数 |
|---|---|---|---|---|---|
| support | 0.9487 | 0.9250 | 0.9367 | 40 | 39 |
| partial | 0.8846 | 0.9200 | 0.9020 | 25 | 26 |
| contradict | 1.0000 | 1.0000 | 1.0000 | 15 | 15 |
| no_evidence | 1.0000 | 1.0000 | 1.0000 | 20 | 20 |

混淆矩阵（行 = 真实，列 = 预测；support / partial / contradict / no_evidence）：

```text
              pred support  partial  contradict  no_evidence
true support            37        3           0            0
true partial             2       23           0            0
true contradict          0        0          15            0
true no_evidence         0        0           0           20
```

**单段 prompt v3 历史结果（对比用）**：macro-F1 0.9005 / accuracy 0.8900；混淆矩阵 `[[38,2,0,0],[7,18,0,0],[2,0,13,0],[0,0,0,20]]`。**两段式 + v4 历史结果**：0.9328 / 0.9300；**v8**：0.9544 / 0.9500。v8 把 partial 边界写进 prompt（引用句含证据之外的目的/设计细节 → partial；证据只覆盖部分断言 → partial）；v10 再补「方向相反 → contradict」，把 contradict 从 14/15 修正到 15/15，macro-F1 提到 0.9597。

## 6. 复现命令

```bash
# 构建（首次需访问 OpenAlex；之后用片段缓存离线重建，SHA 一致）
PYTHONPATH=src python3 scripts/build_claimsupport.py

# 评测（需要 DeepSeek key；key 只走环境变量，不落盘；judge 结果缓存于 cache/support/）
DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/evaluate_support.py

# 服务器（依赖在 .pylibs）
cd /data/xyjiang/aic_mental/citeguard
PYTHONPATH=.pylibs:. python3 scripts/evaluate_support.py
```

## 7. 文件清单

| 文件 | 说明 |
|---|---|
| `claimsupport_cn.jsonl` | 100 条评测集 |
| `claimsupport_cn.meta.json` | 构造元数据（seed、口径、计数、抽检、SHA） |
| `claimsupport_cn.sources.json` | 片段级来源缓存（每篇 ≤2 句，不含完整摘要） |
| `claimsupport_cn.spot_check.json` | 20 条（20%）构造规则复核记录 |
| `results.json` | 评测结果（macro-F1/accuracy/per-class/混淆/judge 信息/逐条预测） |
| `predictions.csv` | 逐条预测明细 |
| `cache/support/` | judge API 响应缓存（复跑可复现） |
| `README.md` | 本数据卡 |

## 8. 已知局限

1. **文本质量**：OpenAlex 中文摘要多为自动翻译，存在机器翻译腔；本集不 re-host 原文，但 claim/evidence 的自然度受上游影响。
2. **构造式标签**：标签由规则决定，没有人工双标注和 κ；20% 抽检为单标注者规则复核，不能替代人工一致性统计。
3. **partial 边界模糊**：证据只给出一个分句时，judge 常判为 `support`；两段式覆盖审计后，25 条 partial 中仍有 2 条被判 support，反映四分类边界本身的模糊性，评测时应连同 per-class 一起解读。
4. **contradict**：反义替换依赖词表，部分机器翻译句的反义关系不够显式，judge 可能判 support/partial。
5. **规模**：100 条适合工程回归与演示，不足以覆盖全部学科；建议与 ClaimSupport 真实人工标注集互补使用。
6. 不评估「引用是否真实存在 / 元数据是否正确」（那是 CiteBench-CN 的任务），只评估给定 evidence 对 claim 的支持度。

## 9. 许可证与引用

- 本数据卡与 ClaimSupport-CN 数据集以 **CC-BY-4.0** 发布。
- 上游元数据来自 **OpenAlex（CC0 1.0）**；数据集只存 claim、短证据片段与来源 ID，不 re-host 全文或完整摘要。
- 引用：`ClaimSupport-CN (v1), CiteGuard-CN project, 2026`。
