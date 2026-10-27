# 附件资源清单

本文件对应比赛要求的「附件资源清单」，说明每个提交文件是什么、怎么用、依赖哪些第三方资源。

## 1. 提交文件

| 文件 | 内容 | 大小（约） | 说明 |
| --- | --- | --- | --- |
| `citeguard-cn-<版本>.zip` | 完整源码、测试、文档、评测脚本与证据 JSON | 8–9 MB | 解压即用；不含模型权重、不含原始 PDF 语料、不含密钥 |
| `CiteGuard-CN-技术报告.pdf` | 技术报告正文（≤15 页） | 1–2 MB | 与仓库 `report/build_report.py` 生成的一致 |
| `CiteGuard-CN-答辩.pptx` / `.pdf` | 答辩演示（18 页） | 3–6 MB | 截图均为产品真实页面 |
| `资源清单.md`（本文件） | 文件说明与复现指引 | < 10 KB | — |

演示视频按要求不做。

## 2. 运行环境

- Python 3.10+（开发与验证用 3.11），Windows / Linux 均可。
- 本地演示默认地址 `http://127.0.0.1:8010`；题目解析、GB/T 7714 规则、本地题录库比对可完全离线运行。
- 在线增强（OpenAlex / Crossref / arXiv / 万方 / 大模型判定）需要外网与 API Key，均通过环境变量开启，不写死在代码里。

## 3. 第三方依赖与许可

| 依赖 | 用途 | 许可 |
| --- | --- | --- |
| FastAPI / Uvicorn / Jinja2 / python-multipart | Web 服务与模板 | MIT / BSD |
| pypdfium2 | PDF 渲染（图表定位、OCR） | Apache-2.0 / BSD-3-Clause |
| pypdf | PDF 文本层解析 | BSD-3-Clause |
| python-docx | Word 报告导出 | MIT |
| rapidocr-onnxruntime（可选） | 扫描版 PDF 的 OCR | Apache-2.0 |
| numpy（OCR 可选依赖） | 图像数组转换 | BSD-3-Clause |
| openai（客户端） | 调用 OpenAI 兼容接口 | Apache-2.0 |
| requests | HTTP 访问公开元数据 | Apache-2.0 |

完整清单与版本见 `requirements.txt`、`THIRD_PARTY_NOTICES.md`。

## 4. 数据与模型来源

| 资源 | 用途 | 许可/获取方式 |
| --- | --- | --- |
| CiteBench-CN | 中文引文核验评测（250 条，自建） | 随仓库提供，CC BY 4.0 |
| ClaimSupport-CN | 引用支持度评测（100 条，自建） | 随仓库提供，CC BY 4.0 |
| 真实中文论文语料（22 篇 / 409 条） | 真实场景评测 | 只保留抽取后的题录与证据 JSON，不随包分发原文 |
| SciFact | 英文支持度外部零样本评测 | 按原项目许可下载，不随包分发 |
| ChartCheck | 图表事实核查外部评测 | 按原项目许可下载，不随包分发 |
| OpenAlex / Crossref / arXiv / DataCite / 万方开放平台 | 在线元数据核验 | 公开 API，遵守各自条款 |
| Qwen3-14B / Qwen3-VL-8B / DeepSeek API | 支持度判定、图表判定、中英扩写 | 本地权重不入包；API Key 不入包 |

## 5. 复现入口

```bash
# 1) 解压后安装依赖
pip install -r requirements.txt

# 2) 启动本地演示（离线可跑）
python -m uvicorn web.app:app --host 127.0.0.1 --port 8010

# 3) 复现评测（可选，需要对应数据）
python scripts/benchmark_citebench.py
python scripts/eval_support_local.py --help
python scripts/verify_artifacts.py
```

评测数字的出处见 `docs/experiments.md` 与 `data/experiments/*.json`；答辩口径见 `docs/ppt_numbers.md`。
