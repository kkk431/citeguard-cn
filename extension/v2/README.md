# CiteGuard Live v2（浏览器扩展）

选中网页上的一句话 → 右键 **“用 CiteGuard Live 核验选中句”** → 侧边栏显示
`support` / `partial` / `contradict` / `no_evidence` 四档标签、置信度、候选来源和
可逐字核对的摘要证据句。

扩展本身不判断真假，也不读网页全文。它把**选中的那一句**发给本地
CiteGuard 服务；服务检索 OpenAlex / Crossref 的候选文献摘要，返回可解释的
四档结果。没有逐字证据时，`evidence` 必须为 `null`。

## 加载步骤（Chrome / Edge，需 116+）

1. 启动本地服务（路由由项目主程序提供）：

   ```bash
   cd citeguard
   PYTHONPATH=src python -m uvicorn web.app:app --host 127.0.0.1 --port 8013
   ```

   若主程序默认端口不是 8013，请用 `--port` 指定，或在扩展设置里改成实际端口。

2. 打开 `chrome://extensions`（Edge 为 `edge://extensions`），启用“开发者模式”。
3. 点击“加载已解压的扩展程序”，选择本目录 `extension/v2/`。
4. 点击工具栏中的 CiteGuard Live 图标打开侧边栏；首次可在“设置”里确认本地
   服务地址（默认 `http://127.0.0.1:8013`，扩展会自动追加 `/api/live/check`）。
5. 在任意可选中文本的网页上选一句话，右键 → **用 CiteGuard Live 核验选中句**。

> 内置页面 `options.html` 可保存地址并“测试连接”。如果返回 404，说明本地服务
> 还没有接入 `POST /api/live/check`；如果返回 401，说明服务开启了访问令牌，
> 需要服务端为 Live 接口放行（本扩展不保存令牌）。

## 与旧版（`extension/`）的差异

| 项目 | 旧版 v1 | v2 |
| --- | --- | --- |
| 入口 | 工具栏 popup，手动粘贴/选择 | 右键选中句自动送入 + 侧边栏 |
| 默认端口 | `8010` | `8013` |
| 接口 | `POST /api/support/check` | `POST /api/live/check` |
| 标签 | support/partial/contradict/no_evidence/not_checked | 四档：support/partial/contradict/no_evidence |
| 结果 | 单条证据 | 四档 + 置信度 + 候选列表 + 逐字证据句 |
| 服务地址 | 代码内固定 | 设置页可配置（默认 8013） |

v1 仍保留在 `extension/`，不影响旧版使用。

## 数据与网络

- 只提交：`claim`（选中句）、`page_url`（当前页 URL）、`page_title`（当前页标题）。
- 不提交网页正文、不提交登录信息、不下载 PDF。
- 本地服务可能向 OpenAlex / Crossref 发起元数据检索；扩展不直接访问这些第三方。
- 扩展使用 `host_permissions` 访问 `127.0.0.1` / `localhost`；服务须返回 CORS
  友好的响应（或由扩展的 host permission 放行）。若服务设置了访问令牌，见上文。

## 边界（必须保留）

1. **只核验选中句**：不读取网页全文，不核查整篇文章。
2. **只看候选摘要片段**：不是系统综述，也不是事实核查；没有全文时证据有限。
3. **四档不是真假判决**：`no_evidence` 只表示没有找到可判断的摘要证据，不表示
   句子为假；`support` 也只表示候选摘要中的一句话支持该句。
4. **证据句必须逐字出现**：服务端会核对 quote 是否为候选摘要的精确子串；
   对不上就不返回证据（§Live API 契约见 `docs/live.md`）。
5. **不伪造页面/截图**：真实页面清单与验证状态记录在 `docs/live.md`。

## 本地检查

- JS 语法：`node --check extension/v2/background.js && node --check extension/v2/sidepanel.js && node --check extension/v2/options.js`
- 服务端单测：`pytest tests/test_live_check.py -q`
- 无模型/无网络时，服务应返回 `no_evidence` 并给出人话原因，而不是报错或编造来源。
