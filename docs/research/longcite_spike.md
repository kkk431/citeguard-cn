# LongCite 公开模型/数据 spike（句级引用生成可行性）

> 结论先行（最终）：**reject，不接主功能，也不保留为离线草稿**。CPU（256 token）上 61.65 s/条、doc proxy F1 0.4957；GPU 4090（512 token）延迟达标（P50 3.70 s / P95 4.14 s，149 tok/s），但质量与生成控制不达标：doc F1 0.5060、statement F1 0.6446、20/20 截断；512 token 只是让模型继续枚举，19/20 条 statement 未闭合，249 条中 100 条空引用。瓶颈是生成控制与引用覆盖，不是算力。许可为 Llama-3.1 Community License，官方 GPT-4o judge 未跑，只有 proxy 指标。详见 §13。

## 1. 要回答的问题

- 公开的 LongCite 模型/数据能否在本仓库环境（CPU、无 GPU、无外部 judge）跑通？
- 句级引用生成的质量（引用召回/精确）与延迟，是否达到可产品化的门槛？
- 如果不行，能否给出可复现的负结果与明确的“不接”理由？

本 spike 只做推理与测量，不训练、不改产品代码；脚本仅落在 `scripts/`，结果落在 `data/experiments/longcite_spike.json`。

## 2. 模型与数据来源

| 材料 | 来源 | 版本/规模 | 许可 |
| --- | --- | --- | --- |
| LongCite-llama3.1-8b | https://huggingface.co/zai-org/LongCite-llama3.1-8b （镜像 https://hf-mirror.com/zai-org/LongCite-llama3.1-8b ） | 8.03B 参数；5 个 safetensors 分片，16.06 GB | Llama-3.1 Community License（模型卡 README 的 License 段指向 [Meta Llama 3.1 LICENSE](https://huggingface.co/meta-llama/Meta-Llama-3.1-8B/blob/main/LICENSE)） |
| LongCite-45k | https://huggingface.co/datasets/zai-org/LongCite-45k | `long.jsonl` 5,726,201,192 B；44,600 条中英长上下文 QA，最长约 128k words | apache-2.0（数据集卡） |
| LongCite 代码/评测 | https://github.com/THUDM/LongCite ，论文 https://arxiv.org/abs/2409.02897 | `LongBench-Cite/eval_cite.py`、`auto_scorer.py` | Apache-2.0（仓库 LICENSE；本次只读参考，未复制代码） |
| llama.cpp | https://github.com/ggml-org/llama.cpp/releases/tag/b12428 | b12428 win-cpu-x64，`llama-server.exe` / `llama-quantize.exe` | MIT |

官方评测口径（`auto_scorer.py`）：citation recall 对每条 statement 用 judge 给支持分（Fully=1 / Partially=0.5 / No=0），无引用时若 judge 认为“需要引用”记 0、否则记 1；citation precision 对每个引用 span 判 Relevant/Unrelevant 取均值；官方 judge 为 `gpt-4o-2024-05-13`。**本环境没有该 judge，也没有任何外部 LLM API key，因此没有计算官方指标。**

## 3. 本地加载路线（含一次失败）

1. 先试现成 GGUF `DevQuasar-3/LongCite-glm4-9b-GGUF`（Q4_K_M，10,738,831,488 B）→ llama.cpp b12428 加载失败：
   `error loading model: done_getting_tensors: wrong number of tensors; expected 323, got 283`
   元数据为 chatglm 架构、40 层、10.52B、323 个张量（多出 40 个 `ffn_up.input_scale`），判断是该转换与当前 llama.cpp 的 chatglm 实现不兼容，**不是下载损坏**（字节数与 Content-Length 一致）。该路线放弃。
2. 改走 Llama 版本：下载 `zai-org/LongCite-llama3.1-8b` 全量 safetensors（16.06 GB），用 llama.cpp master 的 `convert_hf_to_gguf.py` 转 F16（16.07 GB），再 `llama-quantize.exe Q4_K_M` 得到 **4,920,738,912 B** 的 GGUF，llama.cpp b12428 加载成功。
3. Tokenizer 注意：模型仓库自带的是自定义 `TikTokenizer`（`tokenizer.tiktoken`），与当前 transformers 的调用方式不兼容（`tokenize() got an unexpected keyword argument 'split_special_tokens'`）。本地转换时用公开的 Llama-3.1 tokenizer.json（来自 `unsloth/Llama-3.1-8B-Instruct`，词表 128256，与模型 config 一致）替代；生成文本可读、引用格式正确，但**这一 tokenizer 替换未经官方验证**，列为未验证项。

## 4. 运行环境

- CPU：AMD Ryzen 7 8845H（8 核 16 线程）；RAM 27.8 GiB；无 GPU（`torch.cuda.is_available()=False`）。
- 后端：llama.cpp b12428 `llama-server`，`--ctx-size 8192 -t 16 -b 512 -ub 512`，Q4_K_M，模型常驻内存约 5.5 GB。
- 生成：temperature 0（贪心）、`cache_prompt=false`；每条最多 512 token（run B）或 256 token（run A，见下）。

## 5. 样本与抽取

- 数据：`long.jsonl` 只下载了前 300 MB（HTTP Range），可解析 2,533 行（末行截断已跳过）。
- 过滤：prompt ≤ 6000 字符（控制 CPU prefill），得到 27 条中文 + 6 条英文。
- 抽样：中文取前 14 条、英文取全部 6 条，共 **20 条（14 zh / 6 en）**，按脚本固定顺序抽取，可复现。
- 规模：每条 prompt 1,586–5,750 字符；文档块 `<C0>…<Cn>` 共 4–97 个。
- 语言判定：取 `[Document End]` 之后的问题文本，含 CJK 即中文。

## 6. 结果 run A（n_predict=256；已截断，仅作下界）

聚合（`data/experiments/longcite_spike.json`，生成于 2026-11-16 14:37）：

| 指标 | 值 |
| --- | --- |
| n | 20（14 zh / 6 en） |
| 生成 statement 总数 | 114，全部带 `<cite>` |
| 有引用样本 | 20/20 |
| 无效 span（越界/倒序） | 0 / 98 个 span |
| doc 级引用 proxy P / R / F1 | 0.5375 / 0.6510 / 0.4957 |
| statement 级对齐 proxy P / R / F1 | 0.5926 / 0.8649 / 0.7033（114 条中 51 条与参考 statement 3-gram Jaccard≥0.25） |
| 平均延迟 | 61.65 s/条（min 38.3，max 102.2） |
| prefill | 平均 1,793.8 token、22.2 s（≈81 tok/s） |
| decode | 平均 256 token、6.57 tok/s |
| 零命中样本 | #9、#17（doc-hit=0） |

逐条（run A）：

| # | 语言 | statement | 引用 span | 生成文档 | 参考文档 | doc P | doc R |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | zh | 4 | 2 | 2 | 1 | 0.50 | 1.00 |
| 2 | zh | 5 | 3 | 3 | 5 | 1.00 | 0.60 |
| 3 | zh | 4 | 4 | 4 | 1 | 0.25 | 1.00 |
| 4 | zh | 3 | 5 | 5 | 8 | 1.00 | 0.62 |
| 5 | zh | 5 | 1 | 1 | 7 | 1.00 | 0.14 |
| 6 | zh | 5 | 5 | 5 | 17 | 0.60 | 0.18 |
| 7 | zh | 9 | 3 | 3 | 1 | 0.33 | 1.00 |
| 8 | zh | 6 | 9 | 9 | 9 | 0.22 | 0.22 |
| 9 | zh | 7 | 1 | 1 | 4 | 0.00 | 0.00 |
| 10 | zh | 4 | 7 | 7 | 6 | 0.43 | 0.50 |
| 11 | en | 7 | 2 | 2 | 1 | 0.50 | 1.00 |
| 12 | en | 8 | 2 | 2 | 1 | 0.50 | 1.00 |
| 13 | en | 8 | 2 | 2 | 1 | 1.00 | 1.00 |
| 14 | en | 6 | 4 | 4 | 1 | 0.25 | 1.00 |
| 15 | en | 6 | 4 | 4 | 1 | 0.25 | 1.00 |
| 16 | en | 7 | 2 | 2 | 3 | 1.00 | 0.67 |
| 17 | zh | 8 | 4 | 1 | 1 | 0.00 | 0.00 |
| 18 | zh | 3 | 3 | 3 | 7 | 0.67 | 0.29 |
| 19 | zh | 4 | 4 | 4 | 1 | 0.25 | 1.00 |
| 20 | zh | 5 | 4 | 4 | 5 | 1.00 | 0.80 |

**截断警告**：run A 20/20 条都在 `</statement>` 之前被 256 token 上限截断，生成内容不完整；因此上表 P/R 是保守下界，不能当作模型真实能力的上限。run B 原计划把上限提高到 512 并重跑同一 20 条，但因服务连接被重置失败，未产出指标（见 §7）。

## 7. 结果 run B（n_predict=512，未完成）

按计划用同一 20 条、`--n-predict 512`、temperature 0 复跑，用于估计“放宽到 512 token 后指标能回升多少”。实际执行情况：

- 2026-11-16 14:47 启动，日志 `D:\Temp\citeguard_e3\run2.log`；
- 运行中 llama-server 连接被重置：`ConnectionResetError: [WinError 10054] 远程主机强迫关闭了一个现有的连接`，客户端退出码 1；
- 未写回 JSON（`longcite_spike.json` 仍是 run A 的结果，未被覆盖）；随后按 captain 指示暂停并关闭 llama-server，未再启动模型。

因此 run B 没有可用指标，本文所有数字均按 **run A（256 token，保守下界）** 结项；`longcite_spike.json` 中 `run_b.status=failed` 记录同一事实。若后续有稳定 GPU 环境，可按 §11 的命令重跑 512 版本，替换 §6/§7 的数字。

## 8. 与现有 v10 judge 的对照设计（未执行）

目标：把 LongCite 的“生成句 + 引用块”喂给现有 ClaimSupport 判官，测“生成句子是否被所引块支持”，从而把生成质量落到本产品的四档标签上。

- 输入：LongCite 的每条 `<statement>` 去掉 `<cite>` 后作为 claim；其引用 span 对应的 `<C…>` 文本拼接为 evidence；页面标题用数据集里的文档标题（若缺则留空）。
- 判官：产品 v10 prompt（`support.py`，PROMPT_VERSION=4），标签 support / partial / contradict / no_evidence。
- 指标：support+partial 占比、no_evidence 占比、与人工/构造金标的一致率；对照现有 ClaimSupport-CN 100 条的 macro-F1 0.9597（同判官、同 prompt 版本）。
- 成本：20 条 × 1 次判官调用；若走 DeepSeek API 约 1–2 s/条；本环境无 API key，未执行，只留设计。
- 备注：这只能回答“生成句是否被引用块支持”，不能回答“引用块是否是该问题的正确证据”，后者仍需人工或外部金标。

## 9. 产品化门槛与结论

| 门槛 | 现状 | 判定 |
| --- | --- | --- |
| 交互延迟 | CPU 61.65 s/条（run A，256 token）；GPU 4090 Q4 估算 30–60 tok/s → 512 token 约 9–17 s，仍非交互 | 不满足 |
| 显存/内存 | Q4_K_M 4.92 GB，CPU 常驻 5.5 GB；GPU 需 ≥6 GB | 满足（若仅离线） |
| 许可 | 模型 Llama-3.1 Community License（含再分发/命名条款）；数据集 Apache-2.0 | 可用于研究/比赛演示，但不能当 Apache-2.0 资产打包 |
| 质量可验收性 | 官方指标依赖 GPT-4o judge；本环境只有 doc/statement 代理 | 不满足“可复现验收” |
| 与本产品契合 | 本产品核心是“核验已有引用”，LongCite 是“生成带引用答案”，方向不同 | 低 |

**结论：不接主功能（Live/CiteMap 的核验链路）；保留为离线“带引用草稿/引用建议”实验（hold）。** 若后续有 GPU 且拿到 judge，可先复测 run B/人工抽检 30 条，再评估是否做“综述草稿”边角功能；在此之前不投入工程化。

## 10. 未验证与限制

1. 官方 citation recall/precision 未计算（无 GPT-4o judge、无 API key）；本文所有 P/R/F1 都是 doc/statement 级代理。
2. run A 全部截断；run B 的截断比例待补。
3. Tokenizer 用公开 Llama-3.1 tokenizer.json 替代模型自带 `TikTokenizer`，未与官方推理脚本逐 token 对比。
4. GGUF 为本地转换，非官方发布；量化误差未测。
5. 样本只有 20 条（14 zh / 6 en），且来自 LongCite-45k 的前 300 MB，不是随机全量抽样。
6. 无人工评分；没有验证“引用块是否真的支持句子”的语义正确性（只测了文档集合重叠）。
7. 模型权重许可为 Llama-3.1 Community License；商用/再分发条件未做法务确认。

## 11. 复现命令

```powershell
# 1) 下载权重（hf-mirror；xet 会断流，需 curl -C - 或 huggingface_hub 续传）
#    目标目录 D:\Temp\citeguard_e3\longcite_llama（5 个 safetensors + config + tokenizer 文件）

# 2) 转 F16 GGUF（llama.cpp master 源码里的脚本）
python llama-src\llama.cpp-master\convert_hf_to_gguf.py D:\Temp\citeguard_e3\longcite_conv `
  --outfile D:\Temp\citeguard_e3\longcite-f16.gguf --outtype f16

# 3) 量化 Q4_K_M
llama\llama-quantize.exe longcite-f16.gguf longcite-q4km.gguf Q4_K_M 16

# 4) 起服务
llama\llama-server.exe -m longcite-q4km.gguf --ctx-size 8192 -t 16 --port 8099 --no-webui -b 512 -ub 512

# 5) 跑 20 条样本（仓库脚本）
$env:PYTHONIOENCODING='utf-8'
python scripts/longcite_spike_llamacpp.py --n 20 --n-predict 512

# 6) 句级对齐代理（临时脚本，未入库）
python D:\Temp\citeguard_e3\post_longcite.py
```

数据只落在 `data/experiments/longcite_spike.json`（含每条的生成文本与参考文本），不重分发 LongCite-45k 原文。

## 12. 文件

| 文件 | 说明 |
| --- | --- |
| `scripts/longcite_spike_llamacpp.py` | 本 spike 的主脚本：llama-server 调用、prompt 抽样、引用解析、代理指标、JSON 输出 |
| `scripts/longcite_spike.py` | 早期 transformers CPU 版本（0.57 tok/s，保留作对照，不是本次结果来源） |
| `data/experiments/longcite_spike.json` | 20 条样本的逐条生成文本、参考文本、指标与延迟 |
| `docs/research/longcite_spike.md` | 本文 |

## 13. GPU 复跑（4090，20 条 / 512 token）

同一批 20 条样本（14 中文 / 6 英文，t29 选择）、同一份 Q4_K_M GGUF、temperature 0，只把设备从 CPU 换成单张 RTX 4090、n_predict 从 256 提到 512。

### 13.1 环境与模型

| 项 | 值 |
|---|---|
| 设备 | NVIDIA GeForce RTX 4090 (CUDA_VISIBLE_DEVICES=3) |
| 后端 | llama.cpp llama-server (CUDA 12.0, sm_89), CUDA_VISIBLE_DEVICES=3, GIN |
| 主机 | 127.0.0.1 (lmh, 4x RTX 4090) |
| 模型 | zai-org/LongCite-llama3.1-8b (GGUF Q4_K_M, t29 conversion)（8.03B） |
| 许可证 | Llama 3.1 Community License |
| 数据集 | LongCite-45k (Apache-2.0) |
| 权重 | GGUF Q4_K_M，4920738912 B，sha256 `d76b7d905ae8caceba2533017b212b3746b17e8f6b387e0d3b49b4458072f501` |
| 样本 / n_predict / temperature | 20 / 512 / 0.0 |
| 官方指标 | NOT run: official LongCite citation recall/precision needs a GPT-4o judge; this run reports proxy metrics only |

### 13.2 延迟与吞吐

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

### 13.3 质量（proxy）

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

### 13.4 门槛与结论

| 门槛 | 要求 | 实测 | 结论 |
|---|---|---|---|
| p50_wall_s | ≤ 5.00 | 3.7020 | 通过 |
| p95_wall_s | ≤ 15.00 | 4.1410 | 通过 |
| doc_f1_proxy | ≥ 0.65 | 0.5060 | **未过** |
| statement_f1_proxy | ≥ 0.75 | 0.6446 | **未过** |
| truncation_rate | ≤ 0.20 | 1.0000 | **未过** |

**结论：`reject`**

未过门槛：`doc_f1_proxy`、`statement_f1_proxy`、`truncation_rate`

### 13.5 失败样例（按 doc F1 最差的 4 条）

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

### 13.6 逐条明细（20 条）

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

### 13.7 限制

- 只有 20 条样本（14 中文 / 6 英文），来自 LongCite-45k 的 prompt ≤6000 字符子集；不是完整 LongCite 评测集。
- 官方 citation recall/precision（GPT-4o judge）未跑：主机无 API key，且与 t29 不可比。
- 单次运行、temperature 0、固定 seed-free 采样；decode 速度受单卡 4090 与 batch 1 限制。
- llama.cpp 的 CUDA 后端对 LongCite 自定义 tokenizer 的处理与 transformers 不完全等价（t29 已用公共 Llama-3.1 tokenizer.json 替换 TikTokenizer，未做逐 token 对齐验证）。

### 13.8 复现

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
