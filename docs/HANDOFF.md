# 今日收工 & 明天开工说明

> 2026-10-23 00:2x 收工。代码已全部提交并推送：`3627b29`（工作区干净）。
> 本地演示服务已关闭（不是代码问题）。

## 1. 为什么"连不上服务器"

演示服务默认只监听本机回环地址，**别的设备/外网本来就访问不到**：

- 本地：`uvicorn web.app:app --host 127.0.0.1 --port 8010` → 只有本机 `http://127.0.0.1:8010` 能开。
- 要手机/别人访问：加 `--host 0.0.0.0` 并放行防火墙 8010，或用 SSH 隧道（推荐）：
  ```bash
  ssh -L 8010:127.0.0.1:8010 jxy-2
  # 然后本机浏览器打开 http://127.0.0.1:8010
  ```
- 远程服务器项目路径：`/data/xyjiang/aic_mental/citeguard`，启动方式：
  ```bash
  cd /data/xyjiang/aic_mental/citeguard
  PYTHONPATH=src:.pylibs python3 -m uvicorn web.app:app --host 0.0.0.0 --port 8000
  ```
  注意：服务器上先前跑的 uvicorn 可能还是旧代码，重启后才会带上今天的改动。

## 2. 明天一键开工

```powershell
cd D:\ai+ky\citeguard
$py = "C:/Users/hejiaxuan/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe"
$env:PYTHONPATH = "src;.pylibs"; $env:PYTHONIOENCODING = "utf-8"
$env:DEEPSEEK_API_KEY = "..."   # 支持度判定用，不写进任何文件

# 自检
& $py -m pytest tests -q                       # 220 项，全离线

# 起工作台（演示/自用）
& $py -m uvicorn web.app:app --host 127.0.0.1 --port 8010
```

数据与产物：`data/library/library.json`（本地题录库，已 git-ignore）、`data/experiments/`（评测证据）、`out/`（临时文件）。

## 3. 当前状态（一句话）

输入解析（PDF/Word/扫描件 OCR）、GB/T 格式检查、引文真实性核验（在线 + 本地题录库）、支持度判定、报告与导出全部可用；220 项测试通过。已知边界写在 `docs/plan.md`。

## 4. 明天优先级

1. **OCR 后处理**：修 `[J]`→`[]` 之类的类型码/标点丢失，提升扫描件格式检查可用性。
2. **核验准确率**：作者中英文混写归一化（减少 Minor 误判）、题名相似度阈值复调。
3. **性能**：同一文献去重后再查询；大 PDF 分页进度提示。
4. **真实用户测试包**：任务脚本 + 指标 + 问卷（需要真人执行）。

## 5. 今天最后一批改动（已推送）

- 支持度 prompt v3：macro-F1 0.7951 → **0.9005**（v4 few-shot 试了更差，未采用）
- 本地题录库：多文件导入、文件夹导入、BibTeX/RIS 导出、摘要接入支持度判定
- 扫描件 OCR（可选依赖）+ OCR 噪声解析加固
- 格式引擎：作者数规则、DOI/年份/页码校验、文档级一致性检查；E4 漂移检出 10/30 → **15/30**
- 数据源限流/宕机时返回「无法核验」而不是「未找到匹配」
- 网页：批量上传、CSV 导出、格式错误筛选、手机宽度修正
