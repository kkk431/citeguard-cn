# CiteGuard Live 浏览器扩展 v2：真实浏览器验收报告

- 验收日期：2026-11-13（UTC 19:20；本机时间 2026-11-14 03:20）
- 执行人：usability（AgentTeams worker）
- 验收对象：`extension/v2`（MV3，扩展版本 0.2.0）
- 验收结论：**通过（带限定条件）**。真实 Chromium 能加载扩展，service worker 与 manifest 正常；本地 `/live` 页面用扩展 runtime 消息触发真实 `POST /api/live/check`；3 个真实公开网页完成选区 → 消息 → API 调用，HTTP 200、label 与面板渲染正常，`page_url` / `page_title` 原样到达 API；服务不可达时面板进入真实错误状态。右键菜单项的原生点击、真实 side panel 停靠手势、系统 Chrome/Edge 未自动化，见 §6。

> 本报告只记录实际运行结果。所有截图由 `scripts/verify_extension.py` 在同一次真实浏览器运行中直接保存，未补拍、未拼接、未改图。机器可读结果在脚本 stdout（`ok: true`，`failures: []`）。

## 1. 验收环境

| 项目 | 实际值 |
| --- | --- |
| 操作系统 | Windows 11（`Windows-11-10.0.26300-SP0`） |
| Python | 3.13.14 |
| Playwright | 1.64.0 |
| 浏览器 | Playwright 自带 Chromium **156.0.8078.4** |
| Chromium 路径 | `C:\Users\hejiaxuan\AppData\Local\ms-playwright\chromium-1248\chrome-win64\chrome.exe` |
| Edge | 157.0.4341.46，已安装但本次未用于加载扩展 |
| 系统 Chrome | 本机未安装 |
| 本地服务 | `http://127.0.0.1:8013`（本次运行时已启动） |
| 扩展目录 | `extension/v2` |
| 扩展 ID | `ccdjaijaflemilhobcjbackhkoioohnh`（本机未打包加载路径下的稳定 ID） |

扩展 manifest 实测：

- `manifest_version = 3`
- `name = "CiteGuard Live · 划词核验"`
- `version = "0.2.0"`
- `minimum_chrome_version = "116"`
- `side_panel.default_path = "sidepanel.html"`
- `host_permissions` 仅包含 `127.0.0.1` / `localhost` 本地服务

> 环境注意：本机 `PLAYWRIGHT_BROWSERS_PATH` 指向一个空目录 `D:\Caches\playwright`，直接启动会找不到浏览器。脚本会优先使用 Playwright 常规缓存路径和 `CHROME_PATH`，本次实际使用的是上表 Chromium 156。复现时若没有 Chromium，先运行 `python -m playwright install chromium`，或用 `CHROME_PATH` 指定 Chrome/Chromium。

## 2. 启动与测试命令

```powershell
# 终端 1：启动本地 CiteGuard 服务
$env:PYTHONPATH = "src"
python -m uvicorn web.app:app --host 127.0.0.1 --port 8013

# 终端 2：真实浏览器验收
$env:PYTHONIOENCODING = "utf-8"
python scripts/verify_extension.py
```

本次实际执行的命令与结果：

```powershell
$env:PYTHONIOENCODING="utf-8"
python scripts/verify_extension.py 2>&1 |
  Tee-Object -FilePath "$env:TEMP\cg_ext_verify_run4.log"
exit $LASTEXITCODE
```

- 退出码：`0`
- stdout 关键字段：`"ok": true`、`"failures": []`
- 检查项：全部通过（见 §5）
- 截图：7 张（见 §4）
- 可选参数：`--extension`、`--base-url`、`--shots-dir`、`--headless`
  - 本次最终证据使用 headed 模式；`--headless` 只做过扩展加载探测，未作为最终截图证据。
- 脚本退出码约定：`0` 全部必需检查通过；`1` 有检查失败或运行异常；`2` 本地服务/浏览器/Playwright 环境不可用。

## 3. 测试方法与自动化边界

`scripts/verify_extension.py` 的实际流程：

1. 探测本地服务（`GET /live` 200），否则退出码 2。
2. 启动 Playwright persistent context，带
   `--disable-extensions-except=<extension/v2>` 与 `--load-extension=<extension/v2>`。
3. 等待 MV3 service worker，读取 `chrome.runtime.getManifest()`。
4. 打开 `chrome://extensions/`，在 shadow DOM 中读取扩展卡片，检查启用状态和错误按钮。
5. 打开 `sidepanel.html` 扩展页，读取 `/live` 与 3 个公开网页的段落选区。
6. 用与 `background.js` 相同的消息结构
   `{type: "citeguard-live-request", request}` 从 service worker 发给面板；
   `request` 为 `{id, claim, pageUrl, pageTitle, createdAt}`。
7. 用 Playwright `expect_response` 捕获面板真实发出的 `POST /api/live/check`，校验
   HTTP 200、出站 `claim/page_url/page_title` 与选区完全一致、响应 label 合法、
   面板 label 文字与 API 一致。
8. 把 endpoint 临时改为 `http://127.0.0.1:9`，确认面板进入错误状态并截图。
9. 输出 JSON、退出码；任何必需检查失败都会使 `ok` 为 `false`。

### 3.1 为什么不是“右键点击菜单项”

右键菜单是 Chromium 的原生 UI，Playwright 无法定位或点击菜单项；同样，点击工具栏图标把
side panel 真正停靠到浏览器侧边的用户手势也无法自动化。脚本因此复用
`background.js` 在菜单点击后执行的同一条交接路径：

- 向扩展页发送 `citeguard-live-request` runtime 消息；
- 写入 `chrome.storage.local` 的 `cg_live_request`；
- 面板收到后调用真实 API。

为排除“storage 回退”把消息路径掩盖掉：

- **本地 `/live` 用例只发 runtime 消息、不写 storage**（`write_storage=False`），
  仍然捕获到真实 API 请求，证明消息通道本身可用；
- 3 个公开网页用例使用 runtime 消息 + storage，和真实 `background.js` 的双通道一致。

面板是在扩展页 `sidepanel.html` 的普通标签页中打开的，而不是由工具栏手势停靠的 side
panel。页面加载的是**同一份** `sidepanel.html` / `sidepanel.js`，不是 mock。未验证的是
“菜单项/工具栏手势 → 真正侧边栏”这段浏览器原生行为，见 §6。

### 3.2 一个已知的无害控制台提示

`chrome.runtime.sendMessage` 的回调会记录：

```text
The message port closed before a response was received.
```

原因是扩展的消息监听器没有调用 `sendResponse()`，Chromium 在通道关闭时会产生这个
`lastError`；**消息已经送达**，面板也完成了 API 调用。本地用例没有写 storage 仍然拿到
200 响应，可以排除“只是 storage 触发”的解释。这不是扩展运行错误；本次唯一一条其它
console 错误是故意把 endpoint 指向禁止端口 9 触发的：

```text
[sidepanel] console.error: Failed to load resource: net::ERR_UNSAFE_PORT
```

它是 §4.4 错误处理用例的预期结果，不是加载错误。

## 4. 实测结果

### 4.1 扩展加载与 manifest

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| MV3 service worker 启动 | 通过 | `chrome-extension://ccdjaijaflemilhobcjbackhkoioohnh/background.js` |
| manifest 可读取 | 通过 | v3 / 0.2.0 / 最低 Chrome 116 |
| `chrome://extensions` 显示卡片 | 通过 | 卡片名称、版本 0.2.0、启用 |
| 扩展处于启用状态 | 通过 | `enabled: true` |
| 卡片没有错误按钮 | 通过 | `error_button_present: false`、`error_button_visible: false` |
| side panel 声明 | 通过 | `sidepanel.html` |
| host permissions 只指向本地 | 通过 | `127.0.0.1` / `localhost` |

截图：[phase-54-extension-loaded.png](evidence/shots/phase-54-extension-loaded.png)

### 4.2 本地 `/live`：仅 runtime 消息触发真实 API

- 页面：`http://127.0.0.1:8013/live`
- 标题：`Live 单句核验 · 划一句查摘要 · 引证卫士 CiteGuard`
- 选区 claim（146 字）：

  > 把网页或论文里的一句断言贴进来。CiteGuard 会去 OpenAlex / Crossref 取候选论文的公开摘要，
  > 给出「支持 / 部分支持 / 矛盾 / 无证据」四档判断，并把支持或反驳这句话的原文句逐字标出来。
  > 不用安装浏览器扩展，也能把「划一句 → 检索候选 → 四档判定」走完。

- 出站请求（真实网络，Playwright 捕获）：

  ```json
  {
    "claim": "把网页或论文里的一句断言贴进来。CiteGuard 会去 OpenAlex / Crossref 取候选论文的公开摘要， 给出「支持 / 部分支持 / 矛盾 / 无证据」四档判断，并把支持或反驳这句话的原文句逐字标出来。 不用安装浏览器扩展，也能把「划一句 → 检索候选 → 四档判定」走完。",
    "page_url": "http://127.0.0.1:8013/live",
    "page_title": "Live 单句核验 · 划一句查摘要 · 引证卫士 CiteGuard"
  }
  ```

- 响应：HTTP `200`，`ok: true`，label `no_evidence`，confidence `0.0`
- reason：`未配置判定模型；本地规则未在候选摘要中找到与引用句关键词/数字足够重合的句子`
- 面板：`无证据 · no_evidence`，置信度 `0%`
- 截图：[phase-54-extension-local-live.png](evidence/shots/phase-54-extension-local-live.png)
  （本地页面；脚本已选中段落并发起请求）
- 结果截图：[phase-54-extension-live-result.png](evidence/shots/phase-54-extension-live-result.png)

### 4.3 三个真实公开网页

所有页面均为本次实际 `goto` 打开，HTTP 200；claim 来自页面段落选区；页面上下文与
出站 payload 逐字段一致。

| # | 页面 URL | 页面标题 | HTTP | label | 面板 |
| --- | --- | --- | --- | --- | --- |
| 1 | `https://example.com/` | `Example Domain` | 200 | `no_evidence` | 无证据 · no_evidence |
| 2 | `https://www.iana.org/help/example-domains` | `Example Domains` | 200 | `no_evidence` | 无证据 · no_evidence |
| 3 | `https://docs.python.org/3/tutorial/index.html` | `The Python Tutorial — Python 3.15.2 documentation` | 200 | `partial` | 部分支持 · partial |

#### 4.3.1 `example.com`

- claim：

  > This domain is for use in documentation examples without needing permission. This is not
  > a service; avoid relying on it for testing and monitoring purposes.

- 出站 payload：`claim` 与选区一致；`page_url = "https://example.com/"`；
  `page_title = "Example Domain"`。
- 响应：200，`ok: true`，label `no_evidence`，confidence `0.0`。
- 截图：[phase-54-extension-example.png](evidence/shots/phase-54-extension-example.png)

#### 4.3.2 IANA Example Domains

- claim：

  > A number of domains such as example.com and example.org are maintained for documentation
  > purposes. These domains may be used as illustrative examples in documents without prior
  > coordination with us. They are not available for registration or transfer.

- 出站 payload：`page_url = "https://www.iana.org/help/example-domains"`；
  `page_title = "Example Domains"`；claim 与选区一致。
- 响应：200，`ok: true`，label `no_evidence`，confidence `0.0`。
- 截图：
  [phase-54-extension-iana-example-domains.png](evidence/shots/phase-54-extension-iana-example-domains.png)

#### 4.3.3 Python Tutorial

- claim：

  > This tutorial is designed for programmers that are new to the Python language, not
  > beginners who are new to programming.

- 出站 payload：`page_url = "https://docs.python.org/3/tutorial/index.html"`；
  `page_title = "The Python Tutorial — Python 3.15.2 documentation"`；claim 与选区一致。
- 响应：HTTP 200，`ok: true`，label `partial`，confidence `0.433`。
- reason：`未配置判定模型，使用本地规则兜底：候选摘要句关键词覆盖 33%`
- 证据句（来自 `Programming with Python`，DOI
  `10.2174/9789815179637123010014`）：

  > This will surely increase the reader's comprehension of the intricacies of Python and
  > demonstrate the efficiency of the language in making the programming simple.

- 面板：`部分支持 · partial`，置信度 `43%`。
- 截图：
  [phase-54-extension-python-tutorial.png](evidence/shots/phase-54-extension-python-tutorial.png)

### 4.4 错误处理：本地服务不可达

- 操作：把扩展 endpoint 临时设为 `http://127.0.0.1:9`，再触发一次请求。
- 面板状态：`error`
- 实际提示：

  > 无法连接本地服务（http://127.0.0.1:9）。请确认服务已启动，并在“设置”里检查地址。

- 截图：[phase-54-extension-error.png](evidence/shots/phase-54-extension-error.png)
- 控制台：`[sidepanel] console.error: Failed to load resource: net::ERR_UNSAFE_PORT`
  —— 这是端口 9 被 Chromium 禁止导致的**预期**网络错误，用于验证客户端错误分支；
  不是扩展加载/脚本异常。
- 验证后脚本把 endpoint 恢复为 `base_url` 并清理 `cg_live_request`。

### 4.5 本轮运行汇总

- `ok: true`
- `failures: []`
- 检查项全部通过，包括：
  - `本地用例仅靠 runtime 消息触发真实 API`
  - `至少 3 个真实公开网页完成 API 核验：成功 3 个`
  - `截图文件全部存在：7 张`
- 唯一 console 错误是 §3.2 所述、故意触发的 `ERR_UNSAFE_PORT`。

## 5. 截图清单

全部为 1440×960、由 Playwright 在本次运行中直接保存：

| 文件 | 内容 | 大小 |
| --- | --- | ---: |
| [phase-54-extension-loaded.png](evidence/shots/phase-54-extension-loaded.png) | `chrome://extensions` 中已加载的扩展卡片（启用、无错误按钮） | 39,590 B |
| [phase-54-extension-local-live.png](evidence/shots/phase-54-extension-local-live.png) | 本地 `/live` 页面，脚本已选中段落并发起请求 | 637,712 B |
| [phase-54-extension-live-result.png](evidence/shots/phase-54-extension-live-result.png) | 面板显示真实 API 结果：无证据 / no_evidence | 80,827 B |
| [phase-54-extension-example.png](evidence/shots/phase-54-extension-example.png) | example.com 的真实段落选区 | 54,229 B |
| [phase-54-extension-iana-example-domains.png](evidence/shots/phase-54-extension-iana-example-domains.png) | iana.org 的真实段落选区 | 116,992 B |
| [phase-54-extension-python-tutorial.png](evidence/shots/phase-54-extension-python-tutorial.png) | docs.python.org 的真实段落选区 | 109,575 B |
| [phase-54-extension-error.png](evidence/shots/phase-54-extension-error.png) | 服务不可达时的真实错误状态 | 49,116 B |

## 6. 已验证 / 未验证

### 6.1 已验证

- [x] 真实 Chromium 通过 `--load-extension` 加载 `extension/v2`
- [x] MV3 service worker 启动，manifest 可读取，版本与权限符合预期
- [x] `chrome://extensions` 卡片显示、启用、无错误按钮
- [x] 本地 `/live` 选区 → runtime 消息（不写 storage）→ 真实 API 200
- [x] 3 个真实公开网页选区 → 消息 → 真实 API 200，label 合法
- [x] 出站 `claim` / `page_url` / `page_title` 与页面选区逐字段一致
- [x] 面板 label/置信度/reason 与 API 响应一致
- [x] 服务不可达时面板显示错误状态与中文提示
- [x] 7 张真实截图存在

### 6.2 未验证（不要当作已通过）

- [ ] 右键菜单项的实际点击（原生 UI，脚本只复用菜单点击后的交接路径）
- [ ] 工具栏图标打开**真正停靠的 side panel** 的浏览器手势；本次是在普通标签页加载
      `sidepanel.html`，UI/JS 相同但不是停靠形态
- [ ] 系统 Google Chrome（本机未安装）；本次使用 Playwright Chromium 156
- [ ] Microsoft Edge 加载扩展（仅记录版本 157.0.4341.46，未实际加载）
- [ ] Chrome Web Store / CRX 打包安装流程
- [ ] 登录页、PDF、付费墙、CSP 限制页
- [ ] 跨平台（仅 Windows 11）
- [ ] 判定模型质量：本机未配置模型，标签为本地规则兜底，不代表模型能力
- [ ] 网页全文阅读/事实核查：扩展只把选中句和页面上下文发给本地服务，服务只读公开摘要

## 7. 手工验收步骤（覆盖未自动化部分）

1. 按 §2 启动 `127.0.0.1:8013` 服务。
2. 打开 Chrome/Edge 116+ 的 `chrome://extensions`，开启开发者模式，选择
   **加载已解压的扩展程序**，指向 `extension/v2`。
3. 打开任意公开网页，选中一句有实际断言的句子。
4. 右键，点击 **用 CiteGuard Live 核验选中句**。
5. 确认 side panel 打开，claim 与页面标题/URL 正确，点击核验；确认面板出现
   `支持 / 部分支持 / 矛盾 / 无证据` 之一、置信度、reason、证据句（若有）。
6. 在扩展设置里把服务地址改为 `http://127.0.0.1:9`，再试一次，确认出现
   “无法连接本地服务”提示；改回 `http://127.0.0.1:8013`。
7. 停止本地服务后再试，确认同样进入错误状态；重启服务后恢复。

## 8. 接口与错误码（本次实际涉及的客户端行为）

`sidepanel.js` 向 `POST {endpoint}/api/live/check` 发送：

```json
{
  "claim": "选中的句子",
  "page_url": "当前页面 URL",
  "page_title": "当前页面标题"
}
```

服务端 schema：`claim` 去空白后 1–500 字必填；`page_url` ≤2048；`page_title` ≤300；
成功返回 `{ok: true, label, confidence, reason, evidence, candidates}`，其中
`label ∈ {support, partial, contradict, no_evidence}`。

面板对异常的实际处理：

| 情况 | 面板行为 |
| --- | --- |
| 400 | 显示请求无效提示（句子为空或超长） |
| 401 | 提示接口需要访问令牌 |
| 404 | 提示接口或候选来源不存在，检查本地服务版本 |
| 429 | 提示请求过于频繁，稍后再试 |
| 500 / 503 | 提示本地服务内部错误/暂不可用 |
| 网络不可达（`TypeError`） | `无法连接本地服务（<endpoint>）。请确认服务已启动，并在“设置”里检查地址。` |
| 15 秒超时 | `请求超时` |
| 响应缺少合法 label | 进入错误状态，不渲染假结果 |

本次错误用例命中“网络不可达”分支，与上表一致。

## 9. 已知限制

- 本机服务未配置判定模型，`partial` / `no_evidence` 等结果是本地关键词/数字规则兜底，
  不是模型判断；报告只证明扩展到 API 的链路和页面上下文传递。
- 外部页面内容会随时间变化；本次截图对应 2026-11-13 UTC 运行时的页面。
- 公开网页只覆盖 3 个稳定页面，不覆盖需要登录、PDF、付费墙或严格 CSP 的页面。
- 扩展只发送选中句和页面 URL/标题；不读取网页全文，不做事实核查。
- 机器可读结果只打印到 stdout，未额外写入 JSON 文件；本报告的表格与截图是本次运行的
  直接记录。
