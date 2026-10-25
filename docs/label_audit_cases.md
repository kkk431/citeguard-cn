# ClaimSupport-CN 标签审计：产品与 LLM 共识的 10 条分歧

> 这是 **LLM 共识审计**，不是人工金标准。三个独立模型（DeepSeek-Chat、DeepSeek-Reasoner、
> Qwen3-8B）在固定 rubric 下只看 claim + evidence 盲标；具体口径与局限见
> [data/claimsupport_cn/README.md](../data/claimsupport_cn/README.md) §10。

## 数字先摆清楚

| 口径 | 结果 |
|---|---|
| 产品（托管 v10）vs 构造标签（100 条） | 0.9597 macro-F1 / 0.950 acc |
| 多数票 vs 构造标签 | 0.89 一致率 / κ 0.8425（11 条分歧） |
| 产品 vs 多数票 | 0.90 准确率 / 0.9049 macro-F1（10 条分歧） |
| DeepSeek-Reasoner vs 构造标签 | 0.969 一致率 / κ 0.957（98/100） |

两个口径都报，不挑高的说。下面逐条看这 10 条产品-多数票分歧——重点不是"谁对"，
而是**分歧属于哪一类**。

## 10 条分歧逐条

| id | 构造标签 | 产品 | 多数票 | 类型 | 关键事实 |
|---|---|---|---|---|---|
| cs-0025 | partial | partial | support | A 背景从句未覆盖 | claim 开头「与疾病网络的复杂性一致」未出现在 evidence；产品判 partial，多数票忽略背景 |
| cs-0030 | partial | partial | support | A | 「作为新型体外肿瘤模型」这一背景限定未覆盖 |
| cs-0034 | partial | partial | support | A | 「随着互联网的发展」背景未覆盖 |
| cs-0037 | partial | partial | support | A | 主句比较结论覆盖，但「学习性质的调查 poly(乙烯基白酒)」未覆盖 |
| cs-0049 | partial | partial | support | A | 「作为材料准备的预告处理过程」未覆盖，仅覆盖煅烧条件 |
| cs-0024 | support | partial | support | B 产品更严格 | evidence 只复述研究目的 + 分组设计，**没有给效果结论**；产品判 partial，构造标签给 support |
| cs-0048 | support | partial | support | B 产品更严格 | claim 含「沟通能力显著优势」，evidence 只写到临床技能/应对/团队协作/满意度，未明确覆盖「沟通能力」 |
| cs-0057 | contradict | contradict | support | C 方向反转漏判 | evidence「纺织品**增强**的水泥」，claim「**削弱**的水泥」；多数票里的 DeepSeek-Chat 漏掉了反转 |
| cs-0083 | contradict | contradict | support | C | claim「技术**无效**应用」，evidence「**有效**应用」；两票 support，产品与 Reasoner 抓到反转 |
| cs-0095 | contradict | contradict | support | C | claim「**抑制**康复」，evidence「**促进**康复」；同上 |

另外两条不在这 10 条里，但很能说明构造标签的边界：

| id | 构造标签 | 产品/多数票 | 事实 |
|---|---|---|---|
| cs-0001 | partial | support / support | claim 与 evidence **逐字相同**，只是 evidence 多了一个"选择 86 例…"的设计描述；构造标签按 partial 处理 |
| cs-0056 | partial | support / support | claim 与 evidence **完全逐字相同**，构造标签按 partial 处理 |

## 怎么解读

1. **10 条分歧里 8 条产品与构造标签一致**（5 条背景从句 + 3 条方向反转）。
   也就是说，产品 vs 多数票的 0.90 主要反映**多数票在 partial 边界上更宽松**、
   以及**两票模型漏掉 token 级否定**，不是产品独有的错误。
2. **2 条产品比构造标签更严格**（cs-0024、cs-0048）：证据只重复研究目的/少一个维度时，
   产品坚持 partial。这是设计选择——引用核验宁可提示"未完全覆盖"，也不要放过
   "只重复了标题、没给结果"的引用。代价是这类样本上比构造标签低。
3. **方向反转（cs-0057/0083/0095）说明 LLM 共识不能当金标准**：DeepSeek-Chat 和
   Qwen3-8B 在这三条上都投了 support；如果按多数票做评测，产品反而会被判错——
   而产品恰恰是抓到了"增强/削弱""有效/无效""促进/抑制"的。
4. **cs-0001、cs-0056** 是构造标签自己的边界问题（逐字相同但 evidence 多了设计描述），
   三个模型都判 support；这也解释了为什么"多数票 vs 构造标签"有 11 条分歧。

## 结论与用法

- 对外的主数字仍用 **构造标签口径 0.9597**（可复现、标签由构造决定），
  同时并列 **LLM 共识口径 0.90**，并说明 10 条分歧的构成。
- **不要**把"LLM 共识 0.90"说成人工评测，也不要把某一条模型判定当金标准。
- 产品保持"严格覆盖"策略：背景/维度缺失判 partial，方向反转判 contradict；
  这两类正是引文核验最该拦住的情况。

## 证据

- `data/claimsupport_cn/llm_annotation_deepseek.json` / `_qwen3_8b.json` /
  `_deepseek_reasoner.json`
- `data/claimsupport_cn/llm_consensus.json`（逐条 votes、majority、一致性、κ）
- `scripts/llm_annotate_support.py`、`scripts/support_llm_consensus.py`
- 产品预测：`data/claimsupport_cn/results.json`
