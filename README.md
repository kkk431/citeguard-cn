# 引证卫士 CiteGuard-CN

> 给中文论文做一次「引文体检」：**引文是否真实存在、引用是否支持正文那句话、格式是否符合 GB/T 7714-2025**。每条结论都带证据链接。

CiteGuard-CN 是一个开源的中文引文核验工作台，面向毕业论文、课程论文与期刊投稿场景。它把「中文引文解析 → 多源元数据核验 → 引用支持度判定 → 新国标规则检查」串成一条可复现的流水线，并附带一个 250 条的中文评测基准 **CiteBench-CN**。

支持的输入：**PDF**（文字层优先；扫描件可自动 OCR）、**Word（.docx）**（含放在表格里的参考文献表）、**纯文本 / Markdown**。旧版 `.doc` 请先另存为 `.docx` 或 PDF。每份报告都会记录文字来源（PDF 文字层 / OCR / Word / 文本），OCR 生成的报告会显著提示复核。

扫描件 OCR 是可选依赖（不装也能用，只是遇到扫描件会提示）：

```bash
pip install -r requirements-ocr.txt   # rapidocr-onnxruntime + pypdfium2，CPU 即可
```

> 实测（7 页纯图片 PDF，150 dpi）：OCR 后仍能解析出 **23/24 条**参考文献，题名/年份覆盖 23/23、作者 23/23；7 页约 43 s（CPU，含模型加载）。扫描版 PDF 的 OCR 噪声（`[J]`→`[]`、断行、DOI 丢失）会在解析层标注，不臆造字段；报告页与 Markdown / HTML 导出还会写明「文字来源：OCR 识别（扫描件） · 页数 · 字符数」，提醒用户 OCR 错字会传递到核验结论。复现：`PYTHONPATH=src python scripts/eval_ocr_scanned.py --input <paper.pdf>`。

## 它做什么

| 检查 | 做法 | 输出 |
|---|---|---|
| **引文真实性** | 解析 DOI / 题名，查 OpenAlex → Crossref → arXiv；DOI 全系统不存在、或 DOI 指向另一篇文献才判「疑似虚构」 | `真实一致` / `元数据偏差` / `疑似虚构或错配` / `未找到匹配` / `无法核验` + 证据链接 |
| **引用支持度** | 抽取正文引用句 + 被引论文摘要，交给可选的 LLM judge | `支持` / `部分支持` / `矛盾` / `无证据` / `未检测` |
| **新国标格式** | 按 GB/T 7714-2025 的 17 个类型码检查字段、作者名、永久标识符，并可一键生成规范条目 | 逐条「缺什么 / 错在哪 / 怎么改」 |
| **图表结论核验**（可选） | 上传图表截图 + 正文结论（同一张图一次最多 5 条），交给开源的 Qwen2.5-VL-7B 判断 | `支持` / `矛盾` / `信息不足` + 一句理由，多条时逐条列表 |
| **多篇文献对比**（可选） | 一次上传 2–6 篇，抽取研究问题 / 方法 / 数据 / 结论 / 局限 / 贡献六维矩阵 | 对比矩阵 + Markdown / CSV 导出 |
| **选题与文献发现**（可选） | 输入中文主题，先扩展成中英双语检索词，再查 OpenAlex；合并去重后按「相关度 + 标题重合 + 关键词 + 被引 + 新近度 + OA」透明规则排序；支持排序切换、语言筛选、稳定分页、勾选入库 | 卡片列表（摘要 / 被引 / OA / 命中理由）+ CSV 导出 |
| **撤稿/问题文献提醒** | 命中 OpenAlex `is_retracted` 标记即提示，但不改变真实性结论 | 「该文献已撤稿」+ 引用前核对提示 |
| **审稿视角汇总** | 聚合真实性、支持度、格式、正文引注一致性、撤稿标记 | 一条「建议修改 / 可送审」结论 + 问题清单 |

## 实测结果

在自建 CiteBench-CN（250 条：100 真实 / 75 元数据扰动 / 75 虚构或错配）上：

| 系统 | Macro-F1 | Accuracy |
|---|---|---|
| **CiteGuard v1.1** | **0.9684** | **0.968** |
| DeepSeek zero-shot（prompt v3 冻结） | 0.5159 | 0.536 |

```
混淆矩阵（行=真实，列=预测）
        Exact  Minor  Major
Exact  [ 100,     0,     0 ]
Minor  [   8,    67,     0 ]
Major  [   0,     0,    75 ]

消融
full              0.9684
- DOI anchor      0.8071  (Δ -0.1613)
- title search    0.7744  (Δ -0.1940)
```

> 评测集、数据卡、评测脚本与 DeepSeek 基线都在 `data/citebench_cn/` 与 `scripts/` 下；`seed=20261022`，重建字节级一致（SHA-256 `1a8e466b…`）。
> 答辩/汇报用的**已核实数字一页纸**见 [docs/ppt_numbers.md](docs/ppt_numbers.md)；网页 `/benchmark` 也有同一套数据面板。

支持度判定（可选）：

在自建 ClaimSupport-CN（100 条：支持 40 / 部分支持 25 / 矛盾 15 / 无证据 20，标签由构造决定）上：

| 指标 | Macro-F1 | Accuracy |
|---|---|---|
| 支持度四分类（deepseek-chat，temperature 0，两段式 judge + 少样本 v10） | **0.9597** | **0.9500** |
| 同上，单段旧版（prompt v3，仅作对比） | 0.9005 | 0.8900 |

```
混淆矩阵（行=真实，列=预测）            support partial contradict no_evidence
support        [ 37,   3,   0,   0 ]
partial        [  2,  23,   0,   0 ]
contradict     [  0,   0,  15,   0 ]
no_evidence    [  0,   0,   0,  20 ]
```

> **两段式判定**：第一段按证据给「支持/部分支持/矛盾/无证据」并摘出证据句；第二段只对「支持」结论做**覆盖审计**——把引用句拆成对象/条件/因果/量级等要素，证据没覆盖全部要素就降级为「部分支持」。这一步专门修掉旧版最大的错误来源（partial 被误判为 support），代价是「支持」类约 40% 的条目多一次 LLM 调用（`CITEGUARD_SUPPORT_AUDIT=0` 可关）。
> 该数据集为程序化构造（构造规则自检 100/100，20% 抽样复核 0 失败），标签由构造决定，不是人工双标，因此不报告 κ；误差现在主要来自 support ↔ partial 的边界样本。
>
> 外部验证：同一 judge 零样本迁移到英文公开基准 **SciFact**（300 条 dev claims，**未在 SciFact 上训练/微调**，四分类映射为三分类）：给定标注证据句 macro-F1 **0.8224**，给定整段摘要 **0.7939**。说明判定方法不是只在自建中文集上有效。
>
> 本地开源模型：接口是 OpenAI 兼容的，可切到 Qwen 系列开源模型完全离线运行。CPU 上 Qwen3-1.7B（20 条、精简 prompt）macro-F1 0.71；GPU 上实测 Qwen2.5-3B/7B、Qwen3-8B/14B（test 60，同一 v10 prompt + 审计 v2）：**Qwen3-14B 0.9574**（dev 40 上 **1.0000**；全 100 条 **0.9744**）、Qwen3-8B 0.8515、7B 0.7181。14B 与托管 DeepSeek 同 test 口径（0.9598）只差 **0.24 分**，全 100 条 0.9744 高于托管的 0.9597——但 test 只有 60 条，不能外推成全面追平；8B/7B 仍明显更低。细节与复现命令见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) §4.2。

图表结论核验（可选，需自备 GPU 视觉服务）：

Qwen2.5-VL-7B（Apache-2.0，单张 RTX 4090）在 50 条图表结论上：只给图表 v2 口径 **0.90**，粘贴正文/图注上下文后 **0.94**（支持类 0.92 / 矛盾类 0.96，误报「矛盾」**0** 条，平均 2.56 秒/条）；其中合成控例 38/40=0.95、真实论文图表 9/10=0.90。同一张图可一次核验最多 5 条结论、逐条给出判断与理由；正文上下文可手动粘贴、上传 PDF 按页取，页码留空时还会按声明里的图号自动定位图注页（扫描页/找不到时提示手动粘贴或填页码）；不替代引文真实性核验；`insufficient` 一律建议人工复核。实现、局限与复现命令见 [docs/figure_check.md](docs/figure_check.md)。

多篇文献对比（可选，复用同一判官接口）：

在 4 篇**真实中文论文**（文本型 PDF，教育学/语言学方向）上，4/4 篇抽取成功、0 报错，总耗时 **8.0 秒**（约 2 秒/篇），每篇填出 5–6 个字段；「局限」在 3 篇中显示「未提及」（摘要本身不写局限，系统不编造）。这是工程实测而非字段准确率评测：字段为机器抽取，写进综述前须回原文核对。实现、边界与复现命令见 [docs/compare.md](docs/compare.md)。

**选题与文献发现**：输入中文主题，系统先做**中英双语查询扩展**（可关），再查 OpenAlex。实测 `人工智能 教育`：扩展后上游命中 **1,141,987** 条（原查询 112,724 条），冷启动 6–10 s（含一次 LLM 扩展 + 两次上游请求），缓存命中 74 ms；第 1、2 页各 20 条且**零重叠**。卡片自动标注期刊论文/综述/预印本/图书章节等类型，默认过滤**撤稿**与**勘误/杂项**（如 erratum 会继承原文标题和被引、误排第一，现已剔除并显示过滤条数），结果区显示「第 x / y 页」。排序/语言筛选/分页/勾选入库/CSV 均可用。这只是工程可用性验证，不是排序质量评测——排序规则透明、不训练，没有 relevance 标注集；中文覆盖率仍受 OpenAlex 限制。实现与边界见 [docs/discover.md](docs/discover.md)。

## 架构

```
输入 PDF / DOCX / 文本
  → ① 中文引文解析器（自研）：正文夹注 ↔ 文后参考文献表对齐
  → ② 多源元数据核验（自研编排）：本地题录库 → OpenAlex(CC0) → Crossref → arXiv(CC0)
     · DOI 跨机构回退：Crossref → doi.org Handle → DataCite / 中国 DOI 平台落地页
  → ③ 引用支持度判定（自研编排 + 可插拔 LLM judge）：claim 抽取 → 摘要证据 → 四分类
  → ③b 多篇文献对比（可选）：2–6 篇 → 研究问题/方法/数据/结论/局限/贡献矩阵
  → ④ GB/T 7714-2025 规则引擎（自研）：17 个类型码 / 13 类必备字段模板 + 正文引注一致性
  → ⑤ 证据报告（Web / HTML / Markdown / JSON / 纯文本参考文献表）
```

## 快速开始

```bash
python3 -m pip install -r requirements.lock.txt   # 锁定版本；也可用 requirements.txt 取兼容范围

# CLI：分析一篇论文
PYTHONPATH=src python3 -m citeguard.cli --input web/static/samples/sample_paper.txt --out out/demo

# Web 工作台
PYTHONPATH=src python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000

# 评测 CiteBench-CN
PYTHONPATH=src python3 scripts/evaluate_citebench.py --limit 0 --out data/citebench_cn/results.json
```

服务器环境（无 venv 时依赖装在 `.pylibs`）：

```bash
PYTHONPATH=src:.pylibs python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000
PYTHONPATH=src:.pylibs python3 scripts/evaluate_citebench.py --limit 0
```

### 引用支持度（可选）

支持度判定需要一个 LLM judge。默认读环境变量 `DEEPSEEK_API_KEY`；没有 key 时自动降级为「未检测」，不影响真实性/格式核验。

判定只在**题录匹配可靠时**才进行：状态为 `Exact/Minor`，或标题相似度 ≥ 0.90（`CITEGUARD_SUPPORT_MIN_TITLE_SIM` 可调）。原因是摘要必须属于被引论文本身——相似度 0.4 的 Crossref 记录往往是另一篇论文，拿它判「无证据」会把匹配失败误报成引用问题。这类条目会显示「题录匹配度不足」，修复题录或导入带摘要的本地库后重跑即可。

```bash
export DEEPSEEK_API_KEY=...   # 只在本地/服务器环境中设置，不要提交
PYTHONPATH=src python3 -m uvicorn web.app:app --port 8000
```

判定后端是**可插拔的 OpenAI 兼容接口**：指向本地开源模型即可完全离线判定，不需要任何商业 API。仓库自带 `scripts/local_judge_server.py`（transformers + CUDA，支持 `--device auto` 把 7B 拆到多张 12GB 卡），也可用 Ollama / vLLM / llama.cpp-server：

```bash
# 服务器上直接起本地判官（示例：Qwen2.5-7B，两张卡）
python scripts/local_judge_server.py --model /path/Qwen2.5-7B-Instruct \
  --device auto --dtype float16 --port 8099
export CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8099/v1
export CITEGUARD_JUDGE_MODEL=Qwen2.5-7B-Instruct
export CITEGUARD_JUDGE_API_KEY=local   # 本地服务随便填；不校验

# 或者用 Ollama（任意 OpenAI 兼容服务同理）
ollama serve && ollama pull qwen2.5:7b-instruct
export CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:11434/v1
export CITEGUARD_JUDGE_MODEL=qwen2.5:7b-instruct
```

实测（ClaimSupport-CN，与托管模型同一数据/脚本；托管 v10 参考 **0.9597**，同 test 60 参考 0.9598）：

| 本地模型 | 硬件 | 早期配置 | 当前 v10 配置 |
|---|---|---|---|
| Qwen3-1.7B（20 条试点） | CPU | 0.5060 | 0.7059（精简 prompt） |
| Qwen2.5-3B-Instruct | 1×TITAN Xp | 0.3894 | 0.6291（精简 prompt） |
| Qwen2.5-7B-Instruct | 2×TITAN Xp | 0.7181 | 0.7022（精简 prompt） |
| Qwen3-8B（dev 40 / test 60） | 1×RTX 4090 | 0.7817 | **0.8882 / 0.8515** |
| Qwen3-14B（dev 40 / test 60） | 2×RTX 4090 | 0.8676 / 0.8887（v7: 0.9063） | **1.0000 / 0.9574**；全 100 条 **0.9744** |
| Qwen3-8B / 14B（产品路径，全 100 条） | 1× / 2×RTX 4090 | — | **0.8664 / 0.9744**（`judge_support` 直调，自动 v10 + 审计 v2） |
| Qwen3-14B（4-bit NF4，单卡 24GB） | 1×RTX 4090 | — | **1.0000 / 0.9588 / 0.9754**（dev 40 / test 60 / 全 100 条；显存约 11.7GB，13.3 s/条） |

> 2026-10 的 Qwen3-8B/14B 用固定划分：dev 40 选方案，test 60 只报最终数字（`data/claimsupport_cn/split_seed20261024.json`）。v8 先立住两条边界（引用句含证据之外的目的/设计细节 → partial；证据只覆盖部分断言 → partial），把 14B 的 test 从 v4 0.8887 / v7 0.9063 提到 **0.9574**；v10 再补一条「证据与引文方向相反 → contradict」，把 14B 的 dev 从 0.9793 推到 **1.0000**，test 保持 **0.9574**（剩余 3 条固定错误），全 100 条 **0.9744**；托管 v10 同口径 0.9597。需要说明：v10 的三条边界与这份构造集的划分规则同源，提升里有一部分来自规则对齐；因此同时保留旧版历史数字与同口径托管对照，不挑高的说。硬件是实验室已有 GPU，不是为参赛购买。 4-bit NF4 量化后 14B 可压到单张 24GB 卡（约 11.7GB 显存），dev 40 1.0000、test 60 0.9588，质量与 bf16 基本一致。覆盖审计 v2 对自托管端点自动启用（`CITEGUARD_SUPPORT_AUDIT_STYLE=auto`），托管 API 仍用 v1 以保持历史可比；prompt 现在两端统一用 v10。
>
> 小模型（3B 及以下）跟不动长 prompt，建议换精简 prompt：`CITEGUARD_SUPPORT_PROMPT_FILE=scripts/support_prompt_simple.txt`（自定义 prompt 自动使用独立缓存），并设 `CITEGUARD_SUPPORT_AUDIT=0`。7B/8B/14B 适合两段式产品 prompt。判定结果按「模型 + prompt 版本 + 审计版本」分键缓存，换模型会自动重判。
>
> **产品路径直调核对**：不经评测脚本，直接用 `citeguard.support.judge_support`（自动选 v10 + 审计 v2）跑同一 100 条：14B **0.9744**、8B **0.8664**，与离线脚本逐条一致。这一步也修掉两个只在自托管端点暴露的产品 bug：审计风格原先只认 `CITEGUARD_JUDGE_BASE_URL`，若用 `DEEPSEEK_BASE_URL` 指向本地会错用 v1（产品路径一度只有 0.6864）；判定缓存键原先不含审计风格，切换 v1/v2 会复用旧最终标签。修复后按「模型 + prompt 版本 + 审计风格」分键；证据 `data/experiments/support_local_qwen3_{14b,8b}_product_all.json`。

## 目录

```
citeguard/
├── src/citeguard/        # 核心包：解析 / 核验 / 规则 / 支持度 / 报告
├── web/                  # FastAPI + Jinja2 工作台（4 个页面）
├── scripts/              # 评测、基线、样例、复现、自检
├── tests/                # pytest 用例
├── docker/               # Dockerfile + compose
├── data/citebench_cn/    # CiteBench-CN 数据集、结果、数据卡
├── data/claimsupport_cn/ # ClaimSupport-CN 数据集、结果、数据卡
├── docs/                 # 评测规划、真实数据实测、用户测试包、部署文档
├── requirements.txt      # 兼容范围
├── requirements.lock.txt # 锁定版本（可复现）
├── reproduce.sh
├── LICENSE               # Apache-2.0
├── NOTICE
└── THIRD_PARTY_NOTICES.md
```

## 数据与许可证

| 资源 | 用途 | 许可证 |
|---|---|---|
| 本项目代码 | — | Apache-2.0 |
| CiteBench-CN | 中文引文核验评测集 | CC-BY-4.0 |
| ClaimSupport-CN | 中文引用支持度评测集 | CC-BY-4.0 |
| OpenAlex | 文献元数据 | CC0 1.0 |
| arXiv 元数据 | 预印本元数据 | CC0 1.0 |
| Crossref | DOI 元数据 | 元数据开放；摘要版权归出版商 |
| DataCite / doi.org Handle | 非 Crossref 注册 DOI 的注册信息与落地页元数据（含中国 DOI 平台） | 公开接口 |
| FastAPI / Starlette / Uvicorn / Jinja2 | Web 后端与模板 | MIT / BSD-3-Clause |
| pdfplumber / pdfminer.six / pypdf | PDF 文本层抽取 | MIT / BSD-3-Clause |
| python-docx | Word（.docx）解析 | MIT |
| rapidfuzz | 题名相似度 | MIT |

**已集成与候选资源**：Qwen3-8B/14B、Qwen2.5-7B/3B、Qwen3-1.7B（均 Apache-2.0）已实测接入支持度判定；Qwen3-Embedding / Reranker（Apache-2.0）、bge-m3（MIT）、PaddleOCR（Apache-2.0）、Docling（MIT）仍是路线图。支持度 judge 走 OpenAI 兼容接口，切换到这些本地后端只需改 `CITEGUARD_JUDGE_BASE_URL` / `CITEGUARD_JUDGE_MODEL`。

完整清单见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

> 不使用知网 / 万方全文；不 re-host NC/ND 数据；CiteBench-CN 只包含自建标注与公开元数据 ID，不含第三方全文或摘要。

## 开放成果

| 成果 | 内容 | 许可 |
|---|---|---|
| 代码仓 | 本仓库（解析器 / 核验器 / GB-T 规则引擎 / Web 工作台 / 评测脚本 / 测试） | Apache-2.0 |
| CiteBench-CN | 250 条中文引文真实性评测集 + 数据卡 + 评测结果 | CC-BY-4.0 |
| ClaimSupport-CN | 100 条中文引用支持度评测集 + 数据卡 + judge 结果 | CC-BY-4.0 |
| 上游贡献 | RefChecker PR #77：修复 BibTeX 裸值（`year = 2017`）被丢弃导致年份校验失效 | [PR](https://github.com/markrussinovich/refchecker/pull/77) |

复现（约 30 分钟，需联网取一次元数据，之后走本地缓存）：

```bash
pip install -r requirements.lock.txt
bash reproduce.sh                     # 构建数据集 → 评测 → 一致性校验 → 离线测试（可选 DeepSeek 基线/支持度）
```

> 每个对外数字对应的原始结果 JSON、生成脚本与代码快照见 [data/experiments/README.md](data/experiments/README.md)。

## 核验结论怎么读

| 结论 | 含义 | 建议动作 |
|---|---|---|
| **真实一致** | DOI/题名在 OpenAlex/Crossref/arXiv 命中，且年份、作者、来源、卷期页一致 | 无需处理 |
| **元数据偏差** | 文献存在，但年份/作者顺序/来源/卷期/页码与数据库不一致 | 按提示逐项核对（作者顺序、年份最常见） |
| **疑似虚构或错配** | 证据很强：DOI 在 DOI 系统也不存在，或 DOI 指向的是另一篇文献 | 优先处理，极可能是编造或张冠李戴 |
| **未找到匹配记录** | 数据库里没有足够相似的记录 | **不等于造假**：可能是中文期刊未被 OpenAlex/Crossref 收录，也可能是引文有误；用卡片上的百度学术 / Google Scholar / Crossref 链接人工核对 |
| **无法核验** | 本次查询失败（网络/数据源问题） | 稍后重跑 |

> 网页型引文（`[EB/OL]`）会先查链接本身：链接可达且页面标题与引文题名一致 → 判「真实一致」；链接失效/需要登录 → 只提示人工核对，**不会**判「疑似虚构」。带 SSRF 防护（只允许公网 http/https、80/443 端口），`CITEGUARD_URL_CHECK=0` 可完全离线关闭。

引用支持度（可选，需 LLM judge）与真实性是两条独立的轴：

| 支持度 | 含义 | 建议动作 |
|---|---|---|
| **支持** | 被引文献的摘要确实支持正文这句话 | 无需处理 |
| **部分支持** | 方向一致但表述更强/更窄于原文 | 核对是否夸大或断章取义 |
| **矛盾** | 被引文献的结论与正文这句话相反 | **优先处理**：正文论点可能站不住 |
| **无证据 / 未检测** | 只有无关内容，或缺少摘要/超出判定上限/未配置 judge | 看卡片上的原因；补齐摘要或提高上限后重跑 |

> 报告页支持「仅看需处理」与「支持度矛盾 / 部分支持」筛选；`矛盾` 与 `部分支持` 的条目即使元数据完全一致也会被列出来。

## 把参考文献表重排成 GB/T 7714-2025

报告页新增「导出参考文献表 / 复制参考文献表」：把解析出的每一条按 GB/T 7714-2025 的字段顺序与标点重排（作者超 3 人补「等」/`et al`、类型码、卷(期)、页码范围、DOI），生成可直接粘贴进 Word 的 `.txt`；Markdown / HTML 报告末尾也会附这份表，CSV 里多一列「规范条目（按原文重排）」。

> 它只做**格式重排**，不会补原文没有的字段（如缺卷期、缺 DOI 仍会缺）；导出前请对照原文核对。整篇格式合规问题仍以上方的字段检查结果为准。

## 正文引注一致性

顺序编码制论文里，参考文献表应当只列正文引用过的文献，编号按正文首次引用顺序。报告页会核对：正文出现但文献表没有的编号、文献表里从未被正文引用的条目、以及首次引用顺序与编号不一致（计数提示，不扣单条合规分）。只粘贴参考文献表、没有正文时自动跳过；作者-年份制论文说明不适用，不会硬套数字编号规则。

> 这是「正文与文献表对齐」检查，不判断引文真假，也不替代人工核对。

检查器本身有 15 例按顺序编码制构造的自检用例（未引用、缺失编号、顺序倒置、范围引注、作者-年份跳过等），脚本见 `scripts/eval_citation_consistency.py`，结果 **15/15** 通过；这是规则自检，不是人工标注评测。

> 设计取舍：**宁可说「未核实」，也不误指控**。在 409 条真实发表的中文参考文献上实测，当前判「疑似虚构」的比例为 **0%**；代价是约 48% 的中文文献只能给「未找到匹配记录」（旧规则在 224 条子集上曾把 45.1% 误判为虚构）。详见 [docs/real_data_eval.md](docs/real_data_eval.md)。

## 中文文献：导入本地题录库

中文期刊论文大多不在 OpenAlex / Crossref 里：实测 409 条真实中文参考文献中，**约 52% 能给出确定结论**（真实一致 / 元数据偏差），其余约 48% 显示「未找到匹配」。这不是引文的问题，是数据源覆盖问题。

解决方案是**用用户自己的题录导出做核验**：知网 / NoteExpress / EndNote / Zotero 都能导出 RIS、BibTeX、EndNote、CSL-JSON 或纯文本参考文献表，导入「题录库」后，核验会优先比对这些本地记录（数据只存本机，不上传）：

```bash
# 导入一次，之后每次分析自动使用
python -m citeguard.cli --import-library cnki_export.ris
python -m citeguard.cli --input thesis.pdf --library cnki_export.ris   # 或临时指定
```

网页端「题录库」页可以直接管理：导入/清空、搜索、逐条删除，导入时会统计「解析 / 新增 / 跳过重复 / 缺摘要」的条数；报告里会标注哪些条目来自本地库。判断正文是否真的支持这条引文需要摘要——导出时没带摘要也没关系，页面上点「自动补摘要」即可（只处理缺摘要的条目，先 DOI 精确查询、再 OpenAlex/Crossref 题名检索；标题相似度 ≥ 0.92 且年份兼容才接受，不会把另一篇论文的摘要硬塞进来）。命令行等价方式：

```bash
# 从 OpenAlex/Crossref 补全题录库里缺失的摘要（只取公开元数据，写回本地库）
PYTHONPATH=src python3 scripts/enrich_library_abstracts.py --dry-run   # 先看会补多少
PYTHONPATH=src python3 scripts/enrich_library_abstracts.py
```

实测（20 篇真实中文论文，409 条引文，PDF 路径）：

| | 无本地库 | 导入本地库后 |
|---|---|---|
| 能给出结论（真实一致 / 元数据偏差） | 212 条（52%） | **409 条（100%）** |
| 未找到匹配 | 197 条（48%） | **0 条** |
| 检出字段偏差（年份/卷期/页/作者与题录不符） | — | **4 条** |

> 说明：这是「用户拥有其引用题录」的情形；库里没有的条目会自动回退到在线核验。
> 作者字段若解析不完整（PDF/OCR 常把英文缩写拆成 “D.”、“et al.”），核验会**跳过作者比对**并在格式检查里提示补全，
> 而不是把它算成「元数据偏差」。4 条字段偏差抽查原始条目后，均为 PDF 抽取排版差异（重复行、栏间文字粘连、断词），
> 不是论文本身的引用错误——所以这里的偏差数是可信的 4 条，不是把解析噪声当错误。

## 真实论文实测

| 指标 | 结果 |
|---|---|
| 参考文献解析干净率（22 篇真实论文） | **100%**（发布版文字 409 条）/ **99.6%**（PDF 抽取 529 条；另有 1 篇文字层损坏的 PDF 走 OCR 兜底） |
| 真实已发表文献被误判「疑似虚构」 | **0 / 409** |
| 真实性核验 · 按语言拆分 | 英文 **186 / 199（93.5%）** 可确认；中文 **26 / 210（12.4%）**——中文期刊大多不在 OpenAlex / Crossref 的开放索引里，报告会明确标注并给出知网 / 百度学术检索入口，不判「疑似虚构」 |
| 真实文献注入错误检出（可控变异） | **197 / 200（98.5%）**：伪造 DOI 40/40、年份偏移 39/40、作者替换 39/40、刊名替换 39/40、题名替换 40/40；未改动基线 40 条中误判「疑似虚构」**0 条** |
| 网页型引文（`[EB/OL]`）链接核验 | 23 条真实网页引文中 **13 条「链接可达且页面标题一致」**；3 条标题不一致、7 条访问受限 |
| GB/T 7714-2025 规则回归（E4） | 100 条真实文献类型码识别 **100%**、必填字段 98.4%；30 条受控漂移严格检出 **29/30（96.7%）** |
| 单篇 40 条引文的核验耗时 | 并发 4 线程，约 1～2 分钟（含缓存） |

> 注入实验说明：从 125 条带 DOI 的真实引文中抽 40 条，每条注入 5 类错误，共 200 例；「检出」= 判为「疑似虚构或错配」或「元数据偏差」。3 例漏判均因索引记录本身缺年份/作者/刊名（例如中国 DOI 平台落地页元数据不全），不是把错误引文当成了正确引文。另有 13 条无 DOI/URL 的拼接伪造条，产品按设计给「未找到匹配」而非指控——两条边界分开报告，不混成一个「准确率」。脚本与逐条结果在 `scripts/eval_real_mutation.py`、`data/experiments/real_mutation_eval.json`。

> 以上均为内部实验数据。**真实用户研究还没做**——可直接照做的任务脚本、指标、SUS 问卷与结果模板在 [docs/user_test_kit.md](docs/user_test_kit.md)，跑完 3–5 人即可得到可引用的用户数据。

## 已知局限

- 中文文献在 OpenAlex / Crossref 的覆盖率有限：真实语料里**英文文献 93.5% 可自动确认，中文文献只有 12.4%**（210 条中文引文仅 26 条命中）——这是中文库不在开放索引里的结构性缺口，不是引文造假。报告会对未命中的中文条目单独提示，并提供知网/百度学术检索入口供人工核对；**导入本地题录库后，20 篇测试语料 409/409 可判定**。
- 摘要覆盖更少，部分条目支持度会显示「未检测」；题录库页可点「自动补摘要」从 OpenAlex / Crossref 补全（入口保守：标题相似度 ≥ 0.92 且年份兼容才接受，补不到就保持原样），或在导出题录时勾选「摘要/Abstract」再导入。
- 匹配度不足（标题相似度 < 0.90 且非 Exact/Minor）的条目不会做支持度判定：此时摘要是另一篇论文的可能性很高，宁可显示「未检测」也不输出误导性的「无证据」。
- 支持度判定默认只判前 30 条有摘要且被正文引用的文献（可在上传时选 10/30/80/全部或关闭），未判定的条目会写明原因。
- 扫描件可自动 OCR（可选依赖 `rapidocr-onnxruntime`）；OCR 会偶发字符错误（例如把 `[J]` 识别成 `[]`），此类条目会保留题目/来源但标注「类型码丢失」，请人工核对。
- 两栏排版、复杂表格版式仍可能影响抽取（已按页面中线做两栏切分，但非通用版面分析）。
- 英文 APA 式参考文献里，题名本身含 `(2017).` 这类年份样式时，极少数条目会把作者行归到上一条（22 篇语料 529 条 PDF 抽取结果中 1 条）；网页型引文（`机构. 题名. 链接`）已按 `EB` 类型解析、机构作者整体保留、链接不再混入题名。
- 作者比对已改为按姓氏（`Yu, H.` ↔ `Hui Yu`），机构作者、拼音/中文别名、同名不同人仍可能造成少量误判；题名一致但作者完全不同的记录可能是书评，报告会提示人工核对。
- 支持度判定为辅助提示，不构成学术结论。
- 多篇文献对比只读每篇摘要与正文前部（约 3600 字），不读全文方法与实验章节；六维字段是机器抽取，可能不完整或概括偏差；它不做跨文献综合（研究空白仍需人来写），也没有字段级准确率标注集。
- 选题与文献发现只消费 OpenAlex 公开元数据（CC0），不抓取、不转存全文；中文主题的召回取决于 OpenAlex 覆盖，查询扩展依赖已配置的判定模型（不可用时退化为原查询）；排序是启发式规则而非学习排序，结果需要人工判断；「加入题录库」只存题录，不代表已核验。
- 「刷新/加载更多」最多 5 页（选 50 条时 4 页），每页最多 50 条；`matched` 是上游计数，不是可翻页条数。观察到的中文结果占比（自动扩展 3/20、纯中文查询 8/20）只是当次结果，不代表长期质量，也不报告排序指标。
- GB/T 7714-2025 规则引擎基于公开规则事实编码，未复制标准原文；请以国家标准原文与人工复核为准。

## 参考与致谢

- OpenAlex（CC0）、Crossref、arXiv 提供开放元数据。
- 方法对标：OpenScholar（Nature 2025）、RefChecker（MIT）、CiteCheck、DeepSciVerify、CNCV、PaperQA2、LitSearch。
- Qwen3 技术报告（arXiv:2505.09388）。

## 引用

```bibtex
@software{citeguard2026,
  title = {CiteGuard-CN: 中文论文引文核验工作台与 CiteBench-CN 评测集},
  year  = {2026},
  url   = {https://github.com/kkk431/citeguard-cn},
  note  = {Apache-2.0 (code) / CC-BY-4.0 (datasets)}
}
```
