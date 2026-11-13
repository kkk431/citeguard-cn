# Live 公开页 held-out 评测（5 页 / 30 句）

> 2026-11-14 实测：被引来源命中 **hit@1 = 27/30、hit@3 = 30/30**；但四档判定里 **23/30 是 no_evidence**。候选映射成功，摘要却在 page-reference 候选上为空（`src/citeguard/live_check.py:1030`）。t17 给页面候选补摘要后，同一 30 句复测：hit@1 27/30、hit@3 30/30 不变，**有逐字证据的句子 11/30（其中 8 条指向被引来源本身）**，no_evidence 降到 19/30；P50 3129.4 → 2982.7 ms，P95 10971.9 → 16088.8 ms。本集与 t13 的公开页集（18/30）**不混算**。

## 1. 目的与边界

t13 的公开页集在选页时把"被引 DOI 位于 OpenAlex `referenced_works` 前 40"当作准入条件，因此它只能检验 t12 的页面引用列表路径，不能检验 t14 新加的「正文 `[n]` → 页面参考文献」映射。t15 换一套未参与任何调参的页面，回答两个问题：

1. 在没见过的 arXiv HTML 页面上，`[n]` 能否稳定映射到页内参考文献条目？
2. 真实页面上，产品能不能把"找到来源"变成"给出四档判定与证据句"？

边界：

- 5 页 / 30 句（每页 6 句），英文；只做单次实测，不做参数搜索。
- 选样规则只看"句内有显式 `[n]`、`[n]` 在页内参考文献中存在、DOI 可解析"，**不按产品是否命中筛选**。页面与句子在 t14 落地前冻结（`data/live_eval/pages_holdout.json` 的 `generated_at` 为 2026-11-14T03:12:55+08:00，t14 完成通知为 03:15 之后）。
- hit@3 只检查"候选里是否含被引来源（标题/DOI）"，不评价 stance 判断的对错——本集没有人工 stance 金标。
- 本任务只写 `data/live_eval/` 与本文件；未改 `src/citeguard/live_check.py`、`extension/`、`web/app.py`。

## 2. 页面（5 篇，均与 t13 的 5 篇不重复）

| id | 页面 | 标题（截断） | 参考文献 | 许可 | 抓取时间 |
| --- | --- | --- | ---: | --- | --- |
| `arxiv-2611-07772` | [HTML](https://arxiv.org/html/2611.07772) | Adapt the Object to the Subject: Representative Study Material for Empirical Software Engineering | 54 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0) | 2026-11-14T03:12:55+08:00 |
| `arxiv-2610-38049` | [HTML](https://arxiv.org/html/2610.38049) | Perspective on AI and quantum open-source software | 126 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0) | 同上 |
| `arxiv-2610-24037` | [HTML](https://arxiv.org/html/2610.24037) | Benchmarking and Improvement of Artifact Segmentation Methods in H&E-Stained Whole Slide Imaging | 60 | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0) | 同上 |
| `arxiv-2610-32576` | [HTML](https://arxiv.org/html/2610.32576) | From Regulation to Engineering: Organizational Privacy Climate as Mediator | 63 | [arXiv nonexclusive-distrib 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | 同上 |
| `arxiv-2610-18926` | [HTML](https://arxiv.org/html/2610.18926) | Personalising Deformable Image Registration with Clinical Context and Deformation History for Adaptive Radiotherapy | 19 | [arXiv nonexclusive-distrib 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | 同上 |

URL 均为 `arxiv.org/html/<id>`（LaTeXML HTML5 全文，含编号参考文献列表）。许可从对应 `arxiv.org/abs/<id>` 页面的 "view license" 记录；`2610-24037` 为 NC 许可、`2610-32576` / `2610-18926` 为 arXiv 非独占分发许可，因此**只在本仓库记录 URL 与句子，不再分发全文**。

## 3. 30 句如何构造

| 规则 | 具体做法 |
| --- | --- |
| 来源 | 5 篇页面的 `<p class="ltx_p">` 正文段落，不取摘要、不取参考文献表 |
| 引用标记 | 句内必须有显式 `[n]` 或 `[n,m]`；`reference_index` 必须出现在该句标记里 |
| 编号对齐 | 按页面**显示编号** `[n]` 建索引（arXiv LaTeXML 的 `li id="bib.bibN"` 内部 id 不等于显示编号，早期按 id 索引会错配来源，已修正） |
| 长度 | 40–300 字符；本集实际 67–284 |
| 来源元数据 | `source_title` 取该 DOI 的 OpenAlex `display_name`，`source_doi` 取页面参考文献里的 DOI |
| DOI 校验 | 30/30 通过 `doi.org/api/handles/<doi>`（`responseCode=1`，2026-11-14） |
| 分布 | 5 页 × 6 句；每页选句索引见下表 |

| 页面 | 选句索引 | 对应页内编号 |
| --- | --- | --- |
| 2611.07772 | 0, 9, 18, 19, 20, 22 | 1, 4, 26, 27, 28, 32 |
| 2610.38049 | 0, 2, 6, 10, 13, 17 | 56, 4, 27, 16, 84, 10 |
| 2610.24037 | 0, 3, 9, 18, 22, 31 | 60, 13, 25, 23, 34, 5 |
| 2610.32576 | 0, 1, 2, 6, 7, 14 | 8, 15, 10, 36, 9, 62 |
| 2610.18926 | 0, 2, 3, 5, 7, 11 | 1, 6, 12, 17, 19, 7 |

每条记录恰好 7 个字段，例如：

```json
{"id": "hld-261107772-01", "sentence": "… [1] …", "source_title": "Conducting realistic experiments in software engineering", "source_doi": "10.1109/ISESE.2002.1166921", "page_url": "https://arxiv.org/html/2611.07772", "page_title": "Adapt the Object to the Subject: Representative Study Material for Empirical Software Engineering", "reference_index": 1}
```

数据校验命令（`--check` 同时检查 5 页、30 句、每页 6 句、字段齐全、`reference_index` 在句内）：

```powershell
$env:PYTHONPATH='src'; python scripts/eval_live.py --claims data/live_eval/claims_holdout.jsonl --pages data/live_eval/pages_holdout.json --check
# OK: 5 个页面 / 30 条引用句（公开页集），来源字段齐全
```

## 4. 先做一个覆盖测量：旧候选源只能看到 10/30

在跑产品之前，先量了一次"t14 之前的候选源"对本集的覆盖：对每篇页面查 OpenAlex 的 `referenced_works`，取前 40（产品的 `MAX_REFERENCED_WORKS=40`），看 30 条 gold DOI 是否在其中。

| 页面 | OpenAlex `referenced_works` 总数 | 前 40 内 gold |
| --- | ---: | ---: |
| 2611.07772 | 0（2026 预印本尚未入库） | 0/6 |
| 2610.38049 | 50 | 0/6 |
| 2610.24037 | 39 | 5/6 |
| 2610.32576 | 1 | 0/6 |
| 2610.18926 | 15 | 5/6 |
| 合计 | — | **10/30** |

含义：t14 之前的路径在这套数据上几乎看不到被引来源，所以本集是真正检验 `[n]` 映射的 held-out，而不是给旧路径"送分"；反过来，也不能拿这 10/30 的覆盖率去推断任何产品结论（它只是候选源可用性测量，测量脚本为临时脚本，未入库）。

## 5. 结果

### 5.1 t14 落地后（2026-11-14 03:18，基线）

```powershell
$env:PYTHONPATH='src'; python scripts/eval_live.py --claims data/live_eval/claims_holdout.jsonl --pages data/live_eval/pages_holdout.json --out data/live_eval/live_eval_holdout.json
# n=30 pages=5 k=3
# hit@1=0.9 hit@3=1.0
# latency p50=3129.4ms p95=10971.9ms mean=4428.2ms
# labels={'support': 2, 'partial': 5, 'contradict': 0, 'no_evidence': 23} failures=0 no_candidates=0
```

| 指标 | 值 |
| --- | --- |
| n / 页面 | 30 / 5 |
| hit@1 | **0.9000（27/30）** |
| hit@3 | **1.0000（30/30）** |
| 首次命中位次 | 第 1 位 27 条、第 2 位 2 条、第 3 位 1 条 |
| 延迟 | P50 3129.4 ms、P95 10971.9 ms、mean 4428.2 ms（min 30.1、max 14819.2） |
| 四档分布 | support 2 / partial 5 / contradict 0 / **no_evidence 23** |
| 失败 / 无候选 | 0 / 0 |
| 每条候选数 | 均为 5（`MAX_CANDIDATES=5`） |

逐页：

| 页面 | hit@1 | hit@3 | 四档分布 |
| --- | ---: | ---: | --- |
| 2611.07772 | 6/6 | 6/6 | no_evidence 5, partial 1 |
| 2610.38049 | 5/6 | 6/6 | no_evidence 4, partial 2 |
| 2610.24037 | 6/6 | 6/6 | no_evidence 2, partial 2, support 2 |
| 2610.32576 | 4/6 | 6/6 | no_evidence 6 |
| 2610.18926 | 6/6 | 6/6 | no_evidence 6 |
| 合计 | 27/30 | 30/30 | support 2 / partial 5 / no_evidence 23 |

结果文件为 `data/live_eval/live_eval_holdout.json`。注意：该 JSON 的 `dataset` 字段是按数据形状推断的 `"public"`（与 t13 公开页集同一 schema），区分两套数据请看文件名、`data.pages` / `data.claims` 路径，以及本文件的说明。没有为这一差异修改 `scripts/eval_live.py`（t15 只允许写 `data/live_eval/` 与本文件）。

### 5.2 t17 摘要补全后（2026-11-14 03:31，同一 30 句复测）

t17 给 page-reference 候选按 DOI/题名补 OpenAlex/Crossref 摘要（`has_abstract`），并加 URL→参考文献表的进程缓存（TTL 300 s、LRU 32）。同一批冻结数据重跑（未改数据、未调参；包装脚本在临时目录，原因见 §9）：

| 指标 | 值 |
| --- | --- |
| n / 页面 | 30 / 5 |
| hit@1 | **0.9000（27/30）** |
| hit@3 | **1.0000（30/30）** |
| 首次命中位次 | 第 1 位 27 条、第 2 位 2 条、第 3 位 1 条 |
| 延迟 | P50 2982.7 ms、P95 16088.8 ms、mean 5135.7 ms |
| 四档分布 | support 2 / partial 9 / contradict 0 / **no_evidence 19** |
| 有逐字证据的句子 | **11/30**（其中 8 条指向被引来源本身，见 §5.3） |
| 失败 / 无候选 | 0 / 0 |

逐页（同一页面 id，便于与 5.1 对照）：

| 页面 | hit@1 | hit@3 | 有证据 | 四档分布 | 5.1 证据下界 |
| --- | ---: | ---: | ---: | --- | ---: |
| 2611.07772 | 6/6 | 6/6 | 3/6 | no_evidence 3, partial 3 | 1 |
| 2610.38049 | 5/6 | 6/6 | 4/6 | partial 4, no_evidence 2 | 2 |
| 2610.24037 | 6/6 | 6/6 | 4/6 | no_evidence 2, partial 2, support 2 | 4 |
| 2610.32576 | 4/6 | 6/6 | 0/6 | no_evidence 6 | 0 |
| 2610.18926 | 6/6 | 6/6 | 0/6 | no_evidence 6 | 0 |
| 合计 | 27/30 | 30/30 | 11/30 | support 2 / partial 9 / no_evidence 19 | 7 |

与 5.1 的同集对比（**不是**与 t13 比）：

| 指标 | 5.1（t14 后） | 5.2（t17 后） | 变化 |
| --- | ---: | ---: | --- |
| hit@1 | 27/30 | 27/30 | 持平 |
| hit@3 | 30/30 | 30/30 | 持平 |
| 有逐字证据 | 7（由标签推断的下界） | 11（直接计数） | +4 |
| no_evidence | 23/30 | 19/30 | −4 |
| P50 | 3129.4 ms | 2982.7 ms | −146.7 ms（−4.7%） |
| P95 | 10971.9 ms | 16088.8 ms | +5116.9 ms（+46.6%） |
| mean | 4428.2 ms | 5135.7 ms | +707.5 ms |

### 5.3 “OpenAlex 有摘要”的 25 条子集

30 个 gold DOI 中 25 个在 OpenAlex 有 `abstract_inverted_index`（5 个没有；脚本为临时脚本）。该子集单报：

| 指标 | 5.1 同子集 | 5.2 同子集 |
| --- | ---: | ---: |
| n | 25 | 25 |
| hit@1 | 22/25（0.88） | 22/25（0.88） |
| hit@3 | 25/25 | 25/25 |
| 有逐字证据 | 6（标签推断下界） | 9 |
| 四档 | support 2 / partial 4 / no_evidence 19 | support 2 / partial 7 / no_evidence 16 |
| P50 | — | 2735.1 ms |

补充测量（同一 30 句再独立调用一轮，用于核对证据指向）：gold 候选 30/30 都出现在候选里；**gold 候选摘要有内容的 20/30**（OpenAlex 可得的 25 条里仍有 5 条没取到摘要）；11 条证据句中 **8 条的证据 DOI/标题就是被引来源本身**，另 3 条来自同页其它候选。10 条 gold 摘要仍为空：`hld-261107772-02`、`hld-261038049-01`、`hld-261024037-02`、`hld-261032576-01/-02/-03/-05/-06`、`hld-261018926-01/-06`。

## 6. 诊断：命中满分，证据不足

### 6.1 映射确实生效

30 条 gold 中 27 条排在第 1 位、2 条第 2 位、1 条第 3 位；`no_candidates=0`。手工探测 `hld-261107772-01`（`[1]`）与 `hld-261032576-01`（`[8]`）时，`live_check._page_reference_candidates` 分别返回 1 / 4 条页面候选，gold 都在其中，说明 t14 的 `[n]` → 页内参考文献映射在没见过的 2026 年页面上可用。

### 6.2 no_evidence 的主因不是"文献没有摘要"

page-reference 候选在构造时就把摘要设成空串：`_reference_candidate` 的 `Candidate(..., abstract="")`（`src/citeguard/live_check.py:1030`）。而 `check_claim` 只有在**全部**候选都没有摘要时才直接返回 no_evidence（`src/citeguard/live_check.py:1168`）；本集会混入其它带摘要的关键词候选，于是流程进入判定，但 gold 候选没有摘要可引用，最终落为 no_evidence。

单独核对 30 个 gold DOI 的 OpenAlex 记录：**25/30 有 `abstract_inverted_index`**（5 条没有，脚本为临时脚本）。也就是说，问题不是"这些文献没有摘要"，而是"页面候选没有去取摘要"。这给下一步一个明确、可验证的改进点，而不是把 no_evidence 解释成"检索不到"。（t17 已按此补摘要，残差见 6.5。）

### 6.3 延迟：每句重新解析整页 HTML

页面 HTML 有 URL+日期缓存（`_cache_page_path`），但 `_parse_bibliography(html)` 在每次 `check_claim` 里重新跑；参考文献多的页面（本集有 126 条、63 条）单句需要数秒，冷启动首次抓取最长 14.8 s（产品 `PAGE_FETCH_TIMEOUT=5 s`，另有重试/回退）。P50 3.1 s 对"边读边核验"偏慢，建议缓存解析后的参考文献表（不在本任务范围）。

### 6.4 其它观察

- `2610-32576` 有一条 HTML 参考文献既无 DOI 也无可用 anchor，候选退化为页面本身（DOI 为空），占用一个候选位，但不影响 gold 命中。
- 逐页命中都不低于 6/6，说明不是某一页的特例；`2610.32576` / `2610.18926` 的 12 条全部 no_evidence，与这两页被引文献以政策/书籍/临床指南为主、摘要可得性更差一致（探测中 abs_len 均为 0）。

### 6.5 t17 之后的残差：瓶颈从“没摘要”转为“没判定模型”

1. **摘要补全不是全覆盖**：30 条 gold 里 20 条拿到摘要（OpenAlex 可得的 25 条中 5 条仍未取到），10 条仍为空；`2610.32576` 这一页 6 条 gold 全空，因此该页 6 条仍全部 no_evidence。补全依赖 OpenAlex/Crossref 外部 API，失败/限流会静默降级。
2. **没有判定模型时只剩词面规则**：本环境 `support.judge_available()` 为 False，四档由本地规则降级判定；`no_evidence` 的 `reason` 原文是“未配置判定模型；本地规则未在候选摘要中找到与引用句关键词/数字足够重合的句子”。即使 `2610.18926` 的 gold 候选 VoxelMorph 摘要已补上（1573 字符），规则判定仍是 no_evidence——方法类句子与摘要措辞不重合时，规则不会给出证据。
3. **“有证据”不等于“证据支持该句”**：11 条有证据的句子里，8 条的证据指向被引来源本身，3 条来自同页其它候选；本集没有人工 stance 金标，不能把“有引文”当成“判断正确”。
4. **延迟尾部变差**：P50 略降（−4.7%），但 P95 +46.6%、mean +707.5 ms；摘要补全引入的外部调用在冷启动/缓存失效时抬高尾部。TTL 300 s 的进程缓存在一次性 30 句评测里有效，但真实阅读会话需要预热或并发控制。

## 7. 与 t13 公开页集的关系（不混算）

| 维度 | t13 公开页集 | t15 held-out 集 |
| --- | --- | --- |
| 页面 | 2611.02510 / 2610.41688 / 2610.34084 / 2611.09866 / 2611.10770 | 2611.07772 / 2610.38049 / 2610.24037 / 2610.32576 / 2610.18926 |
| 选页准入 | 被引 DOI 在 OpenAlex `referenced_works` 前 40 | 只要求句内有 `[n]`、页内有该条目、DOI 可解析 |
| gold 在旧候选源内 | 30/30（按设计） | 10/30（测量值） |
| 机制 | 页面引用列表排序（t12） | `[n]` → 页内参考文献映射（t14） |
| hit@3 | 18/30（0.6000） | 30/30（1.0000） |
| P50 | 16.7 ms | 3129.4 ms |
| 主要瓶颈 | 词面打分 + top-5 截断 | 页面候选无摘要 → no_evidence；HTML 重解析延迟 |

两套数据的页面、许可、选样规则、候选来源都不同，**18/30 与 30/30 不能相加、平均，也不能表述成"提升 12 条"**。它们回答的是不同问题：t13 问"页面引用列表排序在可控候选里效果如何"，t15 问"`[n]` 映射在未见页面上是否成立"。本文件 5.1 与 5.2 则是**同一套数据的前后两次运行**，可以并列比较（before/after）；t18 不改选样、不调参，只报告 t17 摘要补全带来的变化。

## 8. 决策

| 对象 | 决策 | 理由 |
| --- | --- | --- |
| `[n]` → 页内参考文献映射（t14） | **adopt** | held-out 30/30 hit@3，27/30 第 1 位；没见过的 2026 页面可用 |
| "Live 检索已解决" | **hold** | 19/30 no_evidence；命中来源不等于给出证据与判定 |
| 用本集数字宣称 stance 准确率 | **reject** | 无人工 stance 金标，且 no_evidence 占 19/30 |
| page-reference 候选补摘要（t17） | **adopt** | 同集复测：有证据 7（下界）→ 11，no_evidence 23→19；hit@3 保持 30/30 |
| "有证据句" = "判断正确" | **reject** | 11 条证据中 8 条指向 gold，3 条来自其它候选；无人工 stance 金标 |
| 用本集 P95 承诺交互延迟 | **reject** | P95 16.1 s（冷启动 + 外部 API）；P50 3.0 s 对"边读边核验"仍偏慢 |
| 摘要补全失败时静默降级 | **hold** | 20/30 gold 有摘要、10/30 仍空；需可观测的失败计数/重试，超出本任务范围 |
| 缓存解析后的参考文献表 / 摘要缓存 | 工程建议 | t17 已加 URL→参考文献表缓存（TTL 300 s、LRU 32）；摘要缓存与预热可继续压 P95 |

上述后续实验已由 t18 执行并写入 5.2；仍未验证的是"四档判断是否正确"——这需要人工 stance 标注，不能在无金标的本集上宣称。

## 9. 复现

```powershell
cd D:\ai+ky\citeguard
$env:PYTHONPATH='src'

# 数据完整性
python scripts/eval_live.py --claims data/live_eval/claims_holdout.jsonl --pages data/live_eval/pages_holdout.json --check

# 实测（需网络；结果写入 data/live_eval/live_eval_holdout.json）
python scripts/eval_live.py --claims data/live_eval/claims_holdout.jsonl --pages data/live_eval/pages_holdout.json --out data/live_eval/live_eval_holdout.json
```

```powershell
# t18 复测（t17 后；会额外统计 evidence 非空的条数）
$env:PYTHONPATH='src'; python D:\Temp\citeguard_e3\run_enriched.py
# 结果写入 data/live_eval/live_eval_holdout_enriched.json
```

`scripts/eval_live.py` 的 `run()` 不统计 evidence（它只看 label/候选/延迟），所以 5.2 的 `evidence_available` 由一层包装 checker 计数。因为 t18 只允许写 `data/live_eval/` 与本文件，包装脚本留在临时目录、未入库；其核心逻辑如下（仓库根目录运行）：

```python
import json, sys
sys.path[:0] = ["scripts", "src"]
import eval_live
from citeguard import live_check

claims = eval_live.load_claims("data/live_eval/claims_holdout.jsonl")
pages = eval_live.load_pages("data/live_eval/pages_holdout.json")
id_by_sentence = {c["sentence"]: c["id"] for c in claims}
evidence_ids = []

def checker(sentence, **kw):
    out = live_check.check_claim(sentence, **kw)
    if out.get("evidence"):
        evidence_ids.append(id_by_sentence.get(sentence))
    return out

res = eval_live.run(claims, pages, checker)
res["evidence_available"] = len(set(evidence_ids))
res["evidence_ids"] = sorted(set(evidence_ids))
json.dump(res, open("data/live_eval/live_eval_holdout_enriched.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
```

5.3 的补充测量（gold 候选摘要是否非空、证据是否指向 gold）是另一个临时脚本：对同一 30 句再调用一轮 `check_claim`，按 DOI/标题比对 evidence 与 gold，并与主 run 的标签对照；两轮是独立调用，见 §10 第 9 条。

结果可重复性：同一网络环境下重跑脚本会得到相同候选来源；延迟受网络与缓存状态影响（首次抓取与后续缓存差异明显），不作为固定指标承诺。

## 10. 局限

1. 规模小：5 页 / 30 句，单次运行；不足以估计方差的置信区间。
2. 语言：全部英文正文；不能据此推断中文场景的 Live 表现（中文跨语言集是另一套，见 `docs/live_eval.md`）。
3. 无 stance 金标：四档分布只反映产品行为，不代表判断正确率；t18 的 19 条 no_evidence 也不能当成"错误率"。
4. hit@3 的定义是"候选是否含被引来源的标题/DOI"，不检查证据句是否真的支持该句。
5. 页面为 2026 年 arXiv 预印本，作者可能更新版本；本集记录的是 2026-11-14 的 HTML 状态。
6. 两页为 NC / arXiv 非独占许可，只用于评测，不再分发全文。
7. t14 只映射"页内参考文献里有的 `[n]`"；`[n]` 缺失、编号错位或非 arXiv HTML 页面时仍走旧路径（t13 已记录 0/30 的跨语言问题）。
8. 覆盖测量（10/30）只针对 OpenAlex `referenced_works` 前 40，不代表其它候选源或未来索引状态。
9. 5.2 主 run 与 5.3 补充测量是两次独立调用（网络、摘要补全成功率可能波动）；两轮的有证据条数都是 11，但"20/30 拿到摘要"不是稳定保证。
10. 本环境没有 LLM 判定模型（`judge_available()=False`），四档是本地规则降级结果；`no_evidence` 的 `reason` 已明确写出这一点，不能当作语义 stance 能力。
11. 25 条子集按"OpenAlex 有摘要"选取，不是随机子集，不能外推到整个 held-out 集或其它领域。
12. "OpenAlex 可得 25/30"与"实际补到 20/30"相差 5 条，未逐条归因（可能是 API 失败、题名/DOI 匹配失败或候选截断）；本任务只记录差值，不猜原因。
13. P50/P95 依赖网络与进程缓存状态；t18 的 P95 比 t15 高 46.6%，不能把 5.2 的延迟当稳定性能承诺。

## 11. 文件

| 文件 | 说明 |
| --- | --- |
| `data/live_eval/pages_holdout.json` | 5 页元数据（id/url/title/fetched_at/license/license_url/source/references） |
| `data/live_eval/claims_holdout.jsonl` | 30 句，7 字段，6 句/页 |
| `data/live_eval/live_eval_holdout.json` | t15 基线（5.1；n=30，hit@3=1.0） |
| `data/live_eval/live_eval_holdout_enriched.json` | t18 复测（5.2/5.3；evidence_available=11、gold 摘要补充测量、per-page 与 25 条子集） |
| `scripts/eval_live.py` | 复用 t13 扩展的 `--claims/--pages/--out/--check`，本任务未改 |
| `docs/live_eval.md` | t13 两套数据的说明与对比；本文件不重复其数字 |
