# 引证卫士 CiteGuard-CN

> 给中文论文做一次「引文体检」：**引文是否真实存在、引用是否支持正文那句话、格式是否符合 GB/T 7714-2025**。每条结论都带证据链接。

CiteGuard-CN 是一个开源的中文引文核验工作台，面向毕业论文、课程论文与期刊投稿场景。它把「中文引文解析 → 多源元数据核验 → 引用支持度判定 → 新国标规则检查」串成一条可复现的流水线，并附带一个 250 条的中文评测基准 **CiteBench-CN**。

支持的输入：**PDF**（文字层优先；扫描件可自动 OCR）、**Word（.docx）**（含放在表格里的参考文献表）、**纯文本 / Markdown**。旧版 `.doc` 请先另存为 `.docx` 或 PDF。

扫描件 OCR 是可选依赖（不装也能用，只是遇到扫描件会提示）：

```bash
pip install -r requirements-ocr.txt   # rapidocr-onnxruntime + pypdfium2，CPU 即可
```

> 实测（7 页纯图片 PDF，150 dpi）：OCR 后仍能解析出 **23/24 条**参考文献，题名/年份覆盖 23/23、作者 21/23；单页约 19 s（CPU）。扫描版 PDF 的 OCR 噪声（`[J]`→`[]`、断行、DOI 丢失）会在解析层标注，不臆造字段。复现：`PYTHONPATH=src python scripts/eval_ocr_scanned.py --input <paper.pdf>`。

## 它做什么

| 检查 | 做法 | 输出 |
|---|---|---|
| **引文真实性** | 解析 DOI / 题名，查 OpenAlex → Crossref → arXiv；DOI 全系统不存在、或 DOI 指向另一篇文献才判「疑似虚构」 | `真实一致` / `元数据偏差` / `疑似虚构或错配` / `未找到匹配` / `无法核验` + 证据链接 |
| **引用支持度** | 抽取正文引用句 + 被引论文摘要，交给可选的 LLM judge | `支持` / `部分支持` / `矛盾` / `无证据` / `未检测` |
| **新国标格式** | 按 GB/T 7714-2025 的 17 个类型码检查字段、作者名、永久标识符，并可一键生成规范条目 | 逐条「缺什么 / 错在哪 / 怎么改」 |

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
| 支持度四分类（deepseek-chat，temperature 0，两段式 judge） | **0.9328** | **0.9300** |
| 同上，单段旧版（prompt v3，仅作对比） | 0.9005 | 0.8900 |

```
混淆矩阵（行=真实，列=预测）            support partial contradict no_evidence
support        [ 37,   2,   0,   1 ]
partial        [  2,  23,   0,   0 ]
contradict     [  1,   1,  13,   0 ]
no_evidence    [  0,   0,   0,  20 ]
```

> **两段式判定**：第一段按证据给「支持/部分支持/矛盾/无证据」并摘出证据句；第二段只对「支持」结论做**覆盖审计**——把引用句拆成对象/条件/因果/量级等要素，证据没覆盖全部要素就降级为「部分支持」。这一步专门修掉旧版最大的错误来源（partial 被误判为 support），代价是「支持」类约 40% 的条目多一次 LLM 调用（`CITEGUARD_SUPPORT_AUDIT=0` 可关）。
> 该数据集为程序化构造（构造规则自检 100/100，20% 抽样复核 0 失败），标签由构造决定，不是人工双标，因此不报告 κ；误差现在主要来自 support ↔ partial 的边界样本。
>
> 外部验证：同一 judge 零样本迁移到英文公开基准 **SciFact**（300 条 dev claims，**未在 SciFact 上训练/微调**，四分类映射为三分类）：给定标注证据句 macro-F1 **0.8224**，给定整段摘要 **0.7939**。说明判定方法不是只在自建中文集上有效。
>
> 本地开源模型：接口是 OpenAI 兼容的，可切到 Qwen3 等开源模型。已在 CPU 上用 **Qwen3-1.7B（Apache-2.0）** 离线跑通（20 条试点 macro-F1 0.71，明显低于托管大模型但完全离线）；生产离线场景建议 Qwen3-8B + GPU。细节见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) §4.2。

## 架构

```
输入 PDF / DOCX / 文本
  → ① 中文引文解析器（自研）：正文夹注 ↔ 文后参考文献表对齐
  → ② 多源元数据核验（自研编排）：本地题录库 → OpenAlex(CC0) → Crossref → arXiv(CC0)
     · DOI 跨机构回退：Crossref → doi.org Handle → DataCite / 中国 DOI 平台落地页
  → ③ 引用支持度判定（自研编排 + 可插拔 LLM judge）：claim 抽取 → 摘要证据 → 四分类
  → ④ GB/T 7714-2025 规则引擎（自研）：17 个类型码 / 13 类必备字段模板
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

```bash
export DEEPSEEK_API_KEY=...   # 只在本地/服务器环境中设置，不要提交
PYTHONPATH=src python3 -m uvicorn web.app:app --port 8000
```

判定后端是**可插拔的 OpenAI 兼容接口**：指向本地开源模型即可完全离线判定，不需要任何商业 API（已用 Qwen3-1.7B 在 CPU 上实测跑通，见 `data/experiments/support_local_qwen3_1.7b_simple.json`）：

```bash
# 例：Ollama 起一个开源模型（任意 OpenAI 兼容服务：vLLM / llama.cpp-server / LM Studio 同理）
ollama serve
ollama pull qwen2.5:7b-instruct
export CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:11434/v1
export CITEGUARD_JUDGE_MODEL=qwen2.5:7b-instruct
# 本地服务通常不需要 key；要鉴权时再设 CITEGUARD_JUDGE_API_KEY
```

> 小模型（1.7B 级）在 CPU 上 20 条试点 macro-F1 0.7059（精简 prompt，46 s/条），明显低于 DeepSeek 的 0.9328——离线可用 ≠ 质量相同；生产环境建议 8B 级模型 + GPU，或继续用 API judge。判定结果按「模型 + prompt 版本」分键缓存，换模型会自动重判。

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

**候选资源（本期未集成，仅路线图）**：Qwen3-8B（Apache-2.0）、Qwen3-Embedding / Reranker（Apache-2.0）、bge-m3（MIT）、PaddleOCR（Apache-2.0）、Docling（MIT）。支持度 judge 走 OpenAI 兼容接口，切换到这些本地后端只需改 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`。

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
bash reproduce.sh                     # 构建数据集 → 评测 → 一致性校验（可选 DeepSeek 基线/支持度）
```

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

> 设计取舍：**宁可说「未核实」，也不误指控**。在 409 条真实发表的中文参考文献上实测，当前判「疑似虚构」的比例为 **0%**；代价是约 48% 的中文文献只能给「未找到匹配记录」（旧规则在 224 条子集上曾把 45.1% 误判为虚构）。详见 [docs/real_data_eval.md](docs/real_data_eval.md)。

## 中文文献：导入本地题录库

中文期刊论文大多不在 OpenAlex / Crossref 里：实测 409 条真实中文参考文献中，**约 52% 能给出确定结论**（真实一致 / 元数据偏差），其余约 48% 显示「未找到匹配」。这不是引文的问题，是数据源覆盖问题。

解决方案是**用用户自己的题录导出做核验**：知网 / NoteExpress / EndNote / Zotero 都能导出 RIS、BibTeX、EndNote、CSL-JSON 或纯文本参考文献表，导入「题录库」后，核验会优先比对这些本地记录（数据只存本机，不上传）：

```bash
# 导入一次，之后每次分析自动使用
python -m citeguard.cli --import-library cnki_export.ris
python -m citeguard.cli --input thesis.pdf --library cnki_export.ris   # 或临时指定
```

网页端在「题录库」页导入/清空，报告里会标注哪些条目来自本地库；导入时会统计「带摘要」的条数——判断正文是否真的支持这条引文需要摘要。导出时没带摘要也没关系，可以补：

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
| 网页型引文（`[EB/OL]`）链接核验 | 23 条真实网页引文中 **13 条「链接可达且页面标题一致」**；3 条标题不一致、7 条访问受限 |
| 单篇 40 条引文的核验耗时 | 并发 4 线程，约 1～2 分钟（含缓存） |

> 以上均为内部实验数据。**真实用户研究还没做**——可直接照做的任务脚本、指标、SUS 问卷与结果模板在 [docs/user_test_kit.md](docs/user_test_kit.md)，跑完 3–5 人即可得到可引用的用户数据。

## 已知局限

- 中文文献在 OpenAlex / Crossref 的覆盖率有限：约 48% 的中文参考文献会显示「未找到匹配记录」——**导入本地题录库可以把这一比例降到 0**（见上节，20 篇测试中 409/409 可判定），不导入时需要人工核对。
- 摘要覆盖更少，部分条目支持度会显示「未检测」；若命中的是本地题录，导出题录时勾选「摘要/Abstract」再导入，支持度才能判定。
- 支持度判定默认只判前 30 条有摘要且被正文引用的文献（可在上传时选 10/30/80/全部或关闭），未判定的条目会写明原因。
- 扫描件可自动 OCR（可选依赖 `rapidocr-onnxruntime`）；OCR 会偶发字符错误（例如把 `[J]` 识别成 `[]`），此类条目会保留题目/来源但标注「类型码丢失」，请人工核对。
- 两栏排版、复杂表格版式仍可能影响抽取（已按页面中线做两栏切分，但非通用版面分析）。
- 英文 APA 式参考文献里，题名本身含 `(2017).` 这类年份样式时，极少数条目会把作者行归到上一条（22 篇语料 529 条 PDF 抽取结果中 1 条）；网页型引文（`机构. 题名. 链接`）已按 `EB` 类型解析、机构作者整体保留、链接不再混入题名。
- 作者比对已改为按姓氏（`Yu, H.` ↔ `Hui Yu`），机构作者、拼音/中文别名、同名不同人仍可能造成少量误判；题名一致但作者完全不同的记录可能是书评，报告会提示人工核对。
- 支持度判定为辅助提示，不构成学术结论。
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
