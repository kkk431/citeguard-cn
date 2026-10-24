# 第三方资源清单（THIRD_PARTY_NOTICES）

> 本表按 **实际集成情况** 分三组：① 交付系统中实际运行的开源依赖；② 第三方服务（非开源）；③ 候选/预留资源（本期未集成，仅作为可替换后端的设计依据）。
> 版本以 `requirements.lock.txt`（锁定的实际运行版本）为准；许可证链接为官方来源。许可证一律以英文原名为准。

## 1. 实际集成并随作品分发的开源组件

| 组件 | 版本 | 许可证 | 用途 | 是否修改 | 分发方式 | 来源 |
|---|---|---|---|---|---|---|
| FastAPI | 0.159.1 | MIT | Web 后端路由 | 否 | pip 依赖 | https://github.com/fastapi/fastapi |
| Starlette | 1.9.0 | BSD-3-Clause | FastAPI 的 ASGI 基础（间接依赖） | 否 | pip 依赖 | https://github.com/encode/starlette |
| Uvicorn | 0.54.0 | BSD-3-Clause | ASGI 服务器 | 否 | pip 依赖 | https://github.com/encode/uvicorn |
| Jinja2 | 3.1.6 | BSD-3-Clause | 服务端模板渲染 | 否 | pip 依赖 | https://github.com/pallets/jinja |
| MarkupSafe | 3.0.4 | BSD-3-Clause | Jinja2 间接依赖 | 否 | pip 依赖 | https://github.com/pallets/markupsafe |
| python-multipart | 0.0.32 | Apache-2.0 | 文件上传解析 | 否 | pip 依赖 | https://github.com/Kludex/python-multipart |
| requests | 2.34.2 | Apache-2.0 | 调用 OpenAlex / Crossref / 可选 LLM 接口 | 否 | pip 依赖 | https://github.com/psf/requests |
| urllib3 / certifi / charset-normalizer | 2.8.0 / 2026.10.19 / 3.5.2 | MIT / MPL-2.0 / MIT | requests 间接依赖 | 否 | pip 依赖 | 见各自 PyPI 页 |
| pydantic | 2.14.1 | MIT | 请求/响应模型校验 | 否 | pip 依赖 | https://github.com/pydantic/pydantic |
| rapidfuzz | 3.14.6 | MIT | 题名相似度（评测集构建脚本与核验层） | 否 | pip 依赖 | https://github.com/rapidfuzz/RapidFuzz |
| pdfplumber / pdfminer.six | 0.11.10 / 20260107 | MIT | PDF 文本抽取（主路径） | 否 | pip 依赖 | https://github.com/jsvine/pdfplumber |
| pypdf | 6.21.2 | BSD-3-Clause | PDF 文本抽取（回退路径） | 否 | pip 依赖 | https://github.com/py-pdf/pypdf |
| pypdfium2 | 5.14.0 | BSD-3-Clause / Apache-2.0（含 PDFium） | pdfplumber 的渲染后端（间接依赖） | 否 | pip 依赖 | https://github.com/pypdfium2-team/pypdfium2 |
| Pillow | 12.3.0 | MIT-CMU | 图片处理（间接依赖） | 否 | pip 依赖 | https://github.com/python-pillow/Pillow |

上述组件均以**未修改的库**形式被 import，不复制其源码；分发的是本作品源码 + pip 依赖声明，符合各许可证的保留声明与许可副本要求（见 §5）。

## 2. 实际调用的第三方服务（非开源）

| 服务 | 用途 | 是否必需 | 数据边界 | 说明 |
|---|---|---|---|---|
| OpenAlex API | 文献元数据（题名/作者/年/卷期/页码/摘要/DOI） | 真实性核验必需 | 仅发送引文题名或 DOI 查询；不发送论文全文 | 元数据 CC0 1.0；遵守 polite pool（`mailto`）与速率限制 |
| Crossref REST API | DOI 元数据 | 可选（DOI 回退） | 仅发送 DOI | 元数据开放；摘要版权归各出版商，不转存全文 |
| arXiv API / 元数据 | 预印本元数据 | 可选 | 仅发送 DOI/arXiv ID | 元数据 CC0 1.0 |
| DeepSeek API | 引用支持度 LLM judge | **可选**（未设 `DEEPSEEK_API_KEY` 时自动降级为「未检测」） | 发送引用句 + 被引论文摘要（≤1800 字），不发送论文正文 | 闭源商业 API，按服务条款使用；**不参与**真实性判定与格式合规判定；密钥只经环境变量注入，不写入仓库 |

> 说明：本作品的「AI 判定」部分（引用支持度）通过 **OpenAI 兼容的 `/chat/completions` 接口**调用，接口地址、模型名与 key 均可配置（`CITEGUARD_JUDGE_BASE_URL` / `CITEGUARD_JUDGE_MODEL` / `CITEGUARD_JUDGE_API_KEY`，未设置时回退 `DEEPSEEK_*`）。因此可切换到本地开源推理后端（vLLM / Ollama / llama.cpp 部署的 Qwen3 等）。评测中统一使用 DeepSeek（temperature 0）以保证与基线可比；另有本地开源模型实测脚本 `scripts/eval_support_local.py`，证明该后端可完全离线运行（结果见 `data/experiments/`）。

**可选扩展（默认不安装）**：

| 组件 | 版本 | 许可证 | 用途 | 使用方式 | 来源 |
|---|---|---|---|---|---|
| rapidocr-onnxruntime | ≥1.3 | Apache-2.0（含 PP-OCR ONNX 模型，Apache-2.0） | 扫描件 PDF OCR 兜底 | 可选依赖 `requirements-ocr.txt`；未装时扫描件给出提示 | https://github.com/RapidAI/RapidOCR |

## 3. 候选/预留资源（本期**未集成、未分发**）

| 资源 | 版本 | 许可证 | 原计划用途 | 本期状态 | 来源 |
|---|---|---|---|---|---|
| Qwen3-8B | 8B | Apache-2.0 | 本地开源 judge 后端（替换 §2 DeepSeek） | 接口已兼容；**Qwen3-1.7B 已在 CPU 离线跑通（见 §4.2）**；8B 建议 GPU，未在本机实测 | https://huggingface.co/Qwen/Qwen3-8B |
| Qwen3-Embedding-0.6B | 0.6B | Apache-2.0 | 题名/摘要检索嵌入 | 未集成（当前用题名检索 + DOI 锚点） | https://huggingface.co/Qwen/Qwen3-Embedding-0.6B |
| Qwen3-Reranker-0.6B | 0.6B | Apache-2.0 | 证据重排 | 未集成 | https://huggingface.co/Qwen/Qwen3-Reranker-0.6B |
| bge-m3 | — | MIT | 多语嵌入 | 未集成 | https://huggingface.co/BAAI/bge-m3 |
| Docling | — | MIT | PDF 结构化解 | 未集成 | https://github.com/docling-project/docling |

> 以上资源均只用作**选型论证与路线图**，不计入「已使用开源模型」得分项；已实测的部分见 §4.1。

## 4. 数据

| 数据 | 许可证 | 用途 | 是否再分发 | 来源 |
|---|---|---|---|---|
| OpenAlex 元数据 | CC0 1.0 | 真实性核验 + 构建 CiteBench-CN / ClaimSupport-CN 的元数据来源 | 不再分发原始 dump；仅存 ID 与自建标签 | https://docs.openalex.org |
| Crossref 元数据 | 元数据开放；摘要版权归出版商 | DOI 核验 | 不转存摘要全文 | https://www.crossref.org/documentation/retrieve-metadata/rest-api/ |
| arXiv 元数据 | CC0 1.0 | 预印本核验 | 不转存全文 | https://info.arxiv.org/help/api/tou.html |
| **CiteBench-CN**（自建） | **CC-BY-4.0** | 中文引文真实性评测集，250 条 | 随仓库分发（仅 ID + 自建扰动 + 标签） | `data/citebench_cn/` |
| **ClaimSupport-CN**（自建） | **CC-BY-4.0** | 中文引用支持度评测集，100 条 | 随仓库分发（claim + 短证据片段 + 来源 ID） | `data/claimsupport_cn/` |
| **SciFact**（外部公开数据集） | claims/evidence **CC BY 4.0**；corpus abstracts **ODC-By 1.0**；code Apache-2.0 | 支持度 judge 的**外部英文零样本验证**（Wadden et al., EMNLP 2020） | **不随仓库分发**；只提交评测脚本与结果 JSON | https://github.com/allenai/scifact |

### 4.1 SciFact 外部零样本验证（只评测，不再分发数据）

| 设置 | 输入 | n | Macro-F1 | Accuracy | 说明 |
|---|---|---|---|---|---|
| oracle 证据句 | 标注的证据句（+题名） | 300 | **0.8224** | 0.8267 | 相当于「给定黄金 rationale」的标签预测 |
| 整段摘要 | 被引论文完整摘要 | 300 | **0.7939** | 0.8000 | 更接近产品真实输入（更难） |

- 映射：本产品四分类的 `support`/`partial` → SciFact `SUPPORT`，`contradict` → `CONTRADICT`，`no_evidence` → `NOT_ENOUGH_INFO`；zero-shot，**未在 SciFact 上训练/微调**，因此与 SciFact 微调系统不可直接比较。
- 复现：下载 `https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz` → 解压到 `data/experiments/scifact_raw/`（git-ignored）→ `DEEPSEEK_API_KEY=... PYTHONPATH=src python scripts/eval_support_scifact.py`。

### 4.2 本地开源模型离线实测（Qwen2.5-3B/7B、Qwen3-1.7B，Apache-2.0）

产品 judge 走 OpenAI 兼容接口。`scripts/local_judge_server.py` 用 `transformers` 起一个同样的
`/v1/chat/completions` 服务，支持 `--device auto` + `CITEGUARD_LOCAL_MAX_MEMORY` 把 7B 拆到多张卡上
（实测 2×NVIDIA TITAN Xp 12GB，fp16，CUDA 11.4 驱动；3B 单卡即可）。评测脚本、数据、prompt 版本都与
托管模型一致，因此这些数字可直接对比：

| 模型 | 硬件 | Prompt | 条数 | Macro-F1 | Accuracy | 速度 |
|---|---|---|---|---|---|---|
| Qwen3-1.7B | CPU | 产品长 prompt | 20 | 0.5060 | 0.55 | ~93 s/条 |
| Qwen3-1.7B | CPU | 精简 prompt | 20 | **0.7059** | 0.75 | ~46 s/条 |
| Qwen2.5-3B-Instruct | 1×TITAN Xp | 产品长 prompt | 100 | 0.3894 | 0.40 | 5.9 s/条（2 workers） |
| Qwen2.5-3B-Instruct | 1×TITAN Xp | 精简 prompt | 100 | **0.6291** | 0.68 | — |
| Qwen2.5-7B-Instruct | 2×TITAN Xp | 产品长 prompt（含覆盖审计） | 100 | **0.7181** | 0.66 | 8.5 s/条（2 workers） |
| Qwen2.5-7B-Instruct | 2×TITAN Xp | 精简 prompt | 100 | 0.7022 | 0.73 | — |

- 产品长 prompt 是为强托管模型调优的：3B 跟不动（0.3894），换精简 prompt 后升到 0.6291；7B 已能执行两段式判定，
  产品路径 0.7181，反而略高于精简 prompt 的 0.7022（差 0.016，在 100 条样本上不宜过度解读）。
- 与托管 DeepSeek 的 0.9328 仍有明显差距——**离线可跑通 ≠ 质量相同**。但整条链路（题录解析 → 核验 → 支持度判定）
  可以完全离线，接口、缓存、评测脚本与线上一致，这是「AI 部分开源可替换」的可复现证据。
- 7B 用产品 prompt 跑 100 条耗时 847.6 s（两段式、2 workers）；3B 591.5 s。硬件是 2017 年的 TITAN Xp，
  换成 24GB 级新卡或 4-bit 量化可进一步提速/放大模型。
- 复现（服务器示例）：
  ```bash
  python scripts/local_judge_server.py --model /path/Qwen2.5-7B-Instruct \
    --device auto --dtype float16 --port 8099
  CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8099/v1 \
  CITEGUARD_JUDGE_MODEL=Qwen2.5-7B-Instruct CITEGUARD_JUDGE_API_KEY=local \
  PYTHONPATH=src python scripts/evaluate_support.py --limit 100 \
    --out data/experiments/support_local_qwen25_7b_gpu.json
  ```
- 证据文件：`data/experiments/support_local_qwen25_{3b,7b}_{gpu,simple}.json`（含 confusion / per-class / prompt hash）。
  小模型换精简 prompt 时，产品侧可设 `CITEGUARD_SUPPORT_PROMPT_FILE=scripts/support_prompt_simple.txt`
  （自定义 prompt 自动使用独立缓存命名空间），并建议 `CITEGUARD_SUPPORT_AUDIT=0`。
- 尚未实测 Qwen3-8B / 14B：8B 需要更大显存或量化；接口已经兼容，后续换模型只需改 `--model` 与环境变量。

### 4.3 图表结论核验（Qwen2.5-VL-7B-Instruct，Apache-2.0）

产品新增一个可选的「图表 vs 结论」检查：`web/templates/figure.html` + `src/citeguard/figure_check.py` 通过
OpenAI 兼容的 `/v1/chat/completions` 调用视觉模型；`scripts/local_vl_server.py` 用 `transformers` 起服务
（`transformers`、`accelerate`、`qwen-vl-utils` 仅在 GPU 主机安装，不随作品分发）。模型权重从 ModelScope 下载，
不随作品分发；产品主机（CPU）不加载模型，未配置 `CITEGUARD_VL_ENDPOINT` 时此页面只显示说明。

实测（单张 RTX 4090 24GB，bf16，峰值显存 16.0–16.1 GB，首次加载 8.1–8.3 秒；prompt 与产品一致，版本 1）：

| 数据 | 条数 | 准确率 | 支持类 | 矛盾类 | 误报矛盾 | 平均延迟 |
|---|---|---|---|---|---|---|
| 合成控例（20 图，支持/矛盾各 20 条，seed=20261024） | 40 | 0.90 | 17/20 | 19/20 | 0 | 1.55 s |
| 真实论文图表（5 图，支持/矛盾各 5 条） | 10 | 0.90 | 5/5 | 4/5 | 0 | 2.56 s |

- 合成集由 `scripts/make_synth_figtest.py` 生成（柱状图/折线图各 10 张，每图 1 条支持 + 1 条矛盾），标签由构造决定；
  真实图由 `scripts/extract_real_figures.py` 从本地 PDF 截取后人工挑图、人工写结论，规模小，只作方向性证据。
- 另测了一个更严格的 v2 prompt：合成 0.925 但把 2 条支持结论误判为矛盾；真实 1.00。产品选择 v1，优先避免
  「把支持说成矛盾」的误伤；v2 只作为实验记录。细节见 [docs/figure_check.md](docs/figure_check.md)。
- 证据：`data/experiments/` 下的 VL 结果不随公开仓库分发（图片来自本地真实语料，不便于再分发）；评测脚本公开，
  合成集可一键重建。真实语料上的图表截图只保存在评测机本机目录。

## 5. 许可证义务与履行方式

| 许可证 | 主要义务 | 本作品如何履行 |
|---|---|---|
| Apache-2.0（本作品代码） | 提供许可证副本、保留 NOTICE、修改文件标注 | 根目录 `LICENSE` + `NOTICE` + 文件头注释 |
| Apache-2.0（第三方库） | 保留版权与许可声明 | 不改源码、以 pip 依赖引入；本表列出出处与许可 |
| MIT / BSD | 保留版权与许可声明 | 同上 |
| CC0 1.0 | 无强制义务 | 主动标明数据来源（OpenAlex / arXiv） |
| CC-BY-4.0（自建数据集） | 署名、标明修改、不附加额外限制 | 数据卡写清来源 ID、构造方法与修改说明 |
| 闭源 API 条款（DeepSeek） | 遵守服务条款、不泄露密钥 | 密钥仅环境变量注入；仓库中只有 `.env.example` 占位符 |

## 6. 明确排除的资源（为避免许可风险）

- **KeSpeech**（禁止再分发）、**OBI-Bench**（无 LICENSE）、**古联杯**数据（不可公开）、教材/课件 PDF、知网/万方全文——均未使用。
- **Food-101**（无明确许可）、**iNaturalist / FUNSD / XFUND / CTW**（仅研究或 NC）——均未纳入。
- **PyMuPDF / AGPL 组件 / ultralytics YOLO（AGPL）**——未引入，避免 AGPL 传染性义务。

## 7. 上游开源贡献

| 项目 | 形式 | 内容 | 链接 |
|---|---|---|---|
| RefChecker（MIT） | Pull Request #77 | 修复 BibTeX 裸值（`year = 2017`）被丢弃导致年份校验失效的问题，含 10 条回归测试 | https://github.com/markrussinovich/refchecker/pull/77 |

## 8. 自研边界（不属于第三方资源）

`src/citeguard/` 下全部模块为自研：中文引文解析器、元数据核验与三分类判定、GB/T 7714-2025 规则引擎、引用支持度编排、报告与 Web 工作台、评测脚本与两套数据集构造脚本。第三方资源只承担「元数据来源」「PDF 文本抽取」「HTTP/Web 框架」三类基础能力。
