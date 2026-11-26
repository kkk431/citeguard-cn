# 可观测性、许可与回归（H1，1.7.47）

## 请求可观测

- 所有响应带 `X-Request-ID`（沿用请求头，否则生成 12 位十六进制）和 `X-Response-Time-ms`。
- `GET /api/health` 返回 `version`、`offline`、`supported`、`uptime_seconds`、`requests_total`。
- `GET /api/metrics` 返回进程内累计请求数、按状态码计数和运行时长。
- 不记录请求体、查询串、页面 URL、访问令牌、模型 key；计数只存在进程内，重启清零。

## 许可

- H1 无新增第三方依赖；请求 ID 使用标准库 `uuid`，计数使用 `collections.Counter`。
- 许可清单仍以 `docs/licenses.md`、`THIRD_PARTY_NOTICES.md`、资源清单 PDF 为准。

## 回归

```bash
python scripts/regression_check.py
python scripts/regression_check.py --base http://127.0.0.1:8013 --pdf data/real_corpus/hanspub_152575.pdf
```

依次跑：pytest、verify_artifacts、audit_evidence、test_licenses；给 `--base` 时追加 e2e_smoke。
结果写 `data/experiments/opt_h1_regression_<UTC>.json` 与 `opt_tests_<UTC>.txt`；任一步非 0 则退出码 1。


## 实测（1.7.47）

- `X-Request-ID` 透传；health/metrics 返回 200；metrics 实测 `by_status {"200":16,"202":1}`。
- 一键回归：pytest 1074 passed/10 skipped、verify 137/137、audit 259/134、licenses 通过、e2e 14/14；JSON/日志见 E121。
