# 可选向量接口（BGE-M3 / OpenAI-compatible）

CiteGuard 的核验不依赖向量模型。这一层只服务于两个可选用途：

1. 中文题名候选重排（同题名不同版本、繁体/简体、别名）；
2. 题录库的语义搜索。

默认关闭：没有配置 endpoint 时，`citeguard.embeddings.embed_texts()` 会抛出
带人话的 `EmbeddingError`（“未配置向量服务…”），调用方必须显式回退到字符串匹配，
不允许静默失败。

## 配置

| 变量 | 含义 | 默认 |
|---|---|---|
| `CITEGUARD_EMBED_ENDPOINT` | 基础地址，如 `http://127.0.0.1:8080/v1` | 空（关闭） |
| `CITEGUARD_EMBED_MODEL` | 模型名 | `BAAI/bge-m3` |
| `CITEGUARD_EMBED_API_KEY` | Bearer token（可选） | 空 |
| `CITEGUARD_EMBED_TIMEOUT` | 超时秒数 | `30` |

接口要求：`POST {endpoint}/embeddings`，请求体 `{"model": ..., "input": [...]}`，
返回 `{"data": [{"embedding": [...]}, ...]}`。vLLM、TEI 的 OpenAI shim、Xinference
都提供这个形状。如果 endpoint 本身以 `/embeddings` 结尾，不会重复拼接。

## 自测（不下载权重）

```bash
PYTHONPATH=src python - <<'PY'
from citeguard.embeddings import rerank, load_config
print("configured:", load_config() is not None)
if load_config():
    print(rerank("深度学习 医学影像", ["医学图像分割综述", "教育公平研究"]))
PY
```

## 当前状态与边界

- 已实现：配置解析、OpenAI 兼容调用、超时/HTTP/JSON 错误的人话提示、余弦相似度、
  重排函数、6 个测试（本地假服务，不访问外网）。
- **未部署真实 BGE-M3 服务**：本机没有 embedding 端点；lmh GPU 服务已按要求关闭。
  因此没有“BGE-M3 召回提升 X%”的数字，也不把接口层写成效果。
- 尚未接入产品路径：库检索与候选重排仍走现有字符串归一化 + 模糊匹配；接入时必须
  先跑同一批评测（`scripts/eval_library_real.py` / `scripts/eval_title_norm.py`）做对照。
