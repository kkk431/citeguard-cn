# E3 CiteMap 半自动扩展：候选 + 人工确认

> 结论先行：本轮只生成**机器候选**，没有写入任何人工证据；候选不是证据，未人审，不能据此宣称准确率。真实运行 `ai_education` 得到 **9 条候选**、9 篇来源论文和一份空白人工确认清单。

## 1. 目标与边界

CiteMap 的人工层已经覆盖 4 个主题、每主题 10 条人工证据。继续扩展时，完全手写摘要证据成本高，完全自动写入又会把机器判断伪装成人工证据。E3 把流程拆成两段：

1. 机器从开放论文摘要中提出**候选 claim + 逐字摘要句 + 来源论文**；
2. 人类在 CSV 中逐条选择 `accept` / `reject` 并写 note；
3. 只有显式 `--write-human-layer` 的 promote 才会把确认结果追加到 `extractions/<topic>.json`。

边界：

- `machine=true`、`needs_human=true`、`status=pending`；
- 候选写入独立目录 `data/evidence_map/expansion/`，不写 `evidence` / `auto_evidence`；
- 不做“准确率”宣称：候选生成是启发式召回，不是评测结果；
- 不读全文、不判断论文结论真假；`locator` 只到 `Abstract`；
- 不改 `web/app.py`、模板、JS、CSS；不自动改人工层。

## 2. 真实运行结果（2026-11-27）

运行环境：本地仓库，离线读取 `ai_education` 已有 corpus、人工抽取和 `abstracts.json`；不依赖 OpenAlex 实时网络。

```bash
python scripts/citemap_expand.py \
  --topic ai_education \
  --limit 15 \
  --min-candidates 5 \
  --summary data/experiments/opt_e3_citemap_expand_2026-11-27.json
```

结果：

| 指标 | 值 |
|---|---:|
| 主题 | `ai_education`（人工智能教育） |
| 候选数 | **9** |
| 来源论文数 | 9 |
| 候选类型 | `new_claim`（摘要结果句提出的新 claim） |
| 人工确认队列 | 9 行，`decision` / `note` / `reviewer` 全空 |
| 写入人工层 | **否**（`human_layer_written=false`） |
| 跳过 | 1 篇无摘要、1 条重复、4 篇无明确结果句 |

来源论文：`edu-001`、`edu-002`、`edu-003`、`edu-004`、`edu-005`、`edu-008`、`edu-009`、`edu-012`、`edu-015`。

产物：

- `data/evidence_map/expansion/ai_education_candidates.json`：完整候选（含 `source_text`，便于复核逐字性）；
- `data/evidence_map/expansion/ai_education_review.csv`：人工确认清单，空白决策列；
- `data/experiments/opt_e3_citemap_expand_2026-11-27.json`：本次运行摘要与边界。

## 3. 候选如何生成

### 3.1 输入模式

| 模式 | 输入 | 行为 |
|---|---|---|
| 现有主题（默认，离线） | `--topic ai_education` | 读 `data/evidence_map/corpus/<topic>.json`、`extractions/<topic>.json`、`abstracts.json`；不联网 |
| 外部查询（可选） | `--query "..."` 或一个/多个 `--doi` | 复用 `citemap_builder.search_works` / `lookup_dois` 获取 OpenAlex work；仍只生成候选 |

本轮真实运行使用现有主题离线模式。原因：OpenAlex 实时调用出现 HTTP 429（Too Many Requests），不能把网络不稳定性带进真实运行；本地主题的摘要足以验证候选契约。

### 3.2 候选 claim 的选取

每篇论文的摘要先用 `citemap_verify.split_sentences` 分句，再选**含明确结果线索**的句子；`_STRONG_RESULT_CUES` 包括 `results show(ed)`、`findings suggest/indicate/revealed`、`show that`、`significantly`、`accuracy`、`outperform` 等。没有结果线索时返回空，宁可跳过也不把背景/方法句包装成 claim。

选中的句子同时作为：

- `claim`：机器提出的新断言（待人工改写/确认）；
- `quote`：逐字摘要句；
- `source_text`：摘要全文，供 promote 时再次校验 `quote in source_text`。

本轮不会把候选硬映射到现有 4 条中文断言。现有断言是中文，摘要多为英文；在没有翻译/判定模型时，词项重叠为 0，硬映射会制造“看起来匹配”的伪证据。因此候选 claim 是论文自身的结果句，人工确认时再决定它是否值得成为主题里的新 claim。

> 这是**保守召回**，不是语义相似度匹配；它不保证候选覆盖主题的全部观点，也不保证每个候选都值得保留。

### 3.3 去重

- 与人工证据/auto 证据的 quote 完全相同：跳过；
- 与现有 claim 文本完全相同：跳过；
- 候选之间 quote 完全相同：跳过；
- 同一篇论文在本轮最多产生 1 条候选。

## 4. 候选记录契约

`ai_education_candidates.json` 顶层：

```json
{
  "schema_version": "1.0",
  "topic_id": "ai_education",
  "topic": {"topic_id": "...", "name_zh": "...", "name_en": "...", "question": "...", "description": "..."},
  "generated_at": "2026-11-27",
  "mode": "existing-topic",
  "method": "候选 claim=摘要结果句；quote=同一句逐字摘要；stance 仅为机器提议；未人审。",
  "boundaries": ["..."],
  "counts": {"candidates": 9, "pending": 9, "skipped": {"no_abstract": 1, "duplicate": 1, "no_sentence": 4}},
  "candidates": []
}
```

单条候选至少包含：

| 字段 | 说明 |
|---|---|
| `candidate_id` | `cand-<topic>-NNN` |
| `candidate_type` | 本轮为 `new_claim` |
| `topic_id` / `claim_id` | 主题与拟新增 claim id（`exp-<topic>-cNNN`） |
| `claim` | 机器提出的断言（待人工确认/改写） |
| `quote` | 摘要中的逐字句 |
| `locator` | `Abstract` |
| `quote_lang` | 语言标记 |
| `stance` | 机器提议的立场（本轮均为 `support`，仅表示候选与自身句子一致；不是核验结论） |
| `confidence` | 机器启发式分数，不是概率保证 |
| `machine` / `needs_human` | 恒为 `true` / `true` |
| `status` | `pending`（未人审） |
| `source` / `source_kind` | 来源通道，如 `existing-topic-abstract` / `abstract` |
| `source_title` / `source_url` | 来源论文 |
| `paper` | `paper_id/title/year/venue/doi/url/license/fulltext_available` |
| `source_text` | 摘要全文，复核 quote 逐字性 |
| `notes` | 机器候选边界提示 |

CSV 人工确认列：`candidate_id, topic_id, claim_id, claim, paper_id, doi, source, quote, locator, stance, confidence, machine, needs_human, decision, note, reviewer`。

## 5. 人工确认与 promote

### 5.1 填清单

在 `ai_education_review.csv` 中逐行填写：

- `decision`: `accept` 或 `reject`（空值不合法）；
- `note`: 确认理由、改写建议、为什么不收录；
- `reviewer`: 姓名/代号。

CSV 初始全部空白，脚本不会自动勾选。

### 5.2 生成待应用 patch

```bash
python scripts/citemap_expand.py \
  --topic ai_education \
  --promote cand-ai_education-001 \
  --decision accept \
  --reviewer alice \
  --note "摘要句与断言一致，保留；人工改写 claim 后再入层"
```

默认只写 `data/evidence_map/expansion/promotions/<candidate_id>.json`，**不改** `extractions/ai_education.json`。

### 5.3 显式写入人工层

```bash
python scripts/citemap_expand.py \
  --topic ai_education \
  --promote cand-ai_education-001 \
  --decision accept \
  --reviewer alice \
  --write-human-layer
```

写入前会：

1. 校验 candidate 的 `machine/needs_human/status/stance`；
2. 校验 `quote in source_text`；
3. 校验论文在该主题 corpus 中，DOI 与 corpus 一致；
4. 校验新 claim id 不存在（本 spike 只 promote 新 claim 候选）；
5. 用 `evidence_map.Claim.from_dict` / `Evidence.from_dict` / `EvidenceMap.from_dict` / `validate_map` 验证；
6. 追加到 `extractions/<topic>.json`，并写 patch 留痕。

写入后的 evidence 标记：

- `extracted_by="human:promoted-candidate"`；
- `verified=true`；
- `notes` 记录 candidate id、reviewer、note。

重复 promote 同一 claim 会被拒绝，避免静默重复。

## 6. 测试

新建 `tests/test_citemap_expand.py`，8 个测试全部通过：

```bash
python -m pytest tests/test_citemap_expand.py -q
# 8 passed
```

覆盖：

1. 真实 `ai_education` 主题生成 ≥5 条候选，字段齐全、quote 逐字、claim/quote 一致；
2. 生成/写 CSV 不改变人工抽取文件字节；CSV 决策列为空；
3. 空白、非法、`pending` 决策被拒绝；
4. accept 生成可被 `evidence_map.Evidence.from_dict` 验证的 patch，默认不写人工层；
5. 显式 `write_human_layer=True` 才追加 claim/evidence，重复 promote 被拒绝；
6. 篡改 quote 被拒绝，生成阶段 quote 去重；
7. 重复 claim id 的 promote 被拒绝；
8. 空主题、候选不足、外部 `works=[]` 抛 `ExpandError`。

测试用 `tmp_path` 复制主题数据，不污染真实人工层。

## 7. 未做 / 风险

- **未做人工确认**：9 条候选全部 pending，没有任何一条被写成人工证据；需产品/研究同学逐条审核。
- **候选 claim 是论文结果句**，并非主题级规范断言；可能过长、含章节标签残留或只覆盖摘要的一个侧面。人工确认时应改写/拆分。
- **仅摘要**：没有读全文，不验证全文是否存在相反结果；`locator=Abstract`。
- **启发式召回**：结果句识别与去重是规则，不是语义模型；可能漏掉好候选，也可能保留弱候选。
- **外部 DOI/query 模式**未做真实网络运行；OpenAlex 429 时脚本会给出错误并退出，不会伪造候选。
- **promote 只支持新 claim**：若要把候选挂到既有 claim 上，需要人工先建立映射；本轮没有自动映射，避免中文 claim/英文摘要的伪匹配。
- **不改 web**：本轮没有接产品页面；JSON/CSV 是数据层交付。
- **旧测试的 CSV 断言**：仓库已有的 `test_data_directory_contains_no_pdf_files` 只允许 `data/evidence_map/` 下出现 `.json/.md`，本轮按任务要求新增了人工确认 `.csv`；该旧断言需要维护者放行 `.csv`（本轮未越界改旧测试）。任务自身的 `tests/test_citemap_expand.py` 8 个测试全部通过。
- **无准确率**：9 条候选不能用于计算 precision/recall，也不能对外宣称“扩展了 9 条证据”。

## 8. 文件清单

- `scripts/citemap_expand.py`（新建）：候选生成、CSV、promote 校验、CLI；
- `tests/test_citemap_expand.py`（新建）：8 个测试；
- `data/evidence_map/expansion/ai_education_candidates.json`：真实候选；
- `data/evidence_map/expansion/ai_education_review.csv`：空白人工确认清单；
- `data/experiments/opt_e3_citemap_expand_2026-11-27.json`：运行摘要；
- `docs/optimization/e3_citemap_expand.md`：本文档。

未修改 `src/citeguard/evidence_map.py`（现有 schema 已足够承载 promote 校验）；未修改 `web/app.py`、模板、JS、CSS。
