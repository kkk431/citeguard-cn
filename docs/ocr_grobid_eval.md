# OCR / GROBID 对照评测（只评测，不接入产品）

日期：2026-11-11　版本：0.9.99

## 1. OCR 后端对照

方法：取 `data/real_corpus/hanspub_152575.pdf` 第 3 页，pdfium 200 dpi 渲染；加轻微模糊（GaussianBlur 0.6）与高斯噪声（σ=6，seed 20261111）模拟扫描；以该页数字文字层为真值，比较去空白后的字符错误率 CER。

| 后端 | 耗时 | 识别字符数 | CER | 结论 |
|---|---|---|---|---|
| rapidocr-onnxruntime（产品可选 OCR） | **10.3 s** | 1017 | 0.1825 | 保留为可选 OCR 默认 |
| PaddleOCR 3.7 + paddlepaddle 3.3（仅评测） | 109.3 s | 1135 | **0.1530** | 质量略好，但 CPU 慢 10.6×，不接入 |

边界：单页、单篇中文论文、由数字 PDF 渲染的“干净扫描”；不代表真实手机拍照/倾斜/低分辨率；CER 是字符级，不等于引用字段正确率。PaddleOCR 未加入依赖（仅本机评测环境）。

## 2. GROBID 对照（未完成，如实记录）

- 本地 Docker 拉取 `grobid/grobid:0.8.1` 失败：`failed to copy: failed to send write: ... read-only file system`（Docker Desktop containerd 存储只读）。
- 公共演示服务 `https://cloud.science-miner.com/grobid/api/processReferences` 请求返回 HTTP 000（不可达）。
- 因此本轮**没有** GROBID 的参考文献抽取数字，不写“对照结论”。

复现脚本：`scripts/eval_ocr_backends.py`；原始结果：`data/experiments/ocr_backends_eval.json`。
