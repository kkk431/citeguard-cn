# 第三方资源清单（THIRD_PARTY_NOTICES）

> 版本以仓库锁定为准；许可证链接为官方来源。提交前请按实际使用的版本更新本表。

## 代码与框架

| 组件 | 版本 | 许可证 | 用途 | 来源 |
|---|---|---|---|---|
| FastAPI | >=0.110 | MIT | Web 后端 | https://github.com/fastapi/fastapi |
| Uvicorn | >=0.29 | BSD-3-Clause | ASGI 服务器 | https://github.com/encode/uvicorn |
| Jinja2 | >=3.1 | BSD-3-Clause | 模板渲染 | https://github.com/pallets/jinja |
| python-multipart | >=0.0.9 | Apache-2.0 | 文件上传 | https://github.com/Kludex/python-multipart |
| requests | >=2.31 | Apache-2.0 | HTTP 客户端 | https://github.com/psf/requests |
| rapidfuzz | >=3.0 | MIT | 字符串相似度 | https://github.com/rapidfuzz/RapidFuzz |
| pdfplumber | >=0.11 | MIT | PDF 文本抽取 | https://github.com/jsvine/pdfplumber |
| pypdf | >=5.0 | BSD-3-Clause | PDF 文本抽取（回退） | https://github.com/py-pdf/pypdf |

## 模型

| 模型 | 版本 | 许可证 | 用途 | 来源 |
|---|---|---|---|---|
| Qwen3-8B | 8B | Apache-2.0 | 主判定 / 生成（可选） | https://huggingface.co/Qwen/Qwen3-8B |
| Qwen3-Embedding-0.6B | 0.6B | Apache-2.0 | 检索嵌入（可选） | https://huggingface.co/Qwen/Qwen3-Embedding-0.6B |
| Qwen3-Reranker-0.6B | 0.6B | Apache-2.0 | 证据重排（可选） | https://huggingface.co/Qwen/Qwen3-Reranker-0.6B |
| bge-m3 | — | MIT | 多语嵌入（可选） | https://huggingface.co/BAAI/bge-m3 |
| PaddleOCR | — | Apache-2.0 | 扫描件 OCR（可选） | https://github.com/PaddlePaddle/PaddleOCR |
| Docling | — | MIT | PDF 结构化解析（可选） | https://github.com/docling-project/docling |

## 数据

| 数据 | 许可证 | 用途 | 来源 |
|---|---|---|---|
| OpenAlex | CC0 1.0 | 文献元数据核验 | https://docs.openalex.org |
| arXiv 元数据 | CC0 1.0 | 预印本元数据 | https://info.arxiv.org/help/api/tou.html |
| Crossref | 元数据开放；摘要版权归出版商 | DOI 核验 | https://www.crossref.org/documentation/retrieve-metadata/rest-api/ |
| CiteBench-CN | CC-BY-4.0 | 中文引文核验评测集（自建） | `data/citebench_cn/` |

## 第三方服务（非开源依赖）

| 服务 | 用途 | 说明 |
|---|---|---|
| DeepSeek API | 引用支持度 LLM judge（可选） | 仅在设置 `DEEPSEEK_API_KEY` 时启用；不参与真实性/格式核验；按服务条款使用，不提交 key |

## 许可证义务摘要

- Apache-2.0：保留版权与许可副本、保留 NOTICE、修改文件需声明；含专利授权。
- MIT / BSD：保留版权与许可声明。
- CC0：无强制义务，建议署名。
- CC-BY-4.0：署名 + 标明修改 + 不附加额外限制。
- CC-BY-NC / ND：非商业 / 禁止演绎——本项目不使用此类数据作为可再分发成果。

## 未使用的资源（明确排除）

- KeSpeech（禁止分发）、OBI-Bench（无 LICENSE）、古联杯数据（不可公开）、教材 PDF、知网/万方全文。
- Food-101、iNaturalist、FUNSD、XFUND/CTW（NC 或仅研究）等，未纳入本项目交付物。
