# Word 任务窗格（预览版）

在 Word 里选中一句话，任务窗格会把它填成「引用句」，再粘贴摘要/证据片段，点「核验」后调用
`POST /api/support/check`，显示支持 / 部分支持 / 矛盾 / 无证据四档结果。

## 本地加载（HTTPS）

Office 加载项要求 HTTPS（或受信任的 localhost）。本仓库用 8443 的 HTTPS 演示：

1. 生成本地受信任证书（只需一次）：

   ```bash
   python scripts/word_cert.py
   ```

2. 启动 HTTPS 服务：

   ```bash
   python -m uvicorn web.app:app --host 127.0.0.1 --port 8443 \
     --ssl-certfile out/word_tls/cert.pem --ssl-keyfile out/word_tls/key.pem
   ```

3. 注册 dev 加载项（当前用户，无需管理员）：

   ```powershell
   $key = 'HKCU:\Software\Microsoft\Office\16.0\WEF\Developer'
   New-Item -Path $key -Force | Out-Null
   New-ItemProperty -Path $key -Name 'cd8210d4-1e00-4de0-8736-561959ff4e8b' \
     -Value (Resolve-Path word-addin/manifest.xml).Path -PropertyType String -Force
   ```

4. 重启 Word，打开「插入 → 我的加载项」，应能看到「引证卫士」；
   插入后任务窗格指向 `https://localhost:8443/word/taskpane`。

## 诚实边界

- HTTPS 端点、证书信任、dev 注册、Word 启动都已实测；**任务窗格在 Word 里的手动插入与交互尚未完成视觉验证**。
- 走的是同一套 `/api/support/check`；模型未配置/离线时接口返回 503，页面会如实显示错误。
- 不读取整篇文档，只取用户选中的文字；权限声明为 `ReadDocument`。
