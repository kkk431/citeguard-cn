# 图表结论核验（可选能力）

> 一句话：把「图表 + 一句结论」交给开源的 Qwen2.5-VL-7B，判断结论是**被图表支持**、**与图表矛盾**，还是**图表信息不足**。这是引文核验的补充，不替代逐条引文真实性检查。

## 它解决什么

论文里常见「见图 3，A 方法的准确率最高」这类结论。传统引文核验只查「这篇文献是否真实存在、摘要是否支持这句话」，看不到图里的数据。图表核验把截图和结论一起交给视觉模型，让它核对坐标轴、图例、数值与趋势。

输出三档：

| 判定 | 含义 | 建议动作 |
|---|---|---|
| `supported` | 图表数据与结论一致 | 可保留 |
| `contradicted` | 图表数据与结论矛盾（数值/年份/极值不符） | 必须改结论或改图 |
| `insufficient` | 图表里没有足够信息判断 | 人工复核，不要当作「支持」 |

## 模型与运行方式

- 模型：**Qwen2.5-VL-7B-Instruct**（Apache-2.0，来自 ModelScope/魔搭）。
- 硬件：单张 RTX 4090（24 GB），bf16，峰值显存约 **16.0–16.1 GB**；首次加载约 **8 秒**（之后常驻）。
- 服务：`scripts/local_vl_server.py` 起一个 OpenAI 兼容的 `/v1/chat/completions` 服务；产品只通过 HTTP 调用，CPU 主机不加载模型。
- 产品开关：`CITEGUARD_VL_ENDPOINT`（必填，指向服务）、`CITEGUARD_VL_MODEL`（默认 `qwen2.5-vl-7b`）、`CITEGUARD_VL_API_KEY`（可选）、`CITEGUARD_VL_TIMEOUT`（默认 60 秒）、`CITEGUARD_VL_MAX_FIGURE_MB`（默认 8 MB）。未配置时 `/figure` 页面只展示说明、不接受提交。
- 隐私：图片只在这一次请求里发给**你自己配置的** GPU 服务，不写入磁盘、不发给第三方；产品本身不保存图表。

## 实测结果

模型服务部署在实验室 4090 主机上，用 `scripts/vl_figtest.py` 跑两组数据，prompt 与产品内置的一致（`PROMPT_VERSION = 1`）。

### 1. 合成控例（可客观评分）

20 张图（10 张柱状图 + 10 张折线图），每张图两条结论：一条是真实极值/数值（`supported`），一条是错误数值或错误年份（`contradicted`），共 40 条。图由 `scripts/make_synth_figtest.py` 生成，`seed=20261024`。

| 指标 | 数值 |
|---|---|
| 判定准确率 | **0.90**（36/40） |
| 支持类（20 条） | 17 条正确判 `supported`，3 条判 `insufficient` |
| 矛盾类（20 条） | 19 条正确判 `contradicted`，1 条判 `insufficient` |
| 误报「矛盾」 | **0**（没有把支持结论判成矛盾） |
| 平均延迟 / P90 | 1.55 秒 / 1.69 秒 |

### 2. 真实论文图表

从本地真实语料（中文论文 PDF）里由 `scripts/extract_real_figures.py` 截取候选图，人工挑出 5 张可读图表，加 5 条支持结论和 5 条矛盾结论，共 10 条。

| 指标 | 数值 |
|---|---|
| 判定准确率 | **0.90**（9/10） |
| 支持类（5 条） | 5/5 正确 |
| 矛盾类（5 条） | 4/5 正确（1 条判 `insufficient`） |
| 误报「矛盾」 | **0** |
| 平均延迟 / P90 | 2.56 秒 / 4.36 秒 |

### 为什么产品用 v1 prompt

同一批数据换了一个更「严格」的 v2 prompt（要求先复述图中数值再判断）：

| 数据 | v1（产品采用） | v2 |
|---|---|---|
| 合成控例 | 0.90，误报矛盾 0 | 0.925，但 **2 条支持结论被误判为矛盾** |
| 真实图表 | 0.90，误报矛盾 0 | 1.00 |

v2 在真实图上更好，但它在合成控例里出现了 2 次「把支持结论说成矛盾」——这是最伤人的错误类型。产品选择 v1：宁可漏判成 `insufficient`，也不轻易指控作者。v2 只作为实验记录保留。

## 复现

```bash
# 1) 生成合成控例（本地，需要 matplotlib）
python scripts/make_synth_figtest.py --n 20

# 2) 在 GPU 主机上起视觉服务（Qwen2.5-VL-7B，懒加载）
python scripts/local_vl_server.py --model /path/to/Qwen2.5-VL-7B-Instruct \
    --host 0.0.0.0 --port 8099

# 3) 跑评测（在 GPU 主机上，或能访问服务的主机）
python scripts/vl_figtest.py --images out/figtest_synth --claims out/figtest_synth/figtest_synth.json \
    --endpoint http://127.0.0.1:8099/v1 --out out/vl_synth.json
python scripts/vl_figtest.py --images out/figtest_real/candidates --claims out/figtest_real/figtest_real.json \
    --endpoint http://127.0.0.1:8099/v1 --out out/vl_real.json

# 4) 给产品打开能力
export CITEGUARD_VL_ENDPOINT=http://<gpu-host>:8099/v1
```

## 已知局限

- **输入是截图，不是 PDF 原图**：截图糊、字太小、图例被裁掉都会让模型读错；目前不做版面分析，只支持单张图表。
- **只校对「图 vs 结论」**：不检查图表本身的数据是否来自正文所述实验，也不做多图/跨页推理。
- **中文与英文混排图表**偶尔会把年份/数值读错；`insufficient` 仍建议人工复核。
- **规模验证还小**：真实图表只有 10 条结论，结论方向明确，但不足以当作大样本精度承诺；对外汇报时应同时给出合成集的 40 条数字与这里的局限。
- 服务需要 GPU；产品主机（CPU）本身不能跑这个能力。
