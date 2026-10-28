# P0/P1 优化项状态矩阵（诚实版）

> 目的：每一项都写清楚「做了什么、证据在哪、还差什么」。不把“做了代码”写成“能力已达标”。
> 最后更新：2026-10-28，产品版本 0.9.50。

| 项 | 状态 | 证据 | 还差什么 |
| --- | --- | --- | --- |
| ① 图表核验接通视觉服务并并入主报告 | **已完成** | 0.9.38 主线接入（`pipeline._body_figure_claims`，最多 3 图 × 2 条结论）；0.9.39 图注边界修复；E2E 任务 `hanspub_152575`：21.2 s（7B）/ 14.4 s（8B），3 组结论，图 1 支持 + 信息不足、图 2 两条支持、图 3 支持 + 信息不足；报告页有「正文图表结论抽检」区块 | 2026-10-28 网络恢复后已复测：Qwen3-VL-8B（lmh:8095）14.4 s、3 张图各 1 条结论、全部 supported，页面 3/4/5 自动定位正确 |
| ② 中文演示兜底（预置题录/缓存/预热） | **已完成** | 0.9.27 离线模式（`CITEGUARD_OFFLINE=1`，报告标 Unknown）；0.9.42 `POST /api/library/demo` 一键载入 10 条开放文献；离线演示包 `samples/offline_demo/` 实测 11 条里 10 条 Exact、1 条刻意标注的未核实 | 跨任务 HTTP 缓存是持久化的，但没有做“预热脚本”；断网时视觉/在线核验不可用属于设计边界 |
| ③ 长文档进度细化与解析提速 | **部分完成** | 进度有「多源核验 i/n + ETA」；0.9.44 跳过多余第二提取器（0.04–0.31 s/篇）；0.9.48/0.9.49 源熔断 + 重试预算（3 次、8 s 上限、长 Retry-After 快速失败）；BERT 54 条：暖缓存 20.5 s → 2.4 s，冷缓存 169.2 s → 39.4 s（后者网络状态不同，且有 22 条 Unknown） | 冷启动仍受免费源配额约束；没有做多进程/多 worker 的解析并行 |
| ④ 补 BibTeX / CSL-JSON 导出 | **已完成** | 0.9.37 导出端点 `format=bibtex|csl`；本次 E2E：BibTeX 200、4,047 bytes；CSL 200、7,336 bytes；证据包 ZIP 同时含 `report.bib` / `report.csl.json` | 无 |
| ⑤ 解析版面增强降低真实论文 Unverified | **部分完成** | 0.9.45/0.9.46/0.9.47：作者-年合并、无括号年份切分、尾部作者行移动、作者列表题名清空；真实 BERT：Unverified 7 → 5（另 2 条 Unknown 为源限流），不再出现「题名 = 作者列表」；22 篇真实语料全量解析：**498 条，题名为空 3 条（0.6%，集中在 1 篇双栏论文的两条粘连文献）**（`data/experiments/parse_corpus_titles.json`） | 残留 3 条空题名（PDF 把两条文献粘成一条），未做强制切分以免误伤；英文语料仍以作者-年格式为主，与中文著录格式的覆盖不同 |
| ⑥ 图表多候选页投票、表格提示、扩真实图表集 | **部分完成** | `find_figure_pages` 收集全部候选页；`find_figure_page(claim=...)` 按图注-结论词重合度选页、页码作平手裁决；表格提示走 `kind="table"`（`图注/表注` 分流）；0.9.51 过滤图注自身被当成结论（`_CAPTION_LINE_RE`）；真实图集 13 图/26 条，8B 分步 v3 0.885 | 「扩真实图表集」需要网络 + 视觉服务重新标注，今天做不了；13 图仍是小样本 |
| ⑦ 多源投票参与状态判定 | **已完成** | 0.9.41 `_version_sources`：同题名 ≥0.95 且年份一致的另一来源命中时，从 mismatches 移除 year 并注记「预印本/会议版本差异」；单测覆盖；真实 BERT 的 Minor 主要来自会议/预印本版本差异 | 投票只解决“年份版本差异”，不改变作者/题名不一致的判定 |
| ⑧ 中文支持度样本扩充 | **已完成（构造扩展集）** | 0.9.52 新增 ClaimSupport-CN-Ext 60 条，source work 与原 100 条完全不重叠（24 support / 15 partial / 12 contradict / 9 no_evidence；`scripts/build_claimsupport_ext.py`，sha256 `8015a2e8…`）；v10 产品 judge：macro-F1 **0.9866**、acc **0.9833**，仅 1 条 support→partial | 这是程序化构造集、不是人工标注；原 100 条 **0.9597** 仍是主口径，不能把 0.9866 说成“真实场景 98.7%” | `data/claimsupport_cn/claimsupport_cn_ext.jsonl`；`data/experiments/ext60.json` |

## 本次端到端冒烟（2026-10-28，本地 0.9.50）

- 上传 `samples/offline_demo/paper.txt`（11 条）：**Exact 10 / Unknown 1**，平均合规 86.7，风险指数 0.0，本地库命中 10。
- 导出：RIS 200（6,314 B）、EndNote 200（3,244 B）、BibTeX 200（4,047 B）、CSL 200（7,336 B）。
- 证据包 `/api/report/{id}/bundle` 200（25,516 B），ZIP 内 9 个文件：`manifest.json`、`report.{json,html,md,refs.txt,ris,enw,bib,csl.json}`。
- 题录库演示接口：`imported 10 / added 0 / count 20 / with_abstract 8`（幂等）。
- 未配置视觉服务时 `/api/figure-check` 返回 **503 not_configured**，不假装成功。
- 报告页数据源横幅：`source_health={"degraded":{"openalex":3598},"errors":2}`，页面显示「OpenAlex 冷却 3598 秒，2 次请求失败；因此有 1 条结果标为「无法核验」」。

## 口径提醒

- 冷/暖缓存两组数字不是同一网络状态，**不能**对外说“提速 8 倍”；只能说“限流时不再逐条重试、状态如实标 Unknown”。
- 图表 0.96 是自建 50 条中文图上的数字；公开 ChartCheck 200 条是 0.795/0.794，两者不能混用。
- 真实论文上的承诺是「没有把真实文献误判为虚构」（Major 0），不是「所有引用都能自动找到」。
