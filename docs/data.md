# 数据说明

## 仓库内提供的数据

| 路径 | 内容 | 许可 |
|---|---|---|
| `data/citebench_cn/` | CiteBench-CN：250 条中文引文真实性评测集（真假、状态、字段） | CC-BY-4.0 |
| `data/claimsupport_cn/` | ClaimSupport-CN：100 条人工构造“结论—原文”评测集（support / partial / contradict / no_evidence） | CC-BY-4.0 |
| `data/claimsupport_cn/claimsupport_cn_ext.jsonl` | 60 条扩展集，source work 与原 100 条不重叠，用于泛化检查 | CC-BY-4.0 |
| `data/experiments/` | 支持度、引文核验、SciFact 零样本、格式回归、万方查询等逐条结果（JSON/CSV） | 同代码仓库 |
| `samples/offline_demo/` | 10 条真实开放文献题录，用于断网演示 | 题录元数据 |

评测集构建方式、标签规则与已知局限见 `data/*/README.md` 和 `docs/experiments.md`。SciFact 等第三方评测仅保留派生指标，不再分发原始语料。

## 不随仓库提供的内容

1. `data/real_corpus/` 下 22 篇真实论文 PDF：版权归原作者/出版方，仅用于本地评测。
2. 模型权重（Qwen3-14B/8B、Qwen2.5-VL-7B、Qwen3-VL-8B）：从 Hugging Face / ModelScope 按各自许可证获取，见 `docs/models.md`。
3. API Key、`.env` 密钥文件：只通过环境变量配置，见 `docs/deployment.md`。
4. 万方开放平台的原始查询响应：仅保留题录命中结果，不含密钥与账户信息。

## 许可证

- 代码：Apache-2.0（见 `LICENSE`）。
- 评测集与文档：CC-BY-4.0。
- 第三方组件与资源：见 `THIRD_PARTY_NOTICES.md`。
