# CiteMap evidence-map data

本目录是 CiteMap（证据地图）的数据层，服务任务 B1。**只存放论文元数据、开放获取链接与人工抽取示例，不存放 PDF 全文。**

## 文件

| 路径 | 内容 |
| --- | --- |
| `index.json` | 主题索引：顺序、名称、corpus/extractions 文件指针 |
| `verification.json` | DOI 双通道校验（Crossref + doi.org handle）与许可一致性结果 |
| `corpus/<topic>.json` | 主题 manifest：Topic + 15 篇 Paper（DOI/OpenAlex/URL/license/OA 状态） |
| `extractions/<topic>.json` | 人工示例抽取：Claims + Evidence（stance/quote/method/sample/confidence）+ Gaps |

主题：`ai_education`（人工智能教育）、`medical_imaging`（医学影像 AI），各 15 篇、各 5 条证据，共 10 条人工示例。

## 许可与版权

- 15+15 篇论文均为开放获取，许可为 CC 系列（`cc-by` / `cc-by-nc-nd` / `cc-by-sa` / `cc-by-nc-sa`），无空许可。
- 仓库不提交任何 PDF 全文；`oa_url` 仅指向出版社/arXiv 的开放获取链接。
- `fulltext_available=false` 表示 OpenAlex 未给出可直接下载的 PDF（仅 landing page），不代表论文不开放。
- CC BY-NC-ND / CC BY-NC-SA 材料仅用于非商业研究引用，引用原文时保留出处。

## 复现与校验

```bash
PYTHONPATH=src python -m citeguard.evidence_map --check
PYTHONPATH=src python -m citeguard.evidence_map --topic ai_education
pytest tests/test_evidence_map.py -q
```

> Windows PowerShell：`$env:PYTHONPATH='src'; python -m citeguard.evidence_map --check`。

`verification.json` 由 OpenAlex/Crossref/doi.org 的检索结果生成；重新抓取时请同步更新 `checked_at` 与逐篇记录。

## Schema

字段与不变量见 [`docs/evidence_map.md`](../../docs/evidence_map.md) 与 `src/citeguard/evidence_map.py`。`SCHEMA_VERSION = "1.0"`。
