# CiteBench-CN 评测一页纸

> 给 PPT / 汇报用的单页摘要。完整数据卡见 `data/citebench_cn/README.md`。

## 一句话结论

在自建的中文引文核验评测集 **CiteBench-CN（250 条，标签由构造决定）** 上，CiteGuard-CN v1.1 达到 **macro-F1 0.9684 / accuracy 0.968**，显著高于 zero-shot DeepSeek 的 **0.5159 / 0.536**；消融显示 DOI 锚点（-0.161）与题名检索（-0.194）都是不可省略的环节，30% 无 DOI 样本保证该结论不是「全都靠 DOI」的结果。

## 主表

| 系统 | macro-F1 | accuracy | Exact F1 | Minor F1 | Major F1 |
|---|---|---|---|---|---|
| **CiteGuard-CN v1.1**（规则 + 多源核验） | **0.9684** | **0.968** | 0.9615 | 0.9437 | 1.0000 |
| DeepSeek `deepseek-chat` zero-shot（prompt v3，无检索） | 0.5159 | 0.536 | 0.4000 | 0.4615 | 0.6863 |

- v1.1 per-class：Exact P 0.926 / R 1.000；Minor P 1.000 / R 0.893；Major P 1.000 / R 1.000。
- 评测口径：Exact = 字段全对；Minor = 论文真实存在但一个字段漂移；Major = 题名不存在或 DOI 404。

## 混淆矩阵（行 = 真实，列 = 预测；Exact / Minor / Major）

```text
            pred Exact  Minor  Major
true Exact     100        0      0
true Minor       8       67      0
true Major       0        0     75
```

## 消融（同一数据、同一代码路径）

| 配置 | macro-F1 | Δ vs full | 说明 |
|---|---|---|---|
| full | 0.9684 | 0 | DOI 锚点 + 题名检索 + 字段比对 |
| - DOI anchor | 0.8071 | **-0.1613** | 移除 DOI，只靠题名检索 |
| - title search | 0.7744 | **-0.1940** | 禁用题名检索，只靠 DOI 解析 |

## 数据集口径

- **250 条** = Exact 100 / Minor 75 / Major 75；`seed=20261022`，重建 SHA 一致（`1a8e466b…`，本地 Windows 与服务器 Linux 字节级一致）。
- **Major 75** = 虚构题名 38 + 不存在 DOI 37（`10.9999/…`，经 doi.org 逐条验证 404）。
- **Minor 75** = 年份 15 / 作者顺序 15 / 来源 15 / 卷-期 15 / 页码 15；DOI 大小写与后缀扰动已移除（大小写语义等价、后缀 404 属 Major）。
- **30% 无 DOI**：75 条 = Exact 30 / Minor 22 / Major 23，作为 `- title search` 消融的真实对照。
- 来源：OpenAlex（CC0）中文记录 → GB/T 7714 风格渲染 → 程序化受控扰动；每条渲染串回解析自检；不含全文/摘要。
- 许可证：数据卡与数据集 **CC-BY-4.0**（上游元数据 CC0 1.0）。

## 复现命令

```bash
PYTHONPATH=src python3 scripts/build_citebench.py        # 数据集（seed 20261022，SHA 一致）
PYTHONPATH=src python3 scripts/evaluate_citebench.py     # v1.1 评测 → results.json + 逐条 CSV
DEEPSEEK_API_KEY=... PYTHONPATH=src python3 scripts/deepseek_baseline.py   # DeepSeek 基线（prompt v3）
```

服务器：`PYTHONPATH=.pylibs:. python3 scripts/evaluate_citebench.py`；结果经 `/api/benchmark`、`/benchmark` 读取（服务无需重启）。

## 已知局限

- 作者字段有中英双写/机构作者噪声，作者顺序扰动的可检出率受限。
- 来源名存在中英文名、缩写等变体，来源漂移检测不覆盖所有现实写法。
- 仅用元数据，不评估「引文是否支持论点」；无 DOI 子集依赖题名检索召回。
- 250 条适合工程回归与演示，不构成学科结论性基准；DeepSeek 为无检索 zero-shot，仅为对照。

## 证据与备注

- 标签全部由构造决定，无模型标注；虚构 DOI 37/37 经 doi.org handle API 验证 404；渲染串回解析自检 0 失败。
- `results.json` 记录数据集 SHA-256、per-class、消融与 DeepSeek prompt 哈希（`prompt_sha256=e2637ac0…`），本地与服务器实跑指标一致。
