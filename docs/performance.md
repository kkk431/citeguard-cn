# 性能与延迟（实测，不估算）

这页只放本机真实跑出来的墙钟时间，供答辩/评审对照。数字随机器和网络变化，不承诺复现到毫秒。

## 解析 + 核验（元数据缓存热）

命令：`python scripts/benchmark_latency.py <pdf...>`，`verify_workers=4`、关闭 support judge。

| 论文 | 引用条数 | 解析 (s) | 核验 (s) | 合计 (s) |
|---|---|---|---|---|
| BERT (1810.04805v2) | 54 | 7.46 | 0.55 | 8.01 |
| hanspub_152575 | 15 | 1.18 | 0.17 | 1.35 |
| hanspub_152595 | 9 | 1.04 | 0.11 | 1.16 |

说明：
- 这是**缓存热**（`data/cache` 已有此前评测的响应）的核验时间；冷启动要加 1–3 s/条不等，取决于 OpenAlex/Crossref 当时限流情况。
- 解析时间包含 PDF 文本层抽取、参考文献切分、逐条题录解析，不包含 OCR（扫描件另计）。
- 支持度判定（LLM）是单独一段，未计入此表：托管 DeepSeek 约 1–2 s/条，本地 14B 视显存与并发而定。

## 同一文件的解析缓存（新增）

同一个 PDF 重跑（重试、演示、评测）时，文本层抽取结果按内容哈希缓存，二次运行直接命中。

| 文件 | 首次抽取 | 缓存命中 |
|---|---|---|
| BERT (1810.04805v2) | 3.52 s | 0.014 s |

- 缓存放 `data/cache/text/`，可用 `CITEGUARD_TEXT_CACHE_DIR` 改位置、`CITEGUARD_TEXT_CACHE=0` 关闭；
  `data/cache/` 已在 `.gitignore`，不会把 PDF 文本带进仓库。
- 只缓存文本层，不含 OCR 结果与核验响应；改提取器后清理目录即可。

## 已经做过的优化

- 相同引用（归一化题名 + 年份 + DOI）只查一次，结果按原顺序回填；
- 核验线程池默认 4，可用 `CITEGUARD_VERIFY_WORKERS` 调整；
- HTTP 响应落盘缓存，评测/演示重复运行不重复请求；
- PDF 文本层正常时跳过多余的第二提取器（长文档解析明显变快）；
- 扫描件才走 OCR，OCR 依赖是可选安装；
- PDF 文本层按内容哈希缓存，同一文件二次解析从 3.5 s 降到 0.01 s。

## 复现

```bash
PYTHONPATH=src python scripts/benchmark_latency.py data/real_corpus/arxiv/1810.04805v2.pdf
```

结果写 `data/experiments/latency_bench.json`。

## 1000 条引用压力测试（离线，2026-11-11）

命令：

```bash
CITEGUARD_OFFLINE=1 PYTHONPATH=src python scripts/stress_1000.py --refs 1000
```

合成 1000 条 GB/T 风格题录（中英文混合、8 种类型轮换，86,263 字符），只测**解析 / 格式校验 / 报告生成**，关闭联网核验（因此状态全为 Unknown）。

| 指标 | 数值 |
|---|---|
| 解析 1000 条 | 0.118 s |
| 完整分析（冷，进程内首次） | 0.718 s |
| 完整分析（热，同进程第二次） | 0.159 s |
| 两路并发（2×1000 条） | 0.329 s |
| 峰值内存（tracemalloc） | 5.2 MB |
| 解析成功率 | 1000/1000 |

边界：

- 这是**离线**数字，不含 OpenAlex/Crossref/DOI 联网核验；联网耗时由数据源限速与缓存决定，不在此表内；
- 题录是合成模板，`status_counts` 全为 `Unknown` 是关闭核验的预期结果，不代表真实核验准确率；
- 冷/热指同一进程内两次调用，热路径主要省掉重复的规范化与格式检查；
- 原始数据 `data/experiments/stress_1000.json`。
