# 模型清单与使用说明

本项目**不训练、不微调、不分发模型权重**。所有模型均为上游开源模型，按原许可证使用；我们做的是提示词、两段式判定、覆盖审计与工程接线。权重请从上游仓库获取。

## 用到的模型

| 模型 | 用途 | 许可证 | 实测 |
|---|---|---|---|
| [Qwen3-14B](https://huggingface.co/Qwen/Qwen3-14B) | 支持度判定主模型（prompt v10） | Apache-2.0 | test60 macro-F1 0.9574；全量 100 条 0.9744 |
| Qwen3-14B 4-bit（上游量化） | 显存受限时替代 bf16 | Apache-2.0 | test60 0.9700；显存约 11.7 GB |
| [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) | 支持度备选 / 上下文实验 | Apache-2.0 | 支持度全量 0.8664；4-bit 0.8165 |
| [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) | 图表核验（VL） | Apache-2.0 | 真实图表 10 条 0.90；加上下文 0.94 |
| [Qwen3-VL-8B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct) | 图表核验默认模型 | Apache-2.0 | 真实图表小样本 0.96；ChartCheck 200 条 0.7871 |
| DeepSeek（OpenAI 兼容，可选） | 无 GPU 时的支持度判定 / 探索性扩展 | 服务条款 | 托管基线 |

国内镜像（Hugging Face 访问不畅时）：

- <https://modelscope.cn/models/Qwen/Qwen3-14B>
- <https://modelscope.cn/models/Qwen/Qwen3-8B>
- <https://modelscope.cn/models/Qwen/Qwen2.5-VL-7B-Instruct>
- <https://modelscope.cn/models/Qwen/Qwen3-VL-8B-Instruct>

## 配置

```bash
# 文本判定（OpenAI 兼容接口）
CITEGUARD_LLM_ENDPOINT=http://127.0.0.1:8097/v1
CITEGUARD_LLM_MODEL=Qwen3-14B
CITEGUARD_LLM_API_KEY=...

# 图表核验（可选）
CITEGUARD_VL_ENDPOINT=http://127.0.0.1:8099/v1
CITEGUARD_VL_MODEL=qwen2.5-vl-7b
```

本地起 OpenAI 兼容服务可用 `scripts/local_text_server.py`、`scripts/local_vl_server.py`（vLLM 或 transformers 皆可）。不配模型也能运行：解析、题录核验、GB/T 格式检查、报告导出不依赖模型；支持度与图表会如实标注“未检测”。

## 许可证与边界

- 以上模型均为 Apache-2.0；权重不随本仓库分发。
- 模型输出仅作辅助判断，最终结论与修改建议由规则引擎与人工复核决定。
- 第三方组件与资源见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
