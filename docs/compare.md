# 多篇文献对比（模块 A）

写综述时，研究者要在十几篇论文之间反复翻找「研究问题、方法、样本、结论、局限、贡献」。
本模块把这个过程压缩成一次上传：**一次读 2–6 篇，抽成一张六维对比矩阵**，可导出 Markdown / CSV。

它属于「读懂文献」而非「核验引文」：字段由模型从每篇论文按章节抽取的节选（摘要/引言/方法/结果/讨论/结论）抽取，
报告页与导出文件都会标注 *机器抽取、引用前须回原文核对*。它不判断论文真假，也不替代真实性核验。

## 怎么用

网页入口：`/compare`（导航「文献对比」）。

```bash
# 命令行直接调用核心模块（与网页同一条代码路径）
cd citeguard/
PYTHONPATH=src DEEPSEEK_API_KEY=sk-... python - <<'PY'
from citeguard import compare
from citeguard.pdf_extract import extract_text
papers = [("论文甲", extract_text("data/real_corpus/hanspub_152699.pdf")),
          ("论文乙", extract_text("data/real_corpus/hanspub_152703.pdf"))]
result = compare.compare_texts(papers)
print(compare.render_markdown(result))
PY
```

复现实测证据：

```bash
cd citeguard/
PYTHONPATH=src DEEPSEEK_API_KEY=sk-... python scripts/eval_compare_real.py
# 证据写入 data/experiments/compare_real.json
```

## 实测（4 篇真实中文论文，2026-10-24）

- 语料：`data/real_corpus` 中 4 篇文本型 hanspub PDF（教育学、语言学方向），不是合成样例。
- 判官：`deepseek-chat`（`temperature=0`），与产品默认一致；同一条代码路径。
- 结果：**4/4 篇抽取成功，0 报错，总耗时 8.0 秒**（约 1.9–2.1 秒/篇），每篇填出 5–6 个字段。
- 「局限」在 3 篇里为空：这几篇摘要只讲问题、方法、结论，没有写局限。系统按提示词要求留空，而不是编造，
  对应矩阵里显示「未提及」——这是有意为之的保守行为。

抽取示例（原文核对前仅作快速浏览）：

| 论文 | 研究问题 | 方法 / 设计 | 主要结论 |
| --- | --- | --- | --- |
| hanspub_152678 | 知识生产模式 III 转型下如何重构博士生课程体系 | 以模式 III 为框架的逻辑耦合分析、美国经验剖析 | 美国以超学科整合、情境化教学等回应高阶知识生产需求 |
| hanspub_152699 | 绍兴方言中「上」的语法化阶段、轨迹及历史层次动因 | 历时与共时结合历史语言学与认知语法 | 「上」由实词虚化为后置词，印证「空间>时间>逻辑关系」 |

## 实现

- `src/citeguard/compare.py`：六字段抽取、截断参考文献、缓存、矩阵/CSV/Markdown 渲染。
- `web/app.py`：`GET /compare` 页面；`POST /api/compare` 后台任务；`GET /api/compare/{job_id}` 轮询；
  `GET /api/compare/{job_id}/export?format=md|csv` 导出。
- `web/templates/compare.html`、`web/static/js/compare.js`：上传、轮询、矩阵渲染、导出链接。
- 判官复用产品统一配置：默认 `DEEPSEEK_API_KEY`，或 `CITEGUARD_JUDGE_BASE_URL` / `_MODEL` / `_API_KEY`
  指向本地 OpenAI 兼容服务（Ollama / vLLM / LM Studio）；未配置时页面只展示、不可提交。

## 边界（必须一起说）

- **仍是节选**：按章节标题切分后最多约 6000 字，且 PDF 标题不规范时退化为「截前 3600 字」；不全读方法与实验章节，因此「样本量、具体指标」可能缺失。
- **抽取不是核验**：字段可能不完整或概括偏差；写入综述前必须回原文核对，尤其是数字与因果表述。
- **不做跨文献综合**：它只负责把每篇的字段并排，不生成「研究空白」结论——那需要人写。
- **不构成准确性评测**：当前证据是 4 篇真实论文的工程实测（成功率和耗时），不是标注集上的字段准确率。
- 上传文件与结果仅在本机处理；判官请求会发到所配置的服务（默认 DeepSeek API），文本不会用于训练（按服务方条款）。
- 单次 2–6 篇；扫描版 PDF 需先走 OCR（产品内的 OCR 回退可用）。
