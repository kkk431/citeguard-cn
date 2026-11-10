# 引证卫士 CiteGuard 划词核验（浏览器扩展）

选中一段带引用的文字 → 右键「用引证卫士核验选中文字」→ 在弹窗里贴上证据片段，
直接得到 `support / partial / contradict / no_evidence` 四档判定。

## 安装

1. Chrome / Edge 打开 `chrome://extensions`，开启「开发者模式」。
2. 「加载已解压的扩展程序」，选本目录 `extension/`。
3. 本地启动引证卫士：`uvicorn web.app:app --port 8010`（或已在跑的演示服务）。
4. 点扩展图标，在「服务地址」里填 `http://127.0.0.1:8010`。

## 它调用什么

```http
POST /api/support/check
{"claim": "该方法的准确率提升了 2.3%。", "evidence": "……实验段原文……"}
```

返回 `label / confidence / reason / evidence / audit / prompt_version`。
判定走的是产品同一条支持度链路；扩展本身不存文本、不上传第三方。

## 边界

- 只判断「这段证据是否支持这句话」，不查引用是否真实存在，也不做 GB/T 格式。
- 需要本地服务在跑；服务不可用时弹窗会直接报错，不会伪造结果。
