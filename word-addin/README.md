# Word 任务窗格（预览版）

在 Word 里选中一句话，任务窗格会把它填成「引用句」，再粘贴摘要/证据片段，点「核验」后调用
`POST /api/support/check`，显示支持 / 部分支持 / 矛盾 / 无证据四档结果。

## 本地加载

1. 启动 CiteGuard-CN：`python -m uvicorn web.app:app --port 8010`（默认 `127.0.0.1:8010`）。
2. 打开 Word →「插入」→「我的加载项」→「上传我的加载项」→ 选择 `word-addin/manifest.xml`。
3. 任务窗格默认地址是 `https://localhost:8010/word/taskpane`；如果本地是 http，请把 manifest 里的
   `https://localhost:8010` 改成实际地址并重新上传（Office 要求 HTTPS 或受信任的 localhost）。
4. 选中文字 → 打开任务窗格 → 粘贴证据 → 核验。

## 诚实边界

- **没有在真实 Word 客户端里做过加载与交互测试**：本目录提供 manifest、任务窗格页面与接口接线，
  属于可审阅的实现，不是"已验证可用"的成品；正式使用前必须在 Word 里实测。
- 走的是同一个 `/api/support/check`；模型未配置/离线时接口返回 503，页面会如实显示错误。
- 不读取整篇文档，只取用户选中的文字；权限声明为 `ReadDocument`。
