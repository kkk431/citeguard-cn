## 8. GPU 复跑（4090，20 条 / 512 token）

同一批 20 条样本（14 中文 / 6 英文，t29 选择）、同一份 Q4_K_M GGUF、temperature 0，只把设备从 CPU 换成单张 RTX 4090、n_predict 从 256 提到 512。

### 8.1 环境与模型

| 项 | 值 |
|---|---|
| 设备 | NVIDIA GeForce RTX 4090 (CUDA_VISIBLE_DEVICES=3) |
| 后端 | llama.cpp llama-server (CUDA 12.0, sm_89), CUDA_VISIBLE_DEVICES=3, GIN |
| 主机 | 222.20.126.148 (lmh, 4x RTX 4090) |
| 模型 | zai-org/LongCite-llama3.1-8b (GGUF Q4_K_M, t29 conversion)（8.03B） |
| 许可证 | Llama 3.1 Community License |
| 数据集 | LongCite-45k (Apache-2.0) |
| 权重 | GGUF Q4_K_M，4920738912 B，sha256 `d76b7d905ae8caceba2533017b212b3746b17e8f6b387e0d3b49b4458072f501` |
| 样本 / n_predict / temperature | 20 / 512 / 0.0 |
| 官方指标 | NOT run: official LongCite citation recall/precision needs a GPT-4o judge; this run reports proxy metrics only |

### 8.2 延迟与吞吐

| 指标 | CPU Q4_K_M, 256 tok（t29） | GPU Q4_K_M, 512 tok（本次） |
|---|---|---|
| 平均 wall | 61.65 s | 3.76 s |
| P50 wall | — | 3.70 s |
| P95 wall | — | 4.14 s |
| 平均 prompt tokens | 1793.8 | 1793.8 |
| 平均生成 tokens | — | 512.0 |
| decode tok/s | 6.57 | 149.16 |
| 生成 token 上限命中 | — | 20/20 |
| 未闭合 statement | — | 19/20 |

### 8.3 质量（proxy）

| 指标 | CPU 256 tok（t29） | GPU 512 tok（本次） |
|---|---|---|
| doc-level P / R / F1（均值） | 0.5375 / 0.6510 / 0.4957 | 0.4996 / 0.7487 / 0.5060 |
| statement 级 P / R / F1 | 0.5926 / 0.8649 / 0.7033 | 0.5132 / 0.8667 / 0.6446 |
| 对齐上的生成 statement / 匹配对 | 114 / 51 | 249 / 64 |
| statement 匹配率 | 0.4474 | 0.2570 |
| 引用 statement 缺 cite | 0/114 | 100/249 |
| 无效 span / 零命中样本 | 0 / 2 | 0 / 1 |
| 截断率 | 100.0%（20/20） | 100.0%（20/20） |

doc-level 是「每条样本被引 chunk 集合 vs 参考回答被引 chunk 集合」的 P/R/F1 再取均值（t29 口径，t29 报告中把 chunk 称作 doc）；statement 级是 3-gram Jaccard ≥ 0.25 的贪心对齐 + 匹配对内 chunk 交集。两者都是 **proxy**，不是官方 LongCite 的 GPT-4o judge 指标。

**机制解读：512 token 为什么没有把质量拉上去**

1. 模型在这批长输入上不会自己停：两次运行都是 20/20 命中 token 上限（256 与 512），本次还有 19/20 条在 `<statement>` 中间被切断。
2. 多出来的 256 token 不是更完整的答案，而是继续往下啰嗦：生成 statement 从 114 条涨到 249 条，其中 100 条是空引用 `<cite></cite>`（t29 是 0 条），statement 匹配率从 0.4474 掉到 0.2570。
3. 因此 doc F1 只从 0.4957 动到 0.5060（+0.0103），statement F1 反而从 0.7033 降到 0.6446（-0.0587）。换到 4090 解决的是速度（见下），不是生成控制与引用覆盖。

速度收益：平均 wall 61.65 s → 3.76 s（约 16.4×），decode 6.57 → 149.16 tok/s（约 22.7×），单条范围 3.47–4.25 s。

### 8.4 门槛与结论

| 门槛 | 要求 | 实测 | 结论 |
|---|---|---|---|
| p50_wall_s | ≤ 5.00 | 3.7020 | 通过 |
| p95_wall_s | ≤ 15.00 | 4.1410 | 通过 |
| doc_f1_proxy | ≥ 0.65 | 0.5060 | **未过** |
| statement_f1_proxy | ≥ 0.75 | 0.6446 | **未过** |
| truncation_rate | ≤ 0.20 | 1.0000 | **未过** |

**结论：`reject`**

未过门槛：`doc_f1_proxy`、`statement_f1_proxy`、`truncation_rate`

### 8.5 失败样例（按 doc F1 最差的 4 条）

- **#9（zh，4.05 s，doc F1 0.0000，14 statements，缺 cite 13）**

  - 生成引用 chunk：[1]
  - 参考引用 chunk：[2, 3, 4, 5]
  - 摘录：？ <statement>根据获奖名单，榆中县的学校有以下作品获奖：<cite></cite></statement>  <statement>小学组： - 动物儿歌，作者王小彦，学校榆中县一悟小学，获二等奖<cite>[1-1]</cite></statement>  <statement>- 分类，作者李秋香，学校兰州市安宁区崔家庄小学，获二等奖<cite></cite></statement>  <statement>- 四则运算的意义，作者王玉梅，学校兰州市七里河区龚家湾第三小学，获二等奖<cite></cite></statement>  <statement>- 我诗诉我情，作者张

- **#11（en，3.73 s，doc F1 0.1538，13 statements，缺 cite 3）**

  - 生成引用 chunk：[7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
  - 参考引用 chunk：[18]
  - 摘录： <cite></cite></statement>  <statement>The third paragraph of a thank you letter is a good place to:<cite></cite></statement>  <statement>- Mention something that particularly appeals to you about working for the company, and reinforce a point or two in support of your application.<cite>[17-17]</cit

- **#6（zh，3.56 s，doc F1 0.1905，13 statements，缺 cite 10）**

  - 生成引用 chunk：[1, 4, 5, 7]
  - 参考引用 chunk：[1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
  - 摘录：<cite></cite></statement>  <statement>根据文章内容，这篇英文写作练习的要求主要包括：<cite></cite></statement>  <statement>1. 根据给定的题目，写一篇英文作文。题目包括描述与解释、图表分析、描述与说明等类型。<cite>[1-1][4-4][7-7]</cite></statement>  <statement>2. 作文分两段。第一段描述图片、事件、人物等内容；第二段则表达个人观点、看法、感受等。<cite>[4-5][7-7]</cite></statement>  <statement>3. 根据题目要求，使用恰

- **#10（zh，4.06 s，doc F1 0.2759，10 statements，缺 cite 2）**

  - 生成引用 chunk：[58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 78, 83, 88, 90, 91, 93, 94, 95]
  - 参考引用 chunk：[44, 47, 59, 78, 83, 88]
  - 摘录：？  <statement>根据山西中考模拟百校联考试卷(二)语文参考答案及评分标准，作文评分主要分为以下几个方面：<cite></cite></statement>  <statement>1. 内容：符合题意，能根据写作的目的、主题，选择新颖典型的内容。内容真实感人，叙事生动具体，描写富有表现力。情感真挚，能表达自己对自然、社会、人生的真实而独特的感悟。说明明白清楚；议论观点鲜明，理由充分，逻辑严密。<cite>[58-62][63-67][68-72]</cite></statement>  <statement>2. 结构：结构有创意，完整统一，过渡自然，条理清楚，详略得当，疏密相间，

### 8.6 逐条明细（20 条）

| # | 语言 | wall s | prompt tok | gen tok | decode tok/s | statements | 缺 cite | doc F1 proxy | 截断 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | zh | 3.72 | 2185 | 512 | 147.28 | 6 | 3 | 0.5000 | 是 |
| 2 | zh | 4.14 | 3693 | 512 | 142.63 | 10 | 3 | 0.8889 | 是 |
| 3 | zh | 4.10 | 3041 | 512 | 145.21 | 14 | 11 | 0.3333 | 是 |
| 4 | zh | 4.25 | 4164 | 512 | 141.36 | 8 | 2 | 0.6667 | 是 |
| 5 | zh | 3.81 | 1016 | 512 | 151.88 | 12 | 6 | 0.5455 | 是 |
| 6 | zh | 3.56 | 862 | 512 | 152.49 | 13 | 10 | 0.1905 | 是 |
| 7 | zh | 3.85 | 2697 | 512 | 145.99 | 17 | 5 | 0.5000 | 是 |
| 8 | zh | 3.69 | 973 | 512 | 152.10 | 13 | 3 | 0.5455 | 是 |
| 9 | zh | 4.05 | 3841 | 512 | 142.18 | 14 | 13 | 0.0000 | 是 |
| 10 | zh | 4.06 | 2714 | 512 | 145.84 | 10 | 2 | 0.2759 | 是 |
| 11 | en | 3.73 | 1246 | 512 | 151.04 | 13 | 3 | 0.1538 | 是 |
| 12 | en | 3.59 | 857 | 512 | 152.35 | 15 | 3 | 0.6667 | 是 |
| 13 | en | 3.58 | 1046 | 512 | 151.60 | 20 | 7 | 0.4444 | 是 |
| 14 | en | 3.56 | 890 | 512 | 152.30 | 11 | 1 | 0.6667 | 是 |
| 15 | en | 3.51 | 627 | 512 | 153.57 | 12 | 4 | 0.2857 | 是 |
| 16 | en | 3.49 | 679 | 512 | 153.35 | 16 | 8 | 0.5000 | 是 |
| 17 | zh | 3.47 | 545 | 512 | 153.97 | 14 | 7 | 0.6667 | 是 |
| 18 | zh | 3.70 | 1840 | 512 | 148.17 | 10 | 8 | 0.4000 | 是 |
| 19 | zh | 3.76 | 1646 | 512 | 149.14 | 11 | 0 | 1.0000 | 是 |
| 20 | zh | 3.68 | 1313 | 512 | 150.67 | 10 | 1 | 0.8889 | 是 |

### 8.7 限制

- 只有 20 条样本（14 中文 / 6 英文），来自 LongCite-45k 的 prompt ≤6000 字符子集；不是完整 LongCite 评测集。
- 官方 citation recall/precision（GPT-4o judge）未跑：主机无 API key，且与 t29 不可比。
- 单次运行、temperature 0、固定 seed-free 采样；decode 速度受单卡 4090 与 batch 1 限制。
- llama.cpp 的 CUDA 后端对 LongCite 自定义 tokenizer 的处理与 transformers 不完全等价（t29 已用公共 Llama-3.1 tokenizer.json 替换 TikTokenizer，未做逐 token 对齐验证）。

### 8.8 复现

```bash
# GPU 主机：编译 llama.cpp CUDA 后端并启动服务
bash data/experiments/a3b_scripts/longcite_build_llamacpp.sh   # GGML_CUDA=ON, ARCH=89
bash data/experiments/a3b_scripts/longcite_start_server.sh     # CUDA_VISIBLE_DEVICES=3, port 8099
# 跑 20 条 × 512 token
bash data/experiments/a3b_scripts/longcite_run_gpu.sh
# 本地汇总（JSON -> 本报告）
python scripts/longcite_gpu_report.py
```

文件：`data/experiments/longcite_spike_gpu.json`（逐条明细 + 聚合 + 门槛）、`data/experiments/longcite_spike_gpu_report.md`（本节）。
