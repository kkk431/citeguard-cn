# HTTP API 与 Python 客户端

服务默认监听 `http://127.0.0.1:8010`；所有响应为 JSON。

## 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查：`ok` / `version` / `offline` |
| POST | `/api/support/check` | 单条「claim + evidence」支持度核验，返回四档标签、置信度、理由、覆盖审计、数值提示 |
| POST | `/api/support/batch` | 批量版本，最多 50 条，4 路并发 |
| POST | `/api/figure-check` | 图表核验（图片 + 每行一条 claim，最多 5 条） |
| GET | `/word/taskpane` | Word 任务窗格页面（预览版） |

`X-API-Key` / Bearer 认证只在设置了访问令牌时要求，默认本机不鉴权。

## Python 客户端（零依赖）

```python
from citeguard.client import CiteGuardClient

c = CiteGuardClient("http://127.0.0.1:8010")
print(c.health()["version"])

r = c.check_support("该方法平均提升 2.3%。", "实验显示平均提升 2.1%。")
print(r.label, r.confidence, r.reason)

batch = c.check_support_batch([
    {"claim": "A", "evidence": "..."},
    {"claim": "B", "evidence": "..."},
])
```

命令行：`python -m citeguard.client --claim "…" --evidence "…"`，不带 `--claim` 时打印 health。

错误统一抛 `CiteGuardError`，带 `status` 与 `code`（如 `offline`）。
