# OCR / GROBID 对照评测（只评测，不接入产品）

日期：2026-11-11　版本：0.9.99

## 1. OCR 后端对照

方法：取 `data/real_corpus/hanspub_152575.pdf` 第 3 页，pdfium 200 dpi 渲染；加轻微模糊（GaussianBlur 0.6）与高斯噪声（σ=6，seed 20261111）模拟扫描；以该页数字文字层为真值，比较去空白后的字符错误率 CER。

| 后端 | 耗时 | 识别字符数 | CER | 结论 |
|---|---|---|---|---|
| rapidocr-onnxruntime（产品可选 OCR） | **10.3 s** | 1017 | 0.1825 | 保留为可选 OCR 默认 |
| PaddleOCR 3.7 + paddlepaddle 3.3（仅评测） | 109.3 s | 1135 | **0.1530** | 质量略好，但 CPU 慢 10.6×，不接入 |

边界：单页、单篇中文论文、由数字 PDF 渲染的“干净扫描”；不代表真实手机拍照/倾斜/低分辨率；CER 是字符级，不等于引用字段正确率。PaddleOCR 未加入依赖（仅本机评测环境）。

## 2. GROBID 对照（2026-11-12 完成）

环境修复：把 Docker 数据盘从 C: 迁到 D:（junction，镜像未丢）后，`docker pull
grobid/grobid:0.8.1` 成功；容器 `-p 8070:8070` 启动约 50 s 后就绪。对第五次盲测的
三篇 PDF 跑 `POST /api/processReferences`，统计 `<biblStruct>` 条数，与本项目**版面路径**
的条目数对照（不是字段级正确率）：

| 论文 | GROBID 条数 | 本项目（版面路径） | 差值 |
|---|---|---|---|
| Qwen3 (2505.09388) | 74 | 73 | +1 |
| DeepSeek-R1 (2501.12948) | 90 | 92 | −2 |
| Mixtral (2401.04088) | **35** | 27 | **−8** |

结论（只说数据能支撑的）：

- 两套解析器在同一批 PDF 上条数接近；GROBID 在 Mixtral 上比我们的版面路径多出 8 条，
  说明我们的版面切分在该 PDF 上确实漏条目（文本路径此前也得到 35 条）。
- 条数不等价于质量：GROBID 可能把脚注/附录条目算进来，我们的路径也可能多切；本轮
  **没有**做字段级（作者/题名/年份）对照，因此不能写“我们比 GROBID 更准”。
- 未计时（本轮只比条数）；GROBID 作为外部服务需要额外容器与内存，本轮不接入产品。

复现：`docker run -d --rm --name cg-grobid -p 8070:8070 grobid/grobid:0.8.1` 后运行
`python scripts/eval_grobid.py`；原始结果 `data/experiments/grobid_eval.json`。

复现脚本：`scripts/eval_ocr_backends.py`；原始结果：`data/experiments/ocr_backends_eval.json`。
