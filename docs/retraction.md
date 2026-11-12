# 撤稿与勘误检查

报告里每条「真实一致 / 元数据偏差」的文献，如果带有 DOI，会额外查一次撤稿与勘误状态。

## 数据来源

| 状态 | 来源 | 判据 |
| --- | --- | --- |
| `retracted`（已撤稿） | OpenAlex `works/doi:{doi}` | `is_retracted == true` |
| `corrected`（有勘误/更新） | Crossref `works/{doi}` | `relation.updated-by` 或 `relation.update-to` 非空 |
| `clean`（未发现异常） | OpenAlex | 未标记撤稿 |
| `error`（未完成） | 任一来源 | 网络失败、限流或 DOI 不存在 |

只检查核验状态为 **Exact / Minor** 且有 DOI 的条目：DOI 本身匹配错时，撤稿标记会指向另一篇论文，不能作为结论。最多检查 40 条，4 路并发。

## 报告里怎么呈现

- 总览顶部红色横幅：`撤稿与勘误检查：N 条已撤稿、M 条有勘误/更新（OpenAlex + Crossref）`，并提示打开原文核对撤稿声明或勘误页。
- 条目卡片：已撤稿显示「该文献已撤稿」，Crossref 有更新关系显示「有勘误/更新」。
- 报告 JSON：`references[i].retraction = {status, source, title, detail, doi}`，顶层 `retractions = {checked, retracted, corrected, clean, error}`。

## 评测结果

| 测试 | 样本 | 结果 | 证据 |
| --- | --- | --- | --- |
| 撤稿召回 | OpenAlex `is_retracted:true` 100 条 | **100/100** 检出（100%） | `data/experiments/retraction_eval.json` |
| 对照误报 | OpenAlex 未撤稿 100 条 | **0/100** 误报 | 同上 |
| DOI 互换 | 题名 A + DOI B 构造 99 条 | **0 条 Exact**，98 条明确提示“DOI 指向另一篇” | `data/experiments/doi_swap_eval.json` |

边界：撤稿样本的标签也来自 OpenAlex，这是“与数据源标记一致”，不是独立人工真值；DOI 互换是构造测试（题名取 A、DOI 取 B），只说明错误 DOI 不会被判成完全一致。

## 边界（如实说明）

- 这不是全文比对，只查 OpenAlex / Crossref 的结构化标记；撤稿声明未同步到这两个索引时查不到。
- `clean` 只表示「这两个来源没有标记」，不是「论文一定没问题」。
- 中文期刊 DOI 在 OpenAlex/Crossref 覆盖有限，`error` 或无 DOI 的条目不会被检查。
- 已撤稿文献仍可能被准确引用；横幅提示的是「引用前需要知道」，不是「引用错误」。

## 验证

- 真实撤稿样本：`10.1016/S0140-6736(20)30367-6`（Lancet 2020 痴呆预防委员会报告）→ `retracted`；
- 对照样本：`10.1038/nature14539`（LeCun et al., Deep learning）→ `clean`；
- 端到端报告 `4f00472bc471`：2 条文献，1 条撤稿 + 1 条 clean，红色横幅正常显示。
- 截图：`docs/evidence/shots/phase-F3-retraction-v1.1.4.png`（E59）。
