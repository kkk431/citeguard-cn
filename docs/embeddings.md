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

## 真实端点实测（BGE-M3，2026-11-12）

在 lmh（4×RTX 4090）上部署了真实的 BGE-M3 服务：`BAAI/bge-m3`，1024 维，OpenAI 兼容
`POST /v1/embeddings`，脚本 `scripts/bge_embed_server.py`，端口 8090。评测脚本
`scripts/eval_embeddings_recall.py`：从 ClaimSupport-CN 取 n 条，每条 1 条正确证据 +
5 条其他条目的证据作干扰，按余弦相似度排序；原始 JSON 见
`data/experiments/embeddings_recall_bge_m3_n300.json`。

| n | recall@1 | MRR | 编码耗时 |
|---|---|---|---|
| 100 | 0.8000 | 0.8568 | 5.65 s |
| 300 | **0.8667** | **0.9042** | 20.24 s |

复现：

```bash
export CITEGUARD_EMBED_ENDPOINT=http://<host>:8090/v1
export CITEGUARD_EMBED_MODEL=bge-m3
PYTHONPATH=src python scripts/eval_embeddings_recall.py --n 300 \
  --out data/experiments/embeddings_recall_bge_m3_n300.json
```

边界（必须一起引用）：

- ClaimSupport-CN 是**构造集**，正例证据与引用句措辞接近，本评测只验证“端点可用 +
  重排链路能工作”，**不代表语义检索 SOTA**，也不等同真人写作分布。
- 干扰项是其他条目的证据，不是人工挑的难负例；中文长句、同主题干扰下 13.3% 的
  引用句首选不到正确证据。
- 一次运行、单模型、单硬件；服务用完已关闭，没有吞吐/并发数字。
- 本轮仍**未接入产品路径**：库检索与候选重排继续走字符串归一化 + 模糊匹配；
  接入前要用同一批 `scripts/eval_library_real.py` / `scripts/eval_title_norm.py`
  做对照，并保证 BGE 不可用时自动回退。
