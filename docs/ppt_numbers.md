# 答辩/PPT 数据一页纸

> 用途：答辩 PPT 里可直接引用的**已核实数字**。每条都给了口径、复现命令和证据文件，评委追问时能当场跑。
> 原则：只写真实测得的数；数据集构造的局限性必须一起说（见文末「不能这么说」）。

## 一句话定位

**引证卫士 CiteGuard-CN**：中文论文的引文体检工作台——逐条核验参考文献是否真实存在、是否真的支持正文那句话、是否符合 GB/T 7714-2025 著录格式；本地部署、开源、自带两个中文评测集。

## 核心数字（可直接上 slide）

| # | 指标 | 数值 | 口径 / 数据集 | 证据文件 |
|---|---|---|---|---|
| 1 | 引文真实性分类 macro-F1 | **0.9684** | CiteBench-CN 250 条（构造集） | `data/citebench_cn/results.json` |
| 1b | 同任务 DeepSeek 零样本基线 | 0.5159（acc 0.536） | 同上，prompt 冻结可复现 | `data/citebench_cn/deepseek_results.json` |
| 2 | 引用支持度 macro-F1 | **0.9328**（acc 0.930） | ClaimSupport-CN 100 条（构造集），两段式 judge | `data/claimsupport_cn/results.json` |
| 2b | 单段 judge / prompt v1 对比 | 0.9005 / 0.7951 | 同上，消融记录 | `docs/support_summary.md` |
| 2c | 外部公开基准零样本（英文 SciFact） | **0.8224**（oracle 证据句）/ **0.7939**（整段摘要） | SciFact dev 300 条，未训练/微调，四分类映射三分类 | `data/experiments/scifact_support_results.json` |
| 2d | 本地开源模型离线（Qwen3-1.7B, Apache-2.0） | 20 条试点 **0.7059**（精简 prompt，CPU） | 完全离线可跑通；小模型速度/质量有限，生产建议 Qwen3-8B+GPU | `data/experiments/support_local_qwen3_1.7b_simple.json` |
| 3 | 真实已发表文献被判「疑似虚构」 | **0 / 409** | 20 篇 OA 中文论文的参考文献（真实语料） | `data/experiments/verify_real.json` |
| 3b | 真实文献判定分布（无本地库） | 真实一致 125 / 元数据偏差 87 / 未找到 197 / 疑似虚构 **0** | 同上 | 同上 |
| 3c | 网页型引文（`[EB/OL]`）链接核验 | 23 条真实网页引文中 **13 条链接可达且页面标题一致**（判 Exact）；3 条标题不一致、7 条访问受限 | 真实语料 §3.1，链路检查带 SSRF 防护 | `data/experiments/verify_real.json` |
| 3d | 支持度判定只认可靠匹配 | 扫描件 23 条引文中 **21 条弱匹配（相似度 0.20–0.76）不判定**，避免用错论文摘要编出「无证据」；可靠匹配仍正常判定 | v0.3.6 匹配度护栏；对照 DOI 用例判 `support` | `docs/HANDOFF.md` §14 |
| 4 | 导入本地题录库后的可判定率 | **409 / 409（100%）**，字段偏差 4 条 | 库由 20 篇论文发布版参考文献构建 | `data/experiments/library_real.json` |
| 5 | 参考文献解析干净率 | **100%**（发布版文字 409 条）/ **99.6%**（PDF 抽取 529 条，逐条） | 22 篇真实论文 | `data/experiments/parse_real.json` |
| 5b | 扫描件 OCR 兜底 | 纯图片 PDF 仍能解析 **23/24 条**（题名/年/作者 23/23） | 7 页真实论文扫描版，CPU 约 43 s | `data/experiments/ocr_scan_real.json` |
| 6 | GB/T 7714-2025 类型码识别 | **100 / 100** | E4：100 条真实中文文献回灌 | `data/experiments/e4_format.json` |
| 6b | GB/T 必填字段完整率 | **98.4%** | 同上 | 同上 |
| 6c | 30 条受控格式漂移严格检出 | **29 / 30（96.7%）** | E4，6 类 × 5 条（构造漂移） | 同上 |
| 7 | 中文题名检索召回 | **92%** | OpenAlex 已收录的中文论文 25 篇 | `data/experiments/search_recall.json` |
| 8 | 中国 DOI 平台元数据接入 | CNKI DOI 从「未找到」→ **真实一致**；真实语料可补 1/409 | 真实语料 + 在线接口 | `docs/real_data_eval.md` §5 |
| 9 | 工程与交付 | **299** 测试通过；4 个网页页面 + 报告页；批量/汇总/CSV；Docker/CI | 离线测试，无网络依赖 | `pytest tests -q` |

> 引用时建议写法：**「真实已发表文献 0/409 误判为虚构」**、**「支持度 macro-F1 0.9328（构造集）」**、**「格式漂移检出 29/30」**。
> 这三条分别对应：敢不敢信结论、能不能判断引用是否被支持、格式规则有没有真本事。

## 与竞品/基线的对比（可讲的部分）

| 对比 | 数字 | 说明 |
|---|---|---|
| vs DeepSeek 零样本做引文真实性三分类 | 0.9684 vs 0.5159 | CiteBench-CN；说明「检索 + 规则 + 校验」比纯 LLM 判更可靠 |
| vs 纯标题检索 / 纯 DOI 锚定（消融） | 0.9684 → 0.7744 / 0.8071 | 证明多源编排的必要性 |
| vs 单段 LLM judge | 0.9005 → 0.9328 | 两段式覆盖审计的增益 |
| 外部公开基准 SciFact（英文，zero-shot） | oracle 0.8224 / 摘要 0.7939 | 未训练/微调；判定方法可跨语言迁移 |
| 本地题录库前 vs 后 | 可判定率 49% → 100% | 中文覆盖率的核心解法 |

## 演示动线（3 分钟）

1. 首页拖入示例论文 → 报告：四类结论 + 每题证据链接；
2. 批量上传 2 篇 → 汇总面板（篇数/条数/各状态/格式均分）+ 导出 CSV；
3. 报告页点「支持度矛盾」筛选 → 展示「元数据一致但正文与原文矛盾」条目；
4. 题录库页展示搜索/删除/一键补摘要（只补缺摘要，标题相似度 ≥ 0.92 才接受）；回报告看「本地题录库」标签；
5. 评测页 `/benchmark`：CiteBench / ClaimSupport / 真实语料三块数字一屏看完。

## 复现命令（评委问「这些数字怎么来的」）

```bash
PYTHONPATH=src python -m pytest tests -q                    # 316 passed, 2 skipped
PYTHONPATH=src python scripts/evaluate_citebench.py         # 真实性基准（离线缓存）
DEEPSEEK_API_KEY=... PYTHONPATH=src python scripts/evaluate_support.py   # 支持度（两段式）
PYTHONPATH=src python scripts/eval_parse_real.py            # 真实论文解析实测
PYTHONPATH=src python scripts/eval_verify_real.py           # 真实文献误报实测
PYTHONPATH=src python scripts/eval_library_real.py          # 本地题录库覆盖率实测
PYTHONPATH=src python scripts/e4_format_check.py            # 格式规则回归
PYTHONPATH=src python scripts/verify_artifacts.py           # 数据集/结果/文档数字一致性（63 项；加 --api-base 共 72 项）
```

## 不能这么说（会被当场问穿）

1. **不要说「支持度准确率 93%，适用于任意论文」**：ClaimSupport-CN 是程序化构造集（标签由构造决定，无人工双标、无 κ）；应说「在自建中文支持度评测集上 macro-F1 0.9328」。
2. **不要说「中文文献都能在线核验」**：无本地库时约 48% 只能给「未找到匹配」——这是国际开放元数据覆盖不足，不是造假；本地题录库可把可判定率拉到 100%，但需要用户导入自己的题录。
3. **不要说「覆盖知网/万方全文」**：产品不抓取、不转存授权全文；只消费用户自己导出的题录与公开元数据。
4. **不要说「用户实测/用户满意度」**：目前只有内部实验（E4/E5/E7 是内部实验），没有真人用户研究；用户测试包已备好在 `docs/user_test_kit.md`（3–5 人可跑）。
5. **不要说「格式检查覆盖 GB/T 全部规则」**：E4 是构造漂移回归（29/30），规则引擎仍是有边界的；页码连接号只是 warning，卷/期为小数字时无法判断互换。
6. **「0/409 误判」的前提是这 409 条来自已发表论文**；换成论文写作中的草稿/伪造引文，系统会通过 Major 正常报出来（CiteBench 里 75 条构造虚构全部检出）。
