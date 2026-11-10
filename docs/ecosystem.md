# 生态与接入面

CiteGuard-CN 的核心是「一条引用 → 四层证据」的报告，但同一条支持度链路也开放给外部系统。
下面每一项都标注**验证状态**，不把“写好了”说成“已验证可用”。

| 接入面 | 位置 | 验证状态 |
| --- | --- | --- |
| 单条核验 API | `POST /api/support/check` | 已用真实服务冒烟（本机 0.9.81） |
| 批量核验 API | `POST /api/support/batch`（≤50，4 路并发） | 单测 + 冒烟 |
| 图表核验 API | `POST /api/figure-check` | 7B/8B/3B 实测见 docs/figure_check.md |
| 任务进度 SSE | `GET /api/jobs/{id}/events` | 单测（事件格式、终止、404） |
| Python 客户端 | `src/citeguard/client.py` | 4 个单测 + 对真实服务冒烟 |
| 浏览器扩展 | `extension/` | 本地加载可用，未上架商店 |
| Word 任务窗格 | `word-addin/`、`/word/taskpane` | **预览版；未在真实 Word 客户端加载测试** |
| Docker | `docker/Dockerfile` | 构建成功、容器 health 通过；镜像不含模型/密钥 |

## 最小示例

```python
from citeguard.client import CiteGuardClient

c = CiteGuardClient("http://127.0.0.1:8010")
r = c.check_support("该方法平均提升 2.3%。", "实验显示平均提升 2.1%。")
print(r.label, r.confidence, r.reason)
```

```bash
curl -N http://127.0.0.1:8010/api/jobs/<job_id>/events
```

## 边界

- 所有接口都不做“真伪裁决”：没有证据就返回 `no_evidence` / `insufficient`，不猜。
- 离线模式（`CITEGUARD_OFFLINE=1`）下支持度与图表核验返回 503 `offline`，页面显示离线横幅。
- 模型/密钥不随仓库分发；Word/扩展只是客户端，不内置任何 key。
