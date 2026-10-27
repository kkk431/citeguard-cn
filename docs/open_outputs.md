# 开放成果包说明

本作按「开源赋能的 AI 应用创新」方向提交，代码、评测、数据卡与复现脚本一起开放；本文件说明包里有什么、能怎么用、哪些东西**不**开放。

## 1. 包里有什么

| 类别 | 内容 | 位置 |
| --- | --- | --- |
| 应用代码 | FastAPI 服务、Jinja 模板、原生 JS/CSS、七个能力模块 | `src/citeguard/`、`web/` |
| 测试 | 445 项单元/集成测试（含端到端 Web 流程） | `tests/` |
| 评测脚本 | CiteBench-CN、ClaimSupport-CN、真实语料、SciFact、ChartCheck、E4 格式回归、产物一致性检查 | `scripts/` |
| 数据 | 中文核验 250 条、支持度 100 条；真实语料只放 manifest 与抽取结果 | `data/citebench_cn/`、`data/claimsupport_cn/`、`data/experiments/` |
| 证据 | 每个关键数字对应的结果 JSON（含逐条预测与错误样本） | `data/experiments/*.json` |
| 文档 | README、数据卡、评测方法、部署、许可、资源清单、匿名自查、现场脚本 | `docs/`、`README.md`、`THIRD_PARTY_NOTICES.md` |

## 2. 许可证

- **本项目代码**：Apache License 2.0（见 `LICENSE`、`NOTICE`）。
- **自建数据**（CiteBench-CN / ClaimSupport-CN 的标注与构造脚本）：CC BY 4.0，引用时注明出处。
- **第三方数据/模型**：不在包内重新分发，按各自许可获取（见 `THIRD_PARTY_NOTICES.md` §3）；SciFact、ChartCheck 只保留评测脚本与结果 JSON。
- **论文原文**：不随包分发；真实语料只保留题录、引文句与判定结果，PDF 需自行按公开链接获取。

## 3. 怎么复用

```bash
pip install -r requirements.txt
python -m uvicorn web.app:app --host 127.0.0.1 --port 8010   # 本地演示，离线模式可跑
python scripts/benchmark_citebench.py                         # 复现核验指标
python scripts/verify_artifacts.py                            # 核对文档/证据数字
```

想替换判官模型：设置 `CITEGUARD_LLM_ENDPOINT` / `CITEGUARD_LLM_MODEL`（OpenAI 兼容），支持度 prompt 版本与审计开关见 `src/citeguard/support.py`；图表核验用 `CITEGUARD_VL_ENDPOINT` 指向任意 OpenAI 兼容视觉模型。

## 4. 对外贡献

- 向上游 `markrussinovich/refchecker` 提交 PR #77（修复裸 BibTeX 字段解析），状态以仓库页面为准（当前已关闭、未合并；报告与 PPT 中均按此表述，不写「已合并」）。
- 评测协议、匹配护栏、证据组织方式整理为可复用文档，供其他中文文献工具参考。
- 负结果同样开放：8B thinking 0.8084、3B VL 图表矛盾召回偏弱、DBLP 无公开 API 等，见 `docs/experiments.md`。

## 5. 不开放的东西（及原因）

- 大模型权重：体积大、许可以上游为准，用环境变量指向自建服务即可。
- API Key、`.env`、内网地址：不进包；打包器会做一次替换（见 `docs/anonymity_check.md`）。
- 真实论文 PDF：版权与数据库条款限制，只保留公开链接与抽取结果。
- 演示视频：按要求不做；现场演示脚本见 `docs/demo_script.md`。
