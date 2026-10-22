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

> 说明：本作品的「AI 判定」部分（引用支持度）通过 **OpenAI 兼容的 `/chat/completions` 接口**调用，接口地址与模型名均由 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` 配置。因此可无缝切换到本地开源推理后端（如 vLLM / Ollama / llama.cpp 部署的 Qwen3-8B）。评测中统一使用 DeepSeek（temperature 0）以保证与基线可比，本队未在交付系统中绑定任何闭源模型权重。

## 3. 候选/预留资源（本期**未集成、未分发**）

| 资源 | 版本 | 许可证 | 原计划用途 | 本期状态 | 来源 |
|---|---|---|---|---|---|
| Qwen3-8B | 8B | Apache-2.0 | 本地开源 judge 后端（替换 §2 DeepSeek） | 未集成；接口已兼容，缺本地显卡/下载条件 | https://huggingface.co/Qwen/Qwen3-8B |
| Qwen3-Embedding-0.6B | 0.6B | Apache-2.0 | 题名/摘要检索嵌入 | 未集成（当前用题名检索 + DOI 锚点） | https://huggingface.co/Qwen/Qwen3-Embedding-0.6B |
| Qwen3-Reranker-0.6B | 0.6B | Apache-2.0 | 证据重排 | 未集成 | https://huggingface.co/Qwen/Qwen3-Reranker-0.6B |
| bge-m3 | — | MIT | 多语嵌入 | 未集成 | https://huggingface.co/BAAI/bge-m3 |
| PaddleOCR | — | Apache-2.0 | 扫描版 PDF OCR | 未集成（当前仅处理文本层 PDF） | https://github.com/PaddlePaddle/PaddleOCR |
| Docling | — | MIT | PDF 结构化解 | 未集成 | https://github.com/docling-project/docling |

> 以上资源均只用作**选型论证与路线图**，不计入「已使用开源模型」得分项，答辩时按「候选/未集成」表述。

## 4. 数据

| 数据 | 许可证 | 用途 | 是否再分发 | 来源 |
|---|---|---|---|---|
| OpenAlex 元数据 | CC0 1.0 | 真实性核验 + 构建 CiteBench-CN / ClaimSupport-CN 的元数据来源 | 不再分发原始 dump；仅存 ID 与自建标签 | https://docs.openalex.org |
| Crossref 元数据 | 元数据开放；摘要版权归出版商 | DOI 核验 | 不转存摘要全文 | https://www.crossref.org/documentation/retrieve-metadata/rest-api/ |
| arXiv 元数据 | CC0 1.0 | 预印本核验 | 不转存全文 | https://info.arxiv.org/help/api/tou.html |
| **CiteBench-CN**（自建） | **CC-BY-4.0** | 中文引文真实性评测集，250 条 | 随仓库分发（仅 ID + 自建扰动 + 标签） | `data/citebench_cn/` |
| **ClaimSupport-CN**（自建） | **CC-BY-4.0** | 中文引用支持度评测集，100 条 | 随仓库分发（claim + 短证据片段 + 来源 ID） | `data/claimsupport_cn/` |

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
