# 第三方依赖 / 数据 / 模型许可证清单

本项目代码以 **Apache-2.0** 发布（见仓库 `LICENSE`）。下面列出随产品分发、或用于评测/训练/文档的第三方组件、数据与模型。

规则：

1. 核心分发（`requirements.txt`、Docker 镜像）不得包含 **AGPL / GPL** 依赖；
2. 可选能力放在独立 requirements 文件中，并在本页写明边界；
3. 数据与模型只记录许可，不把无权再分发的内容打包进仓库或镜像。

## 核心运行时（随 Docker 分发）

| 组件 | 版本约束 | 许可证 | 用途 |
|---|---|---|---|
| requests | >=2.31 | Apache-2.0 | HTTP 客户端 |
| rapidfuzz | >=3.0 | MIT | 标题相似度 |
| pypdf | >=5.0 | BSD-3-Clause | PDF 文本读取 |
| pdfplumber | >=0.11 | MIT | PDF 文本 + 坐标 |
| python-docx | >=1.1 | MIT | Word 读写 |
| fastapi | >=0.110 | MIT | Web 框架 |
| uvicorn | >=0.29 | BSD-3-Clause | ASGI 服务器 |
| jinja2 | >=3.1 | BSD-3-Clause | 模板 |
| python-multipart | >=0.0.9 | Apache-2.0 | 表单上传 |

## 可选能力

| 组件 | 文件 | 许可证 | 边界 |
|---|---|---|---|
| rapidocr-onnxruntime | requirements-ocr.txt | Apache-2.0 | 扫描件 OCR；不装也能用，只是不自动识别图片版 PDF |
| pypdfium2 | requirements-ocr.txt | Apache-2.0 / BSD-3-Clause | 页面渲染（图表定位、批注 PDF） |
| numpy | requirements-ocr.txt | BSD-3-Clause | OCR 图像数组 |
| **PyMuPDF (fitz)** | requirements-optional-layout.txt | **AGPL-3.0** | 仅“版面回退”与紧排文本备用解析；核心与 Docker **不安装**，缺失时自动退回 pdfplumber/pypdf |

### 关于 PyMuPDF（重要）

PyMuPDF 是 AGPL-3.0。把它随 Docker 镜像/发行包分发，会触发 AGPL 的传染义务，与本项目 Apache-2.0 冲突。

处置：

- 从 `requirements.txt` 移除，`Dockerfile` 因此不再安装；
- 代码中均为**函数内延迟导入**，缺失时 `_pdf_pymupdf()` / `extract_reference_entries()` 返回空，自动使用 pdfplumber / 悬挂缩进；
- 需要更强版面能力时，用户可自行 `pip install -r requirements-optional-layout.txt`，此时 PyMuPDF 由用户本地安装、不随本项目分发；
- Phase 3 计划用 `pypdfium2` 重写 `refs_layout`，彻底去掉 PyMuPDF。

## 评测 / 训练 / 脚本（不随运行时打包）

| 组件 | 许可证 | 用途 |
|---|---|---|
| torch | BSD-3-Clause | LoRA 训练/推理 |
| transformers | Apache-2.0 | Qwen 加载 |
| peft | Apache-2.0 | LoRA |
| datasets / accelerate | Apache-2.0 | 数据处理 |
| sentencepiece | Apache-2.0 | 分词 |
| matplotlib | PSF-based (BSD 兼容) | 图表生成（脚本） |

## 数据

| 数据 | 许可证 | 说明 |
|---|---|---|
| OpenAlex 元数据 | CC0 | 题录/摘要，不 re-host 全文 |
| Crossref 元数据 | 开放 | DOI 元数据 |
| arXiv 元数据 | 开放 | 预印本元数据 |
| SciFact | CC BY 4.0 | 英文外部评测 |
| CiteBench-CN / ClaimSupport-CN | CC BY 4.0（本项目） | 构造标签，非人审；DATASET_CARD 写明 |
| 真实语料 22 篇（hanspub 等） | 各刊 OA 许可 | 仅本地评测，PDF 不打包、不再分发 |
| CNKI 导出题录（cnki_demo.enw） | 用户机构订阅 | 仅本地示例，不进开源仓库 |

## 模型

| 模型 | 许可证 | 用途 |
|---|---|---|
| Qwen3-14B / Qwen3-8B / Qwen3-1.7B | Apache-2.0 | 支持度 judge、LoRA 基座 |
| Qwen3-VL-8B / Qwen2.5-VL-7B | Apache-2.0 | 图表核验 |
| 自训练 LoRA adapter | Apache-2.0（随项目） | 支持度四分类 |

## 复核方式

```bash
# 核心依赖不得含 pymupdf（AGPL）
python -m pytest tests/test_licenses.py -q
# 全量测试
PYTHONPATH=src python -m pytest tests -q
```

## Optional Chinese title matching
- `opencc-python-reimplemented` (Apache-2.0) — optional Traditional → Simplified normalization for CJK titles; enabled automatically when installed; not part of the core Docker image.
