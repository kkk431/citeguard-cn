# HTTP API 与 Python 客户端

服务默认监听 `http://127.0.0.1:8010`；所有响应为 JSON。

## 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查：`ok` / `version` / `offline` |
| POST | `/api/support/check` | 单条「claim + evidence」支持度核验，返回四档标签、置信度、理由、覆盖审计、数值提示 |
| POST | `/api/support/batch` | 批量版本，最多 50 条，4 路并发 |
| POST | `/api/feedback` | 判错反馈：本地 JSONL 队列（任务号/条目号/原判/正确标签/备注），不上传 |
| POST | `/api/figure-check` | 图表核验（图片 + 每行一条 claim，最多 5 条） |
| GET | `/word/taskpane` | Word 任务窗格页面（预览版） |
| GET | `/api/report/{id}/diff?against={old_id}` | 字段级复检 diff（已解决/仍存在/新增/状态变化） |
| GET | `/api/jobs/{id}/events` | 任务进度的 SSE 流（`text/event-stream`，每 0.5 s 推送一条 JSON，`status` 为 done/error 时结束） |

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


## 进度流示例

```bash
curl -N http://127.0.0.1:8010/api/jobs/<job_id>/events
# data: {"id":"…","status":"running","progress":42,"stage":"核验第 7/15 条","error":""}
```

前端现在优先用 SSE；连接失败或服务端不支持时自动回退到轮询（1.2 s 一次），所以老部署也能工作。

## GET /api/reports/zip?ids=id1,id2

把多个已完成报告打成一个 ZIP：每个任务一个子目录（report.html/json/md/refs/ris/enw/annotated），根目录额外合并 `all.ris` 与 `all.enw`，附 `manifest.json`。一次最多 20 份；未知/未完成的任务会被跳过，全部无效时返回 404。

