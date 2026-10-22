# CiteBench-CN 数据卡

**CiteBench-CN** 是 CITEGUARD-CN 项目自建的**中文参考文献核验评测集**：以 OpenAlex 中真实收录的中文文献元数据为底，按 GB/T 7714 风格渲染成参考文献串，再用**程序化受控扰动**构造 250 条带标签的样本，用于评测「Exact / Minor / Major」三分类核验器。标签完全由构造过程决定，不来自任何模型标注。

## 1. 概览

| 项 | 值 |
|---|---|
| 数据集 | CiteBench-CN |
| 版本 | v3（2026-10-22） |
| 规模 | 250 条（Exact 100 / Minor 75 / Major 75） |
| 文件格式 | JSONL，UTF-8，每行一条 |
| JSONL SHA-256 | `1a8e466b952cd1fef9fc2f897d18053eed7f91596c9d9d91d63fed2f961891d7` |
| 随机种子 | `20261022`（重建 SHA 一致，可复现） |
| 上游数据 | OpenAlex `https://api.openalex.org/works`，`filter=language:zh,has_doi:true`（CC0 1.0） |
| 许可证 | 本数据卡与数据集 **CC-BY-4.0**；上游元数据 CC0 1.0；**不含论文全文/摘要的再分发** |
| 评测基线 | CiteGuard-CN v1.1（规则+多源）、DeepSeek `deepseek-chat` zero-shot（prompt v3） |

## 2. 标签口径

| 标签 | 定义 | 数量 | 构成 |
|---|---|---|---|
| `Exact` | 题名、年份、作者、来源、卷期、页码、DOI 全部与真实文献记录一致 | 100 | 70 条带 DOI + 30 条无 DOI |
| `Minor` | 论文**真实存在**，但上述任一字段漂移（年份 / 作者顺序 / 来源 / 卷-期 / 页码） | 75 | 年份 15、作者顺序 15、来源 15、卷-期 15（卷 7 / 期 8）、页码 15 |
| `Major` | 题名在开放库中**找不到**，或 DOI **不存在（404）** | 75 | 虚构题名 38、不存在 DOI 37 |

**30% 的样本（75 条）不带 DOI 字段**（题名+作者+年份+来源等元数据仍在）：Exact 30 / Minor 22 / Major 23。这样 `- title search` 消融才有真实对照（无 DOI 样本只能靠题名检索）。

**关于 DOI 大小写/后缀扰动（已移除）**：
- DOI 大小写不敏感，改大小写后仍解析到同一文献，语义上就是 `Exact`，不应标 `Minor`；
- 改 DOI 后缀会导致 DOI 404，按本口径应归 `Major`，不能作为 `Minor`；
- 因此本版本 Minor 不再包含任何 DOI 漂移，避免标签与 v1.1 判定口径互相矛盾。
- `Major` 的不存在 DOI 统一使用未注册前缀 `10.9999/…`，并在构建时逐条调用 `https://doi.org/api/handles/{doi}` 验证 **全部 404**（37/37）。

## 3. 构造方法

1. **抓取**：分页调用 OpenAlex `works` 接口（参数见上，`select=id,doi,title,publication_year,authorships,primary_location,biblio,type,language`，带 `mailto`），共取 16 页 / 3200 条中文作品，原始响应缓存在 `openalex_zh_works.json`。
2. **筛选合格 base（344 条）**：标题以中文开头且含 CJK、`type=article`、有 DOI、≥2 位作者、来源名含中文且非 DOAJ/PubMed 等索引聚合器、年份/卷/期/首页/末页齐全且数值合理、名称中无逗号/句点等会干扰解析的字符。
3. **GB/T 7714 风格渲染**（作者≤3，超过 3 位加「等」）：
   ```
   作者1, 作者2, 作者3, 等. 题名[J]. 来源, 年, 卷(期): 首页-末页. DOI: 10.xxxx/yyyy.
   ```
   无 DOI 样本省略末尾 `DOI: …` 段。
4. **标签由构造决定**：
   - `Exact`：直接渲染真实记录，不改任何字段；
   - `Minor`：只改一个字段（年份偏移 / 作者顺序 / 来源换成合成的非存在期刊名 / 卷或期 ±1 / 页码偏移）；
   - `Major`：把题名换成合成题名（与所有真实题名相似度 < 0.78），或把 DOI 换成无关的 `10.9999/…`。
5. **自检**：每条渲染串都用 `citeguard.reference_parser.parse_reference` 回解析，逐字段与渲染值比对；不一致则拒用该 base 并换下一条（最终 0 条被拒）。
6. **确定性**：固定 seed + 原始抓取/DOI 校验缓存 + 统一 **LF 换行** + 纯 Python 相似度过滤（不依赖 rapidfuzz 版本），本地（Python 3.12 / Windows）与服务器（Python 3.10 / Linux）重复构建的 `citebench_cn.jsonl` **字节级一致**（SHA-256 相同）。

## 4. JSONL 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | `cbcn-0001` … `cbcn-0250`（打乱后编号，不泄漏标签） |
| `ref_string` | string | 待核验的 GB/T 7714 风格参考文献串 |
| `label` | string | `Exact` / `Minor` / `Major` |
| `corruption` | string | 构造标记，如 `minor:year 2019->2017`、`major:fake_title`；无 DOI 样本追加 ` (no DOI)`；Exact 为 `none` |
| `gold` | object | 该样本所用**真实 OpenAlex 记录**的元数据：`title/doi/year/authors/venue/volume/issue/pages`；虚构/扰动值见 `corruption` |
| `source` | string | 溯源，如 `openalex:W2606729363` |

示例（Exact，节选自真实记录）：

```json
{"id": "cbcn-0002", "ref_string": "吴诗昊, Shihao Wu, 廖志星, 等. 几种常用病毒载体在猕猴脑内的表达效率的比较[J]. 动物学研究, 2017, 38(2): 88-95. DOI: 10.24272/j.issn.2095-8137.2017.015.", "label": "Exact", "corruption": "none", "gold": {"title": "几种常用病毒载体在猕猴脑内的表达效率的比较", "doi": "10.24272/j.issn.2095-8137.2017.015", "year": 2017, "authors": ["吴诗昊", "Shihao Wu", "廖志星", "…"], "venue": "动物学研究", "volume": "38", "issue": "2", "pages": "88-95"}, "source": "openalex:W2606729363"}
```

示例（Major：真实题名 + 不存在的 DOI；`gold.authors` 从略）：

```json
{"id": "cbcn-0009", "ref_string": "西南医科大学, 江 罗, 艺萌 杨, 等. 基于数据挖掘分析产后抑郁的中医用药规律[J]. 中医与中药材研究, 2022, 2(1): 7-13. DOI: 10.9999/cbcn.2016.62380.", "label": "Major", "corruption": "major:fake_doi", "gold": {"title": "基于数据挖掘分析产后抑郁的中医用药规律", "doi": "10.55375/jttcmmmr.2022.2.2", "year": 2022, "venue": "中医与中药材研究", "volume": "2", "issue": "1", "pages": "7-13"}, "source": "openalex:W4309102008"}
```

## 5. 评测指标（v1.1，`results.json`）

数据集 SHA-256 `1a8e466b…`，评测运行时间 2026-10-22（本地与服务器实跑结果一致）。

| 系统 | macro-F1 | accuracy |
|---|---|---|
| **ours (rule+multi-source, v1.1)** | **0.9684** | **0.968** |
| DeepSeek (deepseek-chat, zero-shot) | 0.5159 | 0.536 |

Per-class（ours）：

| 类别 | Precision | Recall | F1 | 支持数 | 预测数 |
|---|---|---|---|---|---|
| Exact | 0.9259 | 1.0000 | 0.9615 | 100 | 108 |
| Minor | 1.0000 | 0.8933 | 0.9437 | 75 | 67 |
| Major | 1.0000 | 1.0000 | 1.0000 | 75 | 75 |

混淆矩阵（行=真实标签，列=预测标签，顺序 Exact/Minor/Major）：

```text
[[100,  0,  0],
 [  8, 67,  0],
 [  0,  0, 75]]
```

消融：

| 配置 | macro-F1 | Δ |
|---|---|---|
| full（DOI 锚点 + 题名检索 + 字段比对） | 0.9684 | 0 |
| - DOI anchor（移除 DOI，仅题名检索） | 0.8071 | -0.1613 |
| - title search（禁用题名检索，仅 DOI 解析） | 0.7744 | -0.1940 |

DeepSeek 基线固定 prompt（v3，`prompt_sha256=e2637ac0442af992d2d6732da8f26e5059e668b731b4c68299021cd44d3850cd`），zero-shot、无检索、temperature 0，250/250 成功；per-class F1 = Exact 0.400 / Minor 0.462 / Major 0.686。

## 6. 复现命令

```bash
# 1) 构建数据集（seed=20261022；重复执行 SHA 一致）
PYTHONPATH=src python3 scripts/build_citebench.py

# 2) v1.1 评测，更新 results.json + eval_predictions.csv
PYTHONPATH=src python3 scripts/evaluate_citebench.py          # 可加 --limit N / --cache DIR / --workers N

# 3) DeepSeek 基线（key 只走环境变量，不落盘），更新 deepseek_results.json 并合并进 results.json
DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/deepseek_baseline.py
```

服务器（依赖在 `.pylibs`）：

```bash
cd /data/xyjiang/aic_mental/citeguard
PYTHONPATH=.pylibs:. python3 scripts/evaluate_citebench.py
```

说明：`build_citebench.py` 使用 `openalex_zh_works.json` 与 `doi_handle_checks.json` 缓存，离线可重跑；`evaluate_citebench.py` 使用 `cache/` 响应缓存（可用 `--cache` 指定目录）；评测结果可通过 `/api/benchmark` 与 `/benchmark` 页面读取。

## 7. 文件清单（`data/citebench_cn/`）

| 文件 | 说明 |
|---|---|
| `citebench_cn.jsonl` | 250 条评测集（主交付物） |
| `citebench_cn.meta.json` | 构造元数据：seed、SHA 相关统计、标签口径、池统计、虚构 DOI 校验记录 |
| `results.json` | 评测结果（`/benchmark` 页面与 `/api/benchmark` 读取） |
| `deepseek_results.json` | DeepSeek 基线：指标、per-class、prompt 版本/哈希、逐条预测 |
| `eval_predictions.csv` | v1.1 逐条预测（含 status、title_sim、year/author match、notes） |
| `openalex_zh_works.json` | OpenAlex 原始候选池缓存（3200 条，CC0） |
| `doi_handle_checks.json` | DOI 存在性校验缓存（doi.org handle API） |
| `cache/` | 核验器 HTTP 响应缓存（OpenAlex/Crossref） |
| `README.md` | 本数据卡 |

## 8. 已知局限

1. **作者字段噪声**：OpenAlex 中文记录的 authorships 常把中文名与拼音名当作两条作者（如「吴诗昊」「Shihao Wu」并列），也存在机构作者（如「西南医科大学」）混入；作者顺序扰动的可检出率因此受限。
2. **来源名变体**：期刊名在 OpenAlex/Crossref 中存在中英文名、缩写、副标题差异；来源字段的漂移检测不代表覆盖所有真实世界的刊名变体。
3. **中文全文/摘要覆盖**：本集只用公开**元数据**，不判断引用上下文支持度（citation support），也不评估「引文是否支持论点」。
4. **样本选择偏差**：只保留 OpenAlex 可检索、有 DOI、字段齐全的中文期刊论文，偏向较规范出版的中文期刊；对无 DOI、图书、学位论文、标准等类型不覆盖。
5. **无 DOI 子集**依赖题名检索召回，受 OpenAlex/Crossref 中文索引质量限制（30% 样本）。
6. **规模**：250 条适合快速回归与演示，不足以覆盖全部学科/年代；建议作为工程回归集，而非领域结论性基准。
7. **DeepSeek 基线无检索**：其分数反映模型内在知识，不代表检索增强后的能力。

## 9. 许可证与引用

- 本数据卡与 CiteBench-CN 数据集以 **CC-BY-4.0** 发布。
- 上游基础元数据来自 **OpenAlex（CC0 1.0）**；参考文献串为程序化渲染结果。
- 不包含、也不再分发论文全文或摘要。
- 如使用请引用：`CiteBench-CN (v3), CiteGuard-CN project, 2026`，并保留本数据卡中的构造与许可证说明。

## 10. 版本变更

- **v3**（当前）：`Major` 只保留「虚构题名 / 不存在 DOI」；「真实题名 + 不存在期刊」归入 `Minor`（来源漂移）；移除 DOI 大小写/后缀扰动；30% 样本无 DOI；Minor 拆分为卷-期与页码两类。
- v2：引入 v1.1 标签口径与无 DOI 子集。
- v1：初版（100/75/75，全部带 DOI）。
