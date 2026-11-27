# Batch 2.2 / 2.3 / 2.4：既有能力的证据化收口

这三项不再新造算法；它们已是产品现有能力，本轮只做可复核的证据整理，避免把旧功能当成“新方法”。

## 2.2 版式感知解析

- 实现：`src/citeguard/pdf_extract.py`（pdfplumber + pypdfium2 回退）、`src/citeguard/refs_layout.py`（pypdfium2 行框）、`src/citeguard/reference_parser.py`。
- 真实语料：22 篇、529 条参考文献、clean 1.0（`data/experiments/parse_real.json`）。
- 盲测：第 5 次预注册 3 篇均过 95% 健康率；第 4 次 Gemma 仍有边界，已如实记录。
- 本轮没有新增解析算法，因此不宣称“新方法”；报告 2.2 是基线与边界，不是提升数字。

## 2.3 工程可靠性

- 已存在：SQLite 历史索引、任务 JSON 持久化/中断重跑（B1）、结果缓存（B2）、请求 ID/延迟/`/api/metrics`（H1）、回归脚本 `scripts/regression_check.py`。
- 验证：全测 **1162 passed, 10 skipped**；`verify_artifacts` 137/137；回归脚本 5 步 exit 0（含 e2e 14/14）。
- 边界：单机 SQLite，不是多节点队列；缓存为本地磁盘；不宣称高可用。

## 2.4 安全/隐私

- 默认：`CITEGUARD_ACCESS_TOKEN` 为空（本机默认开放）、`CITEGUARD_RATE_LIMIT_PER_MIN=120`（POST `/api/*`）。
- 页面预检：host allowlist（arXiv/PMC/Wikipedia）+ 逐跳重定向校验，阻断 SSRF。
- 日志：只记录方法/路径/状态/延迟/请求 ID，不记录请求体、URL 查询参数或凭据。
- 依赖：核心 `requirements.txt` 无 PyMuPDF/fitz；可选 PyMuPDF 标 AGPL opt-in；`tests/test_licenses.py` 4/4。
- 已验证：H3 3/3 定向测试、`tests/test_live_page.py` 27 passed、`tests/test_observability.py` 2 passed。
- 边界：本机默认无 token 只适合 loopback；公网部署必须设 token 并前置 TLS/反代。

## 证据

`data/experiments/opt_b2_2_3_4_baseline_2026-11-27.json`
