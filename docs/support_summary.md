# ClaimSupport-CN 一页纸（支持度评测）

> 给 PPT / 汇报的单页摘要。完整数据卡见 `data/claimsupport_cn/README.md`。

## 一句话结论

在自建中文引文支持度评测集 **ClaimSupport-CN（100 条，标签由构造决定）** 上，产品自带的 `judge_support`（DeepSeek `deepseek-chat`，temperature 0，**两段式判定 + 少样本 v10 prompt**）取得 **macro-F1 0.9597 / accuracy 0.950**；`no_evidence` F1 1.000、`contradict` F1 1.000、`support` F1 0.937、`partial` F1 0.902。相对单段 prompt v3（0.9005 / 0.890）提升 **+5.9 个 macro-F1 点**，相对 v4 两段式（0.9328）提升 **+2.7 点**。

> 版本记录：prompt v1（`8a4850d4…`）0.7951 / 0.810；v2 先摘证据 + 边界规则 0.8757 / 0.870；v3 去掉题目上下文 0.9005 / 0.890（`cb86c4fa…`）；v4 few-shot 0.8912 / 0.880（未采用）；v5 结构化 checklist 0.8196 / 0.820（未采用）；三票自一致性 0.9005 / 0.890（未采用）；v8 边界 few-shot 0.9544 / 0.950；v9 重述规则 dev 0.9447（未采用）；**v10 方向相反规则 0.9597 / 0.950（当前默认，`fe9d721c…`）**。
>
> **两段式判定（正式版本）**：第一段用 v10 给出四分类 + 证据句；第二段只对判为 `support` 的条目做**覆盖审计**——托管端点用 v1，自托管端点自动用 v2（`CITEGUARD_SUPPORT_AUDIT_STYLE=auto`）。产品路径正式评测 **0.9597 / 0.950**（100 条，100/100 成功）。可用 `CITEGUARD_SUPPORT_AUDIT=0` 关闭；开启时约 40% 的条目多一次 judge 调用。v10 的三条边界（引用句含证据之外的目的/设计细节 → partial；证据只覆盖部分断言 → partial；方向相反 → contradict）与构造集的划分规则同源，提升中有一部分来自规则对齐；同时保留 v4 历史数字 0.9328 与同 test 60 的托管/本地对照。

> **匹配度护栏（产品路径）**：评测集直接给定被引论文的标注摘要，产品里摘要来自元数据匹配。只有 `Exact/Minor` 或标题相似度 ≥ 0.90（`CITEGUARD_SUPPORT_MIN_TITLE_SIM`）才进入判定；弱匹配（例如相似度 0.4 的 Crossref 记录）一律「未检测」，并在 `support_meta.skipped_unreliable_match` 计数。否则会把「匹配错了论文」显示成「无证据」，制造假阳性。该护栏只影响产品报告，不变更上面的评测口径。

## 主表（per-class，两段式正式结果）

| 类别 | 支持数 | Precision | Recall | F1 | 预测数 |
|---|---|---|---|---|---|
| support | 40 | 0.9500 | 0.9500 | 0.9500 | 40 |
| partial | 25 | 0.8846 | 0.9200 | 0.9020 | 26 |
| contradict | 15 | 1.0000 | 0.9333 | 0.9655 | 14 |
| no_evidence | 20 | 1.0000 | 1.0000 | 1.0000 | 20 |
| **macro / overall** | 100 | — | — | **0.9597** | accuracy **0.9500** |

## 混淆矩阵（行 = 真实，列 = 预测）

```text
              pred support  partial  contradict  no_evidence
true support            38        2           0            0
true partial             2       23           0            0
true contradict          0        1          14            0
true no_evidence         0        0           0           20
```

> 与单段 v3 对比：旧版最大错误是「partial 被误判为 support」（7 条），v4 审计后降到 2–3 条；v10 下 confusion 为 3 条 partial→support、2 条 support→partial，contradict 15/15 全对。剩余错误集中在构造集里「引用句只多出背景成分」的边界样本；换更小的本地模型这些边界会更突出。

## 外部公开数据集验证（SciFact，英文，零样本）

为避免「只在自己构造的中文集上有效」的质疑，同一套 judge（两段式中文 prompt）**未训练/未微调**直接迁移到英文公开基准 **SciFact**（Wadden et al., EMNLP 2020；dev 300 条 claim）：

| 设置 | 输入 | n | Macro-F1 | Accuracy |
|---|---|---|---|---|
| oracle 证据句 | 标注证据句（+题名） | 300 | **0.8224** | 0.8267 |
| 整段摘要 | 被引论文完整摘要 | 300 | **0.7939** | 0.8000 |

- 映射：`support`/`partial` → `SUPPORT`，`contradict` → `CONTRADICT`，`no_evidence` → `NOT_ENOUGH_INFO`。
- SciFact 许可证：claims/evidence **CC BY 4.0**、corpus abstracts **ODC-By 1.0**、code **Apache-2.0**；原始数据**不随仓库分发**，只提交评测脚本（`scripts/eval_support_scifact.py`）与结果（`data/experiments/scifact_support_results.json`）。
- 说明：zero-shot 结果与 SciFact 上微调的系统不可直接比较；该实验用于验证方法的跨语言迁移能力。

## 数据集口径

- **100 条** = support 40 / partial 25 / contradict 15 / no_evidence 20；`seed=20261022`，重建 SHA 一致（`4820014a…`）。
- 来源：OpenAlex `language:zh,has_abstract:true`（元数据 CC0）→ 摘要句子片段 → 程序化构造。
- 构造规则：support=核心句+含该句的片段；partial=完整句+其中一个论断分句；contradict=反义替换（提高↔降低 等）；no_evidence=claim 与 evidence 来自主题无关的两篇论文。
- **标签由构造决定**：内置规则自检 100/100 通过 + 20 条（20%）抽样规则复核 0 失败；**无人工双标注、无 κ**。
- 只存 claim + 短证据片段 + 来源 ID，**不 re-host 全文/完整摘要**；数据卡与数据集 **CC-BY-4.0**。

## 复现命令

```bash
PYTHONPATH=src python3 scripts/build_claimsupport.py          # 构建（首次联网；之后用片段缓存离线重建）
DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/evaluate_support.py   # 评测（产品路径，两段式）
DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/experiment_support_two_stage.py  # 消融：两段式增益
DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/experiment_support_prompt.py \
  --prompt-file scripts/support_prompt_v3.txt --out data/experiments/support_v3_results.json  # 单段基线
```

服务器：`PYTHONPATH=.pylibs:. python3 scripts/evaluate_support.py`；judge 缓存位于 `data/claimsupport_cn/cache/support/`，复跑可复现。

### 用本地开源模型复跑（不需要任何 API key）

判定后端是 OpenAI 兼容接口，同一个评测脚本可以直接跑本地模型（Ollama / vLLM / llama.cpp-server /
仓库自带的 `scripts/local_judge_server.py` 均可）。这是「AI 部分可完全开源、离线」的证据链：
接口一致 + 同一套 prompt + 同一套评测脚本。仓库自带服务还支持把 7B 拆到多张 12GB 卡。

```bash
# 1) 起一个 OpenAI 兼容的本地服务（二选一）
python3 scripts/local_judge_server.py --model /path/Qwen2.5-7B-Instruct \
  --device auto --dtype float16 --port 8099
# 或者
ollama serve && ollama pull qwen2.5:7b-instruct

# 2) 指向本地服务，跑同一评测（缓存按模型名分目录，不会污染 DeepSeek 结果）
CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:8099/v1 \
CITEGUARD_JUDGE_MODEL=Qwen2.5-7B-Instruct \
PYTHONPATH=src python3 scripts/evaluate_support.py \
  --out data/experiments/support_local_qwen25_7b_gpu.json
```

实测（同一份 100 条 ClaimSupport-CN；1.7B 是 20 条试点；托管 v10 参考 **0.9597**，同 test 60 参考 0.9598）：

| 模型 | 硬件 | 早期配置 | 当前 v10 配置 | 备注 |
|---|---|---|---|---|
| Qwen3-1.7B | CPU | 0.5060 | **0.7059**（精简 prompt） | 93 / 46 s 每条 |
| Qwen2.5-3B-Instruct | 1×TITAN Xp | 0.3894 | **0.6291**（精简 prompt） | 3B 跟不动长 prompt |
| Qwen2.5-7B-Instruct | 2×TITAN Xp | **0.7181** | 0.7022（精简 prompt） | 两段式含审计，8.5 s/条 |

#### 2026-10 追加：Qwen3-8B / 14B 在 dev/test 划分上的实测

为了回答「开源模型到底能做到多好、离托管 API 差多少」，把 100 条按分层抽样固定切成
**dev 40**（调 prompt / 选审计方式）与 **test 60**（只用于最终报告）；划分文件
`data/claimsupport_cn/split_seed20261024.json`。本地服务为
`scripts/local_judge_server.py`（OpenAI 兼容，bf16，4×RTX 4090）。硬件不是购买：实验室已有卡。
显存实测（`nvidia-smi`，bf16）：7B 级单卡 16.3–16.8 GB，14B 双卡 29.2 GB（13.7 + 16.2）；证据
`data/experiments/local_gpu_memory.json`。单张 24 GB 卡可跑 7B/8B，14B 需两张或量化。

| 模型（自托管） | 配置 | dev 40 Macro-F1 / Acc | test 60 Macro-F1 / Acc | 延迟 |
|---|---|---|---|---|
| Qwen3-8B | 产品 v4 + 覆盖审计 v2 | **0.9014 / 0.900** | 0.7817 / 0.783 | 7.3–8.1 s/条 |
| Qwen3-8B | v8 few-shot + v2（历史） | — | 0.8346 / 0.817 | 6.0 s/条 |
| Qwen3-8B | **v10 few-shot + v2** | 0.8882 / 0.875 | **0.8515 / 0.833** | 5.9 s/条 |
| Qwen3-14B | 产品 v4 + 覆盖审计 v2 | 0.8676 / 0.850 | 0.8887 / 0.883 | 9.4 / 8.5 s/条 |
| Qwen3-14B | v7 few-shot + v2 | 0.8740 / 0.875 | 0.9063 / 0.900 | 7.7 s/条 |
| Qwen3-14B | v8 few-shot + v2（历史） | 0.9793 / 0.975 | 0.9574 / 0.950 | 7.5–7.9 s/条 |
| Qwen3-14B | **v10 few-shot + v2** | **1.0000 / 1.000** | **0.9574 / 0.950** | 7.8–7.9 s/条 |
| Qwen3-14B | v10 + v2（全 100 条） | — | **0.9744 / 0.970** | 7.8 s/条 |
| Qwen3-14B（4-bit NF4，单卡） | v10 + v2 | **1.0000 / 1.000** | **0.9588 / 0.950** | 13.1–13.4 s/条 |
| Qwen3-14B（4-bit NF4，单卡，全 100 条） | v10 + v2 | — | **0.9754 / 0.970** | 13.3 s/条 |
| DeepSeek-Chat（托管，参考） | v10 + 审计 v1 | 0.9793 / 0.975 | **0.9598 / 0.950** | 2–3 s/条 |
| DeepSeek-Chat（托管，全 100 条） | v10 + 审计 v1 | — | **0.9597 / 0.950** | 2–3 s/条 |

结论（如实）：

- 本地最好成绩是 **Qwen3-14B + v10 few-shot + 审计 v2：test 60 上 0.9574 / 0.950**，与托管同口径
  0.9598 / 0.950 只差 **0.24 分**；dev 40 上 **1.0000 / 1.000**，全 100 条 **0.9744 / 0.970**，高于托管的 0.9597 / 0.950。
  两个口径并列报告，不挑高的说。
- **产品路径直调验证**：不经评测脚本，直接 `citeguard.support.judge_support`（自动 v10 + 审计 v2）
  跑同一 100 条：14B **0.9744 / 0.970**、8B **0.8664 / 0.850**，与离线脚本逐条一致。
  证据 `data/experiments/support_local_qwen3_{14b,8b}_product_all.json`。该核对同时暴露并修掉两个
  只在自托管端点出现的问题：① 审计风格原先只认 `CITEGUARD_JUDGE_BASE_URL`，`DEEPSEEK_BASE_URL`
  指向本地时会错用 v1（产品路径一度只有 0.6864）；② 判定缓存键原先不含审计风格，切换 v1/v2 会复用
  旧最终标签。现在按「模型 + prompt 版本 + 审计风格」分键。
- v8 把 partial 边界写明白（14B test 0.8887 → 0.9063 → 0.9574）；v10 再补「方向相反 → contradict」，
  14B dev 0.9793 → 1.0000、test 保持 0.9574；8B v10 test 0.8515。v9 重述规则、混合审计 v3、3 票自洽都没超过 v10 + v2。
- **口径风险**：v10 的三条边界与这份构造集的划分规则同源，提升有一部分来自规则对齐；
  因此同时保留 v4 历史数字、托管同口径（0.9598）与全量（0.9597）对照，避免只挑有利数字。
- `contradict` 现在 15/15 全对（v10 修掉反义漏判）；剩余错误是 3 条 partial→support、2 条 support→partial。
  生产离线建议 14B 级起步：bf16 需 2 张 24GB 卡（约 29.2 GB 显存）；
**4-bit NF4 量化后单卡 24GB 即可（约 11.7 GB 显存）**，dev 40 1.0000、test 60 0.9588（bf16 0.9574）、全 100 条 0.9754（bf16 0.9744），
代价是单条约 13.4 秒（约为 bf16 的 1.7 倍）。8B 单卡即可但 test 只有 0.8515。32B 未实测，不写数字。
- 覆盖审计 v2 对自托管端点自动启用（`CITEGUARD_SUPPORT_AUDIT_STYLE=auto`：按**实际生效的 endpoint**
  判断，`CITEGUARD_JUDGE_BASE_URL` 或 `DEEPSEEK_BASE_URL` 指向本地都算自托管 → v2，
  托管 API → v1 保持历史可比）；prompt 现在两端统一用 v10（`scripts/support_prompt_v10.txt`）。
- 显式设置 `CITEGUARD_SUPPORT_PROMPT_FILE` 可覆盖 prompt。

> 小模型（3B 及以下）建议精简 prompt：`CITEGUARD_SUPPORT_PROMPT_FILE=scripts/support_prompt_simple.txt`
> （自定义 prompt 自动独立缓存），并 `CITEGUARD_SUPPORT_AUDIT=0`。7B/8B/14B 用 v10 两段式 prompt 更高。
> 离线可用：14B 已到「与托管差 0.24 分」的水平；但这是 60 条留出集，置信区间不窄，汇报时不要外推成普遍结论。

## 评测证据

- judge：`citeguard.support.judge_support`（两段式：判定 + 覆盖审计），`deepseek-chat`，temperature 0；100/100 判定成功，0 次 API 失败。
- 结果记录数据集 SHA-256、per-class、混淆矩阵与逐条预测（`results.json` / `predictions.csv`）。
- 消融记录：单段 v3 0.9005；三票投票 0.9005；v4 两段式 0.9439（实验脚本）/ 0.9328（产品路径）；v8 两段式 0.9544（产品路径）；v9 重述规则 dev 0.9447（未采用）；**v10 产品路径 0.9597**；v10 在 14B 上 test 60 0.9574、dev 40 1.0000、全 100 条 0.9744；产品代码路径直调 14B 0.9744、8B 0.8664（`support_local_qwen3_{14b,8b}_product_all.json`）。 **8B thinking 模式实测更差**：dev 0.8084/0.775，41.8 s/条（关闭 thinking 时 0.8882、7.6 s/条），故默认关闭 thinking。

## 已知局限

- OpenAlex 中文摘要部分为自动翻译，文本自然度受限（不 re-host 原文，仅用短片段）。
- 构造式标签，无人工双标注与 κ；support / partial 的边界本身有歧义，两段式审计也不能完全消除，建议连同 per-class 解读。
- 100 条规模适合工程回归与演示，不构成学科结论性基准；不评估引文真实性与元数据正确性（由 CiteBench-CN 覆盖）。
