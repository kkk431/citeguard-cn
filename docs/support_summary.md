# ClaimSupport-CN 一页纸（支持度评测）

> 给 PPT / 汇报的单页摘要。完整数据卡见 `data/claimsupport_cn/README.md`。

## 一句话结论

在自建中文引文支持度评测集 **ClaimSupport-CN（100 条，标签由构造决定）** 上，产品自带的 `judge_support`（DeepSeek `deepseek-chat`，temperature 0，**两段式判定**）取得 **macro-F1 0.9328 / accuracy 0.930**；`no_evidence` F1 0.976、`contradict` F1 0.929、`support` F1 0.925、`partial` F1 0.902。相对单段 prompt v3（0.9005 / 0.890）提升 **+3.2 个 macro-F1 点**。

> 版本记录：prompt v1（`8a4850d4…`）0.7951 / 0.810；v2 先摘证据 + 边界规则 0.8757 / 0.870；v3 去掉题目上下文 **0.9005 / 0.890**（`cb86c4fa…`）；v4 few-shot 0.8912 / 0.880（未采用）；v5 结构化 checklist 0.8196 / 0.820（未采用，`support_v5_results.json`）；三票自一致性 0.9005 / 0.890（未采用，提升不抵 3 倍成本）。
>
> **两段式判定（正式版本）**：第一段用 v3 prompt 给出四分类 + 证据句；第二段只对判为 `support` 的条目做**覆盖审计**——把引用句拆成对象/条件/因果/量级等要素，证据若没有覆盖全部要素就降级为 `partial`。实验脚本（`scripts/experiment_support_two_stage.py`）上 0.9439 / 0.940，产品路径正式评测 **0.9328 / 0.930**（两次独立缓存，差异来自 LLM 运行间波动约 ±2 分）。可用 `CITEGUARD_SUPPORT_AUDIT=0` 关闭；开启时约 40% 的条目多一次 judge 调用。

> **匹配度护栏（产品路径）**：评测集直接给定被引论文的标注摘要，产品里摘要来自元数据匹配。只有 `Exact/Minor` 或标题相似度 ≥ 0.90（`CITEGUARD_SUPPORT_MIN_TITLE_SIM`）才进入判定；弱匹配（例如相似度 0.4 的 Crossref 记录）一律「未检测」，并在 `support_meta.skipped_unreliable_match` 计数。否则会把「匹配错了论文」显示成「无证据」，制造假阳性。该护栏只影响产品报告，不变更上面的评测口径。

## 主表（per-class，两段式正式结果）

| 类别 | 支持数 | Precision | Recall | F1 | 预测数 |
|---|---|---|---|---|---|
| support | 40 | 0.9250 | 0.9250 | 0.9250 | 40 |
| partial | 25 | 0.8846 | 0.9200 | 0.9020 | 26 |
| contradict | 15 | 1.0000 | 0.8667 | 0.9286 | 13 |
| no_evidence | 20 | 0.9524 | 1.0000 | 0.9762 | 21 |
| **macro / overall** | 100 | — | — | **0.9328** | accuracy **0.9300** |

## 混淆矩阵（行 = 真实，列 = 预测）

```text
              pred support  partial  contradict  no_evidence
true support            37        2           0            1
true partial             2       23           0            0
true contradict          1        1          13            0
true no_evidence         0        0           0           20
```

> 与单段 v3 对比：旧版最大错误是「partial 被误判为 support」（7 条），两段式审计后降到 2 条；`contradict` 的 2 条误判来自反义关系在机器翻译摘要里不够显式（已知局限）。

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

判定后端是 OpenAI 兼容接口，同一个评测脚本可以直接跑本地模型（Ollama / vLLM / llama.cpp-server 均可）。
这是「AI 部分可完全开源、离线」的证据链：接口一致 + 同一套 prompt + 同一套评测脚本。

```bash
# 1) 起一个 OpenAI 兼容的本地服务（示例：Ollama）
ollama serve
ollama pull qwen2.5:7b-instruct

# 2) 指向本地服务，跑同一评测（缓存按模型名分目录，不会污染 DeepSeek 结果）
CITEGUARD_JUDGE_BASE_URL=http://127.0.0.1:11434/v1 \
CITEGUARD_JUDGE_MODEL=qwen2.5:7b-instruct \
PYTHONPATH=src python3 scripts/evaluate_support.py \
  --out data/experiments/support_local_endpoint.json \
  --cache data/experiments/support_prompt_cache/local
```

> 已实测的 1.7B 级模型（transformers CPU，非上面命令）：20 条试点 macro-F1 **0.7059**（精简 prompt，46 s/条），
> 远低于 DeepSeek 的 0.9328。离线可用 ≠ 质量相同；生产离线建议 8B 级 + GPU，或继续用托管 judge。

## 评测证据

- judge：`citeguard.support.judge_support`（两段式：判定 + 覆盖审计），`deepseek-chat`，temperature 0；100/100 判定成功，0 次 API 失败。
- 结果记录数据集 SHA-256、per-class、混淆矩阵与逐条预测（`results.json` / `predictions.csv`）。
- 消融记录：单段 v3 0.9005；三票投票 0.9005；两段式 0.9439（实验脚本）/ 0.9328（产品路径）。

## 已知局限

- OpenAlex 中文摘要部分为自动翻译，文本自然度受限（不 re-host 原文，仅用短片段）。
- 构造式标签，无人工双标注与 κ；support / partial 的边界本身有歧义，两段式审计也不能完全消除，建议连同 per-class 解读。
- 100 条规模适合工程回归与演示，不构成学科结论性基准；不评估引文真实性与元数据正确性（由 CiteBench-CN 覆盖）。
