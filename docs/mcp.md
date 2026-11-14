# MCP 服务（stdio）

`integration/mcp/citeguard_mcp.py` 是一个**零依赖**的 Model Context Protocol（MCP）服务：
只用一个 Python 标准库文件，把 CiteGuard 的三项核验能力通过 stdin/stdout 暴露给
Claude Desktop、Cursor 等支持 MCP 的 AI 客户端。它自己不做检索、不调用模型，
只把请求转发给本机已经运行的 CiteGuard HTTP API。

- 协议：JSON-RPC 2.0，**每行一个 JSON 对象**（MCP stdio 传输）
- 声明版本：`2024-11-05`
- 实现方法：`initialize`、`notifications/*`（静默）、`ping`、`tools/list`、`tools/call`
- 工具：`citeguard_health`、`citeguard_check_support`、`citeguard_live_check`

## 验证状态（先看这里）

| 能力 | 证据 |
| --- | --- |
| 握手、`tools/list`、`tools/call`、未知方法、错误处理 | `python -m pytest tests/test_mcp_server.py -q` → **17 passed**（Python 3.13 与 3.11 各跑通；stdlib mock，不联网） |
| `initialize` 管道冒烟 | 经 stdin 传入一行 initialize，返回 `protocolVersion: 2024-11-05`、`serverInfo.name: citeguard-mcp`（见“手工冒烟”） |
| 真实 CiteGuard 服务上的 `citeguard_health` | 本机 `127.0.0.1:8013` 服务在线时冒烟返回 `ok:true`（版本号随仓库变化） |
| Claude Desktop / Cursor 实际加载 | **未验证**：本仓库不提供客户端截图；配置按 MCP stdio 规范编写，是否加载以客户端日志为准 |
| `citeguard_check_support` / `citeguard_live_check` 的真实模型调用 | 本文档未执行（需要本地判定模型与联网检索）；测试用 mock 覆盖协议与参数透传，不声称模型效果 |

## 前置条件

1. Python 3.9+（已在本机 3.11 / 3.13 上跑通测试；只依赖标准库，不需要安装本仓库的依赖）。
2. 本机 CiteGuard HTTP 服务已启动（默认 `http://127.0.0.1:8013`）：

   ```bash
   python -m uvicorn web.app:app --host 127.0.0.1 --port 8013
   ```

3. `citeguard_check_support` / `citeguard_live_check` 需要 CiteGuard 服务侧配置好判定模型；
   `citeguard_health` 不需要。模型/密钥不随仓库分发。

## 启动

服务由 MCP 客户端托管，通过 stdin 接收请求、stdout 返回响应；直接运行会停在等待输入状态，
这时可以手工输入请求行做冒烟。

```bash
cd /path/to/citeguard
python integration/mcp/citeguard_mcp.py
```

- 退出：Windows 按 `Ctrl+Z` 再回车；macOS/Linux 按 `Ctrl+D`。
- 启动时静默。设置 `CITEGUARD_MCP_DEBUG=1` 后会把请求/响应摘要写到 **stderr**，
  不影响 stdout 的协议流。
- 从任意工作目录用绝对路径运行也可以（服务不依赖当前目录，也不会 import `citeguard` 包）。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `CITEGUARD_BASE_URL` | `http://127.0.0.1:8013` | CiteGuard HTTP 服务地址；末尾斜杠会自动去掉 |
| `CITEGUARD_MCP_TIMEOUT` | `60` | 单次 HTTP 超时秒数，可为小数；非数字或 ≤0 会在调用时报可读错误 |
| `CITEGUARD_MCP_DEBUG` | 未设置 | 设为 `1` 时向 stderr 输出诊断日志 |

回环地址（`127.0.0.1` / `localhost` / `::1`）会绕过系统代理直连；指向远程地址时沿用系统代理。

## 客户端配置

### Claude Desktop

配置文件位置：

- Windows：`%APPDATA%\Claude\claude_desktop_config.json`
- macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "citeguard": {
      "command": "python",
      "args": ["C:\\path\\to\\citeguard\\integration\\mcp\\citeguard_mcp.py"],
      "env": {
        "CITEGUARD_BASE_URL": "http://127.0.0.1:8013"
      }
    }
  }
}
```

注意事项：

- MCP 客户端**不会展开 shell 变量**，`args[0]` 必须是绝对路径。
  在仓库根目录执行下面的命令取得当前绝对路径，替换进 JSON：

  ```powershell
  (Resolve-Path integration/mcp/citeguard_mcp.py).Path
  ```

- `command` 写 `python` 时，客户端进程的 `PATH` 必须能找到它；找不到就改成解释器绝对路径。
- 修改配置后需要**完全退出并重启** Claude Desktop。

### Cursor

项目级配置 `<项目>/.cursor/mcp.json`，或用户级 `~/.cursor/mcp.json`，使用相同的 `mcpServers` 结构：

```json
{
  "mcpServers": {
    "citeguard": {
      "command": "python",
      "args": ["C:\\path\\to\\citeguard\\integration\\mcp\\citeguard_mcp.py"],
      "env": {
        "CITEGUARD_BASE_URL": "http://127.0.0.1:8013"
      }
    }
  }
}
```

## 工具参考

| 工具 | CiteGuard HTTP 端点 | 必填参数 | 可选参数 |
| --- | --- | --- | --- |
| `citeguard_health` | `GET /api/health` | 无 | 无 |
| `citeguard_check_support` | `POST /api/support/check` | `claim`、`evidence` | 无 |
| `citeguard_live_check` | `POST /api/live/check` | `claim` | `page_title`、`page_url`、`mode`、`phase` |

所有工具的返回都是 MCP 标准结果：

```json
{"content": [{"type": "text", "text": "<紧凑 JSON>"}], "isError": false}
```

### `citeguard_health`

无参数。转发 `GET /api/health`，返回：

```json
{"ok": true, "version": "1.7.19", "offline": false, "supported": [".doc", ".docx", ".md", ".pdf", ".txt"]}
```

（示例值，`version` / `supported` 随仓库变化。）`offline: true` 表示服务处于离线模式，
这是正常结果，不是错误。

### `citeguard_check_support`

判断一条论点（`claim`）是否被给定证据（`evidence`）支持。转发 `POST /api/support/check`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `claim` | string | 是 | 待核验的论点，最长 500 字 |
| `evidence` | string | 是 | 证据文本（摘要或原文段落）；服务端超过 8000 字会截断，空串会被拒绝 |

返回的 text JSON 字段（值随输入变化）：

`ok`、`label`（`support` / `partial` / `contradict` / `no_evidence`）、`confidence`、
`low_confidence`、`review_hint`、`reason`、`evidence`、`audit`、`numeric`、`sub_claims`、
`prompt_version`。

```json
{"ok": true, "label": "support", "low_confidence": false, "review_hint": "", "confidence": 0.91, "reason": "证据直接陈述了该数值", "evidence": "实验显示平均提升 2.1%。", "numeric": {"status": "match"}, "prompt_version": "…"}
```

（字段固定，值随输入变化；`numeric` / `audit` / `sub_claims` 的结构以 `/api/support/check` 返回为准。）
服务端没有可用判定模型时返回 HTTP 503 `judge_unavailable`，离线模式下返回 HTTP 503 `offline`，
两者都会变成 `isError: true` 的可读文本。

### `citeguard_live_check`

CiteGuard Live 划词核验：判断页面中选中的一句话与检索到的候选文献摘要是否一致。
转发 `POST /api/live/check`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `claim` | string | 是 | 页面中选中的句子，最长 500 字 |
| `page_title` | string | 否 | 页面标题，最长 300 字；与 `page_url` 至少给一个检索效果最好 |
| `page_url` | string | 否 | 页面 URL，最长 2048 字符；DOI / arXiv 链接会被解析到参考列表 |
| `mode` | string | 否 | `fast`（默认，只判 top-1 候选）或 `full`（最多判 3 条，更准但约 3 倍慢） |
| `phase` | string | 否 | `retrieve` 只返回候选；`judge` 判定（会再次读取页面/摘要缓存）；`full`（默认）检索 + 判定 |

返回的 text JSON：

```json
{"ok": true, "label": "support", "confidence": 0.72, "reason": "…", "evidence": {"quote": "…", "title": "…"}, "candidates": [{"title": "…", "authors": ["…"], "year": 2021, "venue": "…", "doi": "10.1234/…", "url": "https://…", "source": "openalex", "abstract": "…", "has_abstract": true, "score": 0.83}]}
```

- `label` 取值与 `citeguard_check_support` 相同；`phase=retrieve` 时只给候选、不产生判定。
- `evidence` 仅当引文是某个候选摘要的**原文片段**时才非 `null`。
- `candidates` 最多 5 条，`abstract` 会截断。
- `page_title` / `page_url` 只是检索线索：仅白名单内的 arXiv 页面会被抓取 HTML
  （5 秒超时、2 MB 上限）；`citeguard_check_support` 完全不检索。

## 协议交互示例

`initialize`（请求一行，响应一行；`instructions` 在示例中做了省略）：

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"claude","version":"0"}}}
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"citeguard-mcp","version":"1.0.0"},"instructions":"CiteGuard-CN：中文引证核验。……"}}
```

`tools/list` 返回 3 个工具及其 `inputSchema`（参数见上一节的工具参考）。

`tools/call`：

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"citeguard_health","arguments":{}}}
{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"{\"ok\":true,\"version\":\"1.7.19\",\"offline\":false,\"supported\":[\".pdf\",\".txt\"]}"}],"isError":false}}
```

`ping` 返回空结果 `{"jsonrpc":"2.0","id":3,"result":{}}`。

未知方法返回 JSON-RPC 错误（服务进程不退出）：

```json
{"jsonrpc":"2.0","id":4,"method":"citeguard/not-a-method"}
{"jsonrpc":"2.0","id":4,"error":{"code":-32601,"message":"Method not found：citeguard/not-a-method"}}
```

其他协议级错误：请求行不是 JSON → `-32700`；每行不是对象或缺 `method` → `-32600`；
`tools/call` 的参数结构不对 → `-32602`。

## 错误处理

工具层的失败**不抛栈**，而是返回 `isError: true` 的一条文本，AI 客户端可以直接转述：

| 场景 | text 内容（示例） |
| --- | --- |
| CiteGuard 未启动 | `无法连接 CiteGuard 服务 http://127.0.0.1:8013/api/health：…。请先在仓库根目录启动服务：python -m uvicorn web.app:app --host 127.0.0.1 --port 8013` |
| 服务端 HTTP 4xx/5xx | `CiteGuard API 返回 HTTP 400（http://127.0.0.1:8013/api/support/check）：需要 claim 和 evidence 两个字段` |
| 缺必填参数 | `缺少必填参数 evidence（非空字符串）` |
| 未知工具 | `未知工具 'x'。可用工具：…` |
| 请求超时 | `请求 … 超时（CITEGUARD_MCP_TIMEOUT=60s）。…` |
| 响应不是 JSON | `… 返回的不是 JSON：…。请确认 CITEGUARD_BASE_URL 指向的是一个 CiteGuard 服务。` |

## 边界

- **无鉴权**：服务假定本机回环信任，不校验调用方身份，也不要直接暴露到公网；
  确需共享时在前面加一层带鉴权的反向代理，并设置 `CITEGUARD_BASE_URL`。
- **需要本地服务**：三个工具都转发本地 HTTP API；服务未启动时返回上面的可读错误，
  不会静默失败。
- **不读全文**：MCP 层不读本地文件、不抓网页、不调用模型，只转发字符串参数；
  `evidence` 必须由客户端提供。Live 的页面抓取发生在 CiteGuard 服务端，
  仅限白名单 arXiv 页面（5 秒超时、2 MB 上限），不保存全文。
- **不做真伪裁决**：证据不足时返回 `no_evidence`，不猜测；工具描述里也写明了这一点。
- **模型/密钥不随仓库分发**：MCP 服务只是 HTTP 客户端；判定模型配置由 CiteGuard 服务进程读取。
- **只实现 tools**：没有 resources / prompts / sampling；stdio 单会话、无状态。
- **离线模式**（服务端 `CITEGUARD_OFFLINE=1`）：`support` / `live` 返回 HTTP 503 `offline`，
  变成 `isError` 文本；`health` 仍可用并显示 `offline: true`。

## 测试与复现

```bash
cd /path/to/citeguard
python -m pytest tests/test_mcp_server.py -q
```

预期输出：`17 passed`（本机约 11 秒；Windows 上解释器启动较慢，不同机器有差异）。

测试做了什么：

- 用标准库 `http.server` 起一个 mock CiteGuard，提供 `/api/health`、`/api/support/check`、
  `/api/live/check`，随机端口、只监听 `127.0.0.1`；
- 以 `subprocess` 启动**真实的** `integration/mcp/citeguard_mcp.py`，用 stdin/stdout 发协议请求；
- 断言请求 `id` 原样返回、协议版本、`serverInfo`、三个工具名与 schema、
  参数逐字段透传（含中文）、`mode`/`phase` 默认值、HTTP 400 的 `detail` 变成 `isError` 文本、
  连接被拒绝时的可读提示、未知方法 `-32601`、坏 JSON `-32700`、通知无响应、EOF 退出码为 0；
- 全程本机回环，不联网，不调用任何模型。

手工冒烟（PowerShell，仓库根目录）：

```powershell
$req = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
$req | python integration/mcp/citeguard_mcp.py
```

应输出一行 `{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",…}}`。

macOS / Linux：

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  | python integration/mcp/citeguard_mcp.py
```

## 排错

| 症状 | 处理 |
| --- | --- |
| 工具返回“无法连接 CiteGuard 服务” | 先启动服务；确认端口与 `CITEGUARD_BASE_URL` 一致 |
| HTTP 503 `judge_unavailable` | 配置判定模型（见 `docs/api.md`） |
| HTTP 503 `offline` | 关闭 `CITEGUARD_OFFLINE`，或在在线环境运行 |
| 客户端里看不到工具 | 检查 `args[0]` 是否绝对路径、`python` 是否在客户端的 `PATH` 中，并查看客户端日志；先用上面的管道冒烟确认服务本身可应答 |
| 服务在客户端中启动即退出 | 单独用管道运行同一条命令；若正常，多为客户端工作目录/环境变量差异 |
| Windows 控制台中文乱码 | 服务内部强制 UTF-8；客户端若按本地编码读取，可设 `PYTHONIOENCODING=utf-8` |

## 相关文档

- [API 与 Python SDK](api.md)
- [CiteGuard Live](live.md)
- [生态与接入面](ecosystem.md)
