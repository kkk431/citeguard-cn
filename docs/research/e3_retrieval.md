# E3 检索基线：T2Retrieval BM25 与替换候选复核

> 结论：T2Retrieval 可以当**检索管线 smoke test**，但不能当 CiteMap / 替换候选的效果证据。200 条抽样查询、全量 118,605 段落上，BM25 R@3 = **0.79**（随机期望 0.000128），说明中文检索数据本身有信号；但段落是 web QA，不是学术引用上下文。替换候选 438 查询 / 477 候选上，title 与 BM25 **完全复现**历史结果，BGE-M3 的 R@3 比 BM25 高 **+0.0639**（> kill 阈值 +0.02），现有语义检索路线未被 kill；但本次没有新重排器可测，BGE 服务未开、数字沿用 2026-11-13 记录值。决策：T2Retrieval **hold**（仅 harness 用途），替换路径维持 BGE-M3（**adopt**），不新增重排器。日期 2026-11-14。

## 1. 结论与决策

| 对象 | 结论 | 理由 |
| --- | --- | --- |
| T2Retrieval（中文段落检索） | **hold**：可 adopt 为 harness smoke test，hold 作为 CiteMap 证据 | BM25 R@3 0.79 远高于随机 0.000128，许可 Apache-2.0、157 MB、41 秒可复现；但语料是 web QA 段落，非学术引用上下文；本次未跑语义模型；且这是 MTEB 转换版 dev split（118,605 段），不是 T2Ranking 原始全库，数字不能与全库榜单比较 |
| 替换候选（438 查询 / 477 候选，in-domain） | **adopt**：维持现有 BGE-M3 语义检索；**hold**：不新增重排器 | BGE R@3 0.3219 vs BM25 0.2580，增益 +0.0639 > kill 阈值 +0.02；但 BGE 数字为历史记录值、本次未复跑，也没有新方法可测 |
| reject | 无 | 两条数据都干净可用；拒绝的只是“把 T2Retrieval 数字当引用检索效果”这个用法 |

一句话给 CiteMap：**top-3 替换候选约 1/3 命中（BGE R@3 0.3219），页面不能承诺“必命中”，应展示候选 + 证据 + 不确定性。**

## 2. 数据

### 2.1 T2Retrieval（中文段落检索）

| 项 | 值 |
| --- | --- |
| 名称 | mtEB `T2Retrieval`（T2Ranking 的 MTEB 转换版） |
| 许可 | **Apache-2.0**（HF dataset card `cardData.license=apache-2.0`，含 `language=cmn`、`annotations_creators=human-annotated`；2026-11-14 通过镜像 API 读取）。链接：[HF 数据卡](https://huggingface.co/datasets/mteb/T2Retrieval) / [MTEB 任务页](https://leaderboard.mteb.org/tasks/T2Retrieval) |
| 原始论文 / 仓库 | [T2Ranking (SIGIR 2023)](https://arxiv.org/abs/2304.03679) / [THUIR/T2Ranking](https://github.com/THUIR/T2Ranking)（原始仓库无 LICENSE 文件，独立条款**待核实**；本实验以 MTEB 数据卡的 Apache-2.0 为准） |
| 本次实际数据 | corpus 118,605 段（156,879,982 B）· queries 22,812 条（817,540 B）· qrels 118,932 对（1,149,414 B），dev split，全中文 |
| 抽样 | 200 条 query（固定种子 42，从 22,812 条有 qrels 的 query 中无放回均匀抽样），共 1,014 个 gold 对；**corpus 未抽样**（全量 118,605 段参与打分） |
| 可得性 | 公开；本网络 `huggingface.co` 超时，改用 `hf-mirror.com` 下载（同一份 parquet，未被改写） |
| 不分发 | 只落盘 query id / doc id / 聚合指标，不 re-host 段落全文 |

注意：论文口径的 T2Ranking 是 30 万级 query、200 万级段落；本次拿到的是 MTEB 转换版 dev split（118,605 段/22,812 query），**不是原始全库**，因此本页数字不可与 T2Ranking 全库榜单或“中文语义检索上限”直接比较。

### 2.2 替换候选评测集（in-domain）

| 项 | 值 |
| --- | --- |
| 名称 | CiteGuard-CN replacement eval：引用上下文 → 被引参考文献 |
| 规模 | 21 篇论文、438 条 query、477 个去重候选（22 篇 OA PDF 的参考文献） |
| 来源文件 | `data/experiments/replacement_eval_dataset.json`（由 `scripts/build_replacement_eval.py` 生成） |
| 构造 | 每条可解析引文一条 query；ground truth = 作者实际引用的那条参考文献；候选池 = 22 篇语料的参考文献（互相做干扰项） |
| 许可/边界 | 22 篇 PDF 为逐刊 OA，仅本地评测、不再分发；见 `docs/licenses.md`。指标只衡量“上下文 → 被引文献”的检索，不衡量“被引文献是否支持论点” |

## 3. 方法

### 3.1 T2Retrieval BM25

- 分词与产品 `scripts/eval_replacement.py` 的 `tokens()` **完全一致**：英文/数字 ≥2 字符 token + 中文按“字符二元组（bigram）”，不做词级切分（因此无 jieba/rank_bm25 依赖）。
- Okapi BM25：`k1=1.5`、`b=0.75`；`idf = ln(1 + (N - df + 0.5)/(df + 0.5))`。
- 倒排索引只保留 200 条 query 出现过的 term（约数千个），对每条 query 仍对**全库 118,605 段**打分；不截断候选。
- 指标：Recall@1/@3/@5、MRR；另给“随机排序”的解析期望作参照（hit@k 精确期望 `1 - C(N-g,k)/C(N,k)`，MRR 用几何近似 `-p·ln p/(1-p)`，p=g/N）。
- 运行：Python 3.13.14 / numpy 2.3.4 / pandas 3.0.0 / pyarrow 26.0.0，单次 **40.7 秒**（CPU，无 GPU）。

### 3.2 替换候选复核

- 直接复用仓库脚本：`PYTHONPATH=src python scripts/eval_replacement.py --methods title,bm25`，输出到临时文件后与 `data/experiments/replacement_eval.json` 逐项比对。
- title：query token 与候选 title token 的重合率排序；BM25：对 title+venue+year 建索引，k1=1.5/b=0.75（与产品脚本一致）。
- BGE：`CITEGUARD_EMBED_ENDPOINT` 未配置（BGE 服务未开），**本次不跑**，沿用 `data/experiments/replacement_eval.json` 中 2026-11-13 的记录值，并在 JSON 里标记 `rerun: false`。

## 4. 指标

### 4.1 T2Retrieval（n = 200 查询 / 118,605 段落）

| 方法 | R@1 | R@3 | R@5 | MRR |
| --- | --- | --- | --- | --- |
| BM25（自实现，char bigram） | **0.7300** | **0.7900** | **0.8400** | **0.7715** |
| 随机期望（解析） | 0.000043 | 0.000128 | 0.000214 | 0.000419 |

解读：BM25 在这份 dev split 上有强词汇信号，数据本身可用；但它只证明“检索管线能跑通、指标能算”，不证明 CiteMap 的引用检索效果。BM25 绝对值偏高也与“MTEB 转换版只含 118,605 段、查询短（平均 10.9 字）”有关。

### 4.2 替换候选（n = 438 查询 / 477 候选）

| 方法 | R@1 | R@3 | R@5 | MRR | 来源 |
| --- | --- | --- | --- | --- | --- |
| title overlap | 0.1712 | 0.2329 | 0.2763 | 0.2245 | 本次复现（与记录值逐位一致） |
| BM25 | 0.1872 | 0.2580 | 0.2900 | 0.2428 | 本次复现（与记录值逐位一致） |
| BGE-M3（语义） | 0.1986 | 0.3219 | 0.3973 | 0.2948 | 2026-11-13 记录值，本次未复跑 |

差值：

| 对比 | ΔR@1 | ΔR@3 | ΔR@5 | ΔMRR |
| --- | --- | --- | --- | --- |
| BGE − BM25 | +0.0114 | **+0.0639** | +0.1073 | +0.0520 |
| BGE − title | +0.0274 | +0.0890 | +0.1210 | +0.0703 |
| BM25 − title | +0.0160 | +0.0251 | +0.0137 | +0.0183 |

## 5. kill 条件判定

E3 的 kill 阈值：检索/重排相对现有 BGE-M3 的 R@3 增益 **< +0.02** 即不换。

| 检查 | 结果 |
| --- | --- |
| BGE-M3 相对 BM25 的 R@3 增益 | +0.0639 > +0.02 → **kill 未触发** |
| 是否有新检索器/重排器被测 | 否（本次只测 title/BM25 基线；BGE 服务未开） |
| 结论 | 不换检索器：维持 BGE-M3；本次没有可 adopt 的新组件 |

补充：feature_radar 里给 T2Retrieval 子集写的 “R@3 < 0.60” 阈值是按 5,000 段落小池子校准的；本次直接用了全量 118,605 段，条件更严，R@3 = 0.79 仍高于该阈值，所以“数据可用”成立，但**不改变 hold 的结论**（域不匹配 + 未跑语义模型）。

## 6. 产物

| 文件 | 内容 |
| --- | --- |
| `docs/research/experiments/e3_t2retrieval.py` | T2Retrieval BM25 评测脚本（调研脚本，非产品代码） |
| `docs/research/experiments/e3_t2retrieval.json` | n / 抽样 query id / 方法 / 指标 / 随机期望 / 200 条 per-query rank / 许可 / 决策；只含 id，无全文 |
| `docs/research/experiments/e3_replacement.json` | n=438 / 477 / 21；title、BM25（本次复现）、BGE（记录值）；三组差值；kill 判定；决策 |

## 7. 复现命令

```powershell
# 1) 下载 T2Retrieval（约 158 MB；huggingface.co 在本网络超时，用镜像）
$dir = "$env:TEMP\citeguard_e3"; New-Item -ItemType Directory -Force $dir | Out-Null
curl.exe -L -A "Mozilla/5.0" -o "$dir\corpus.parquet"  "https://hf-mirror.com/datasets/mteb/T2Retrieval/resolve/main/corpus/dev-00000-of-00001.parquet"
curl.exe -L -A "Mozilla/5.0" -o "$dir\queries.parquet" "https://hf-mirror.com/datasets/mteb/T2Retrieval/resolve/main/queries/dev-00000-of-00001.parquet"
curl.exe -L -A "Mozilla/5.0" -o "$dir\qrels.parquet"   "https://hf-mirror.com/datasets/mteb/T2Retrieval/resolve/main/data/dev-00000-of-00001.parquet"

# 2) T2Retrieval BM25 基线（约 41 秒）
python docs/research/experiments/e3_t2retrieval.py `
  --corpus "$dir\corpus.parquet" --queries "$dir\queries.parquet" `
  --qrels "$dir\qrels.parquet" --out docs/research/experiments/e3_t2retrieval.json

# 3) 替换候选 title / BM25 复现
$env:PYTHONPATH = "src"
python scripts/eval_replacement.py --methods title,bm25 --out "$dir\replacement_repro.json"
```

`e3_t2retrieval.py` 的 `--n-queries`/`--seed` 默认 200/42；`e3_replacement.json` 中的决策字段是在测量完成后人工写入的，指标字段全部来自上述命令输出。

## 8. 边界（不冒充）

- **不是中文语义检索上限**：只跑了 BM25 词法基线；T2Retrieval 上的语义模型分数未测。
- **不是 CiteMap 的效果证据**：T2Retrieval 是 web QA 段落，CiteMap 是学术论文 claim/evidence；域不匹配。
- **样本量已标注**：T2Retrieval 200/22,812 条 query、全量 118,605 段；替换候选 438/477。
- **不是全库榜单**：MTEB 转换版 dev split ≠ T2Ranking 原始 2M+ 段全库；数字不可与论文/榜单直接比较。
- **BGE 未复跑**：R@3 0.3219 为 2026-11-13 记录值，本次仅复现 title/BM25（逐位一致），BGE 复跑需 `CITEGUARD_EMBED_ENDPOINT`。
- **数据合规**：T2Retrieval Apache-2.0；替换语料为逐刊 OA、仅本地评测不再分发；实验 JSON 只存 id，不 re-host 全文。

## 9. 与 feature_radar E3 设计的差异

| 设计 | 实际 | 原因 |
| --- | --- | --- |
| T2Retrieval 固定子集 200 查询 / 5,000 段落 | 200 查询 / **118,605 段落全量** | corpus parquet 仅 157 MB，全量更省事也更严格；无需按 qid 哈希抽段落 |
| BGE-M3 重排 + 增益判定 | 只复核 title/BM25，BGE 用记录值 | `CITEGUARD_EMBED_ENDPOINT` 未配置，BGE 服务未开 |
| T2Retrieval 子集 R@3 < 0.60 触发 kill | 全量下 R@3 = 0.79，不触发 | 阈值原为 5k 小池校准；全量条件更严仍过线，说明数据可用性没问题，但域不匹配仍 hold |
