# 原子断言 × 全文证据核验（通用方法）

这是 CiteMap 从“论文级一句话”转向“断言级逐句证据”的第一步，也是
105 格人工核对后唯一诚实的修正方向。

## 方法

1. **断言先原子化**：8 条复合断言拆成 21 条原子断言
   （`data/evidence_map/claims_atomic.json`，人工尚未逐条确认）。
2. **只使用可获取的全文**：30 篇固定论文中，有 25 篇可通过 OpenAlex OA 链接、Europe PMC
   `fullTextXML`、arXiv 预印本或 PMC HTML 取得全文（其余出版社 403/跳转失败）。全文只缓存文本，PDF/XML 解析后即删除。
3. **通用句子检索**：中文断言遇到英文全文时，用一次模型翻译生成 6–12 个英文
   检索词（含同义词与评价词，例如临床的 radiologist/clinician、教育的
   well-being），再用词面重合排序候选句；不写领域关键词表，不按领域分支。
4. **逐句判断**：判官对每条“断言 × 候选句”输出
   `full / partial / none`，并必须逐字引用原文；引用不命中候选句就
   直接丢弃/降级。
5. **不猜**：没有全文、没有候选句、判官失败，都返回 `none/error`；
   不把主题相关句包装成证据。

翻译只用检索：判官始终看原文断言和候选英文句，翻译不会成为证据。

## 结果（2026-11-15，Europe PMC + arXiv/PMC 补充后）

- 覆盖：21 条原子断言 × **25 篇全文** = **258 个“断言 × 论文”组合**。
- 判定：**完整支持 10、部分支持 15、无证据 233、错误 0**。
- 完整支持覆盖率 **3.9%**；任何支持（full+partial）覆盖率 **9.7%**。
- 105 格人工结果中，**7 个“人工判正确且所在论文有本地全文”的证据格**：
  **完整支持命中 5/7（71.4%）**，**支持证据命中（full+partial）6/7（85.7%）**。
- 10 条 full 判定中有 7 条落在人工正例格内，对应 **5/7 个人工正例格**；
  不能把多条原子断言当成独立人工样本，也不能把“单元格被人工判对”
  等同于每个原子级 full 都被人工确认。
- 唯一完全漏掉的是 edu-002/edu-c1：原文研究 AI literacy、SRL 与
  writing performance/well-being，没有“接受度/自评收益”的对应句；
  这是“论文没研究该断言”，不是检索失败，未强行补一条。
- 分主题：AI 教育 132 组合（6 full / 8 partial / 118 none）；
  医学影像 126 组合（4 full / 7 partial / 115 none）。

## 检索增强做了什么

- 候选句从 top-6 扩到 top-12，避免结论句被介绍句挤出。
- 翻译提示词从 3–8 个直译词改为 6–12 个“直译 + 同义词 + 评价词”，
  并明确只用于检索、不得当证据。
- 判官规则明确：断言是“达到/接近/不低于专家水平”时，原文说明模型与
  医生在同一任务上 accuracy/AUC 相当、更高或非劣，或给出模型不低于医生的
  数值，都应判 `full`，即使原文用 surpassed/outperformed。
- 这些改动只放宽“同一语义的表述”，没有放宽“必须逐字引用原文”。

## 怎么读

- **高精度、中覆盖**：人工正例的支持证据召回 6/7、完整支持 5/7；
  但 258 组合里绝大多数是 `none`——论文本来就没有研究该断言，不是隐藏失败。
- **不能外推**：25/30 全文、7 个人工正例，样本很小；这不是“通用 CiteMap
  已达 85%”。
- **与旧路线对比**：旧 v1 在 31 条人工核对证据里精确率 25.8%；
  全文逐句 + 逐字引用把人工正例的完整支持从 2/7 提到 5/7，代价是整体覆盖率仍低。

## 复现

```bash
# 1) 抓取可获取的 OA 全文（会缓存到 data/cache/citemap_fulltext/）
python scripts/fetch_citemap_fulltext.py

# 2) 跑 21 条原子断言逐句核验（需配置判官）
python scripts/eval_citemap_atomic_fulltext.py --top 12 --workers 6 \
  --out data/experiments/citemap_atomic_fulltext_v3.json

# 3) 与 105 格人工结果交叉汇总
python scripts/summarize_citemap_atomic_fulltext.py

# 4) 重新生成第 16 张证据图
python scripts/make_fulltext_chart.py
```

输出：

- `data/experiments/citemap_atomic_fulltext_v3.json`（逐组合判定与引用）
- `data/experiments/citemap_atomic_fulltext_v3_summary.json`（汇总与人工正例交叉）
- `docs/evidence/shots/final/charts/16-fulltext-atomic.png`

## 边界（必须一起说）

- 全文覆盖 25/30 篇；其余闭源/被出版社拦截的论文无法自动获取，产品对用户上传
  PDF 走同一流程。
- 21 条原子断言是规则拆分的，尚未逐条人工确认；`full` 不等于人工金标。
- 判官是单个模型；没有多模型投票/人工仲裁。
- 引用逐字校验只防“编句子”，不防“句子真实但推断错误”；后者需要更细的
  NLI/人工核对。
- 方法不是针对教育/医学调参：同一套切句、检索、判定、拒答逻辑用于两个主题；
  领域词表没有进入代码。
