# ClaimSupport-CN 一页纸（支持度评测）

> 给 PPT / 汇报的单页摘要。完整数据卡见 `data/claimsupport_cn/README.md`。

## 一句话结论

在自建中文引文支持度评测集 **ClaimSupport-CN（100 条，标签由构造决定）** 上，产品自带的 `judge_support`（DeepSeek `deepseek-chat`，temperature 0）取得 **macro-F1 0.7951 / accuracy 0.810**，`no_evidence` 与 `support` 识别接近满分；主要误差集中在 **partial↔support**（证据只支持部分论断时 judge 倾向于判 support），说明「部分支持」的边界最需要校准。

## 主表（per-class）

| 类别 | 支持数 | Precision | Recall | F1 | 预测数 |
|---|---|---|---|---|---|
| support | 40 | 0.7143 | 1.0000 | 0.8333 | 56 |
| partial | 25 | 0.9167 | 0.4400 | 0.5946 | 12 |
| contradict | 15 | 1.0000 | 0.6667 | 0.8000 | 10 |
| no_evidence | 20 | 0.9091 | 1.0000 | 0.9524 | 22 |
| **macro / overall** | 100 | — | — | **0.7951** | accuracy **0.8100** |

## 混淆矩阵（行 = 真实，列 = 预测）

```text
              pred support  partial  contradict  no_evidence
true support            40        0           0            0
true partial            12       11           0            2
true contradict          4        1          10            0
true no_evidence         0        0           0           20
```

## 数据集口径

- **100 条** = support 40 / partial 25 / contradict 15 / no_evidence 20；`seed=20261022`，重建 SHA 一致（`4820014a…`）。
- 来源：OpenAlex `language:zh,has_abstract:true`（元数据 CC0）→ 摘要句子片段 → 程序化构造。
- 构造规则：support=核心句+含该句的片段；partial=完整句+其中一个论断分句；contradict=反义替换（提高↔降低 等）；no_evidence=claim 与 evidence 来自主题无关的两篇论文。
- **标签由构造决定**：内置规则自检 100/100 通过 + 20 条（20%）抽样规则复核 0 失败；**无人工双标注、无 κ**。
- 只存 claim + 短证据片段 + 来源 ID，**不 re-host 全文/完整摘要**；数据卡与数据集 **CC-BY-4.0**。

## 复现命令

```bash
PYTHONPATH=src python3 scripts/build_claimsupport.py          # 构建（首次联网；之后用片段缓存离线重建）
DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/evaluate_support.py   # 评测
```

服务器：`PYTHONPATH=.pylibs:. python3 scripts/evaluate_support.py`；judge 缓存位于 `data/claimsupport_cn/cache/support/`，复跑可复现。

## 评测证据

- judge：`citeguard.support.judge_support`，`deepseek-chat`，temperature 0，`prompt_sha256=8a4850d4…`；100/100 判定成功，0 次 API 失败。
- 结果记录数据集 SHA-256、per-class、混淆矩阵与逐条预测（`results.json` / `predictions.csv`）。

## 已知局限

- OpenAlex 中文摘要部分为自动翻译，文本自然度受限（不 re-host 原文，仅用短片段）。
- 构造式标签，无人工双标注与 κ；partial / contradict 的边界本身有歧义，误差集中于此，建议连同 per-class 解读。
- 100 条规模适合工程回归与演示，不构成学科结论性基准；不评估引文真实性与元数据正确性（由 CiteBench-CN 覆盖）。
