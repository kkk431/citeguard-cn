# CiteGuard-CN 缺陷记录（BUGS-FOUND）

- 记录时间：2026-10-22 22:25（Asia/Shanghai）
- 最终状态：**5 个缺陷全部已修复**；`pytest tests -q` 全绿（157 passed）。
- 验证环境：Python 3.12.14 + `.pylibs`（`PYTHONPATH=src;.pylibs`）
- 说明：本次发布期间工作区有**并行修改**（`gbt7714.py`、`pdf_extract.py`、`config.py`、
  `report.py`、`pipeline.py`、`web/app.py`、`metadata_verify.py`、`jobs.py` 在
  22:14–22:21 之间被其他成员更新，版本号 0.2.0 → 0.3.0）。发布侧只新增测试与部署资产，
  **没有修改 `src/citeguard/**` 业务逻辑**；下表记录发现、修复位置与回归用例。

## 缺陷总览

| ID | 严重度 | 位置 | 现象 | 状态 | 回归用例 |
|---|---|---|---|---|---|
| BUG-1 | 高 | `src/citeguard/metadata_verify.py`：`lookup_doi_status()` / `verify_reference()` | DOI 端点返回 `HTTP 200` 但响应体解析不出候选记录时，`lookup_doi_status()` 返回 `("", "resolved")`，`_pick_best(ref, [])` 对空列表取 `ranked[0]` 抛 `IndexError`，整个分析任务失败；按设计应降级为 `Unknown` | ✅ 已修复（22:19）：`verify_reference()` 增加 `if not doi_cands: return VerifyResult(status="Unknown", ...)` | `tests/test_metadata_verify.py::test_doi_resolved_without_candidates_degrades_gracefully` |
| BUG-2 | 中 | `src/citeguard/pdf_extract.py::extract_text()` | `.txt` 用 `encoding="utf-8"` 读取，UTF-8 BOM 保留在首行，`INDEX_RE` 匹配不到 `[1]`，**静默丢失第一条参考文献** | ✅ 已修复（22:16）：`_read_text_file()` 按 `utf-8-sig → utf-8 → gb18030` 回退读取 | `tests/test_pdf_extract.py::test_utf8_bom_does_not_drop_first_reference` |
| BUG-3 | 中 | `web/app.py::analyze()` | 先 `manager.create()` 再校验后缀/大小；非法后缀（400）、超大文件（413）、空文件（400）都会残留永远不会执行的 `queued` 任务，首页“最近任务”出现幽灵条目 | ✅ 已修复（22:21）：后缀校验前置，异常分支 `manager.discard(job_id)`；新增空文件 400 | `tests/test_web.py::test_rejected_upload_does_not_create_job`、`tests/test_hardening.py::test_empty_upload_is_rejected_without_leaving_a_job` |
| BUG-4 | 中 | `src/citeguard/gbt7714.py::check_punctuation()` | 检查 `[J]` **之前**的字符是否为 `.`，导致规范写法 `题名[J]` 中题名末字被判为“缺少 `.`”，每条文献白扣 12 分 | ✅ 已修复（22:14）：仅当出现 `题名.[J]` 时报错 | `tests/test_gbt7714.py::test_canonical_entry_has_no_punctuation_error` |
| BUG-5 | 中 | `src/citeguard/cli.py` + `src/citeguard/report.py::_stats()` | `--no-verify` 传入 `[None] * n`，`_stats()` 读取 `v.status` 抛 `AttributeError`，CLI 直接崩溃；而这是公开的离线用法 | ✅ 已修复（22:19）：`_stats()` 对 `None` 按 `Unknown` 计数 | `tests/test_cli.py::test_cli_no_verify_flag_works` |

## 复现与修复细节

### BUG-1：DOI 200 但无候选 → 崩溃

```python
# Crossref / OpenAlex DOI 查询都返回 200 但 JSON 为空（或结构异常）
verify_reference(Reference(..., doi="10.1234/abc"))
# 修复前：IndexError: list index out of range  (metadata_verify.py::_pick_best)
# 修复后：status == "Unknown", doi_status == "resolved"
```

### BUG-2：UTF-8 BOM 丢首条文献

```python
path.write_bytes(b"\xef\xbb\xbf" + "[1] 张三...\n[2] 李四...".encode())
# 修复前：parse_reference_list(extract_text(path)) 只有 1 条（[1] 被静默丢弃）
# 修复后：2 条
```

### BUG-3：被拒绝的上传残留任务

```bash
curl -s -o /dev/null -w '%{http_code}\n' -F 'file=@evil.exe' http://127.0.0.1:8000/api/analyze
# 修复前：400，但 data/jobs/<新 id>.json 已出现（status=queued）
# 修复后：400 且任务被 discard()，data/jobs 无新增
```

### BUG-4：GB/T 7714 标点误报

规范写法是 `题名[J]. 期刊...`；修复前 `(.?)\[J\]` 捕获题名末字并判“缺少 `.`”，
修复后只有 `题名.[J]` 才报错，规范条目 0 error。

### BUG-5：CLI `--no-verify` 崩溃

```bash
PYTHONPATH=src python3 -m citeguard.cli --input refs.txt --refs-only --no-verify --out out/x
# 修复前：AttributeError: 'NoneType' object has no attribute 'status'
# 修复后：正常输出报告，缺失核验记为 Unknown
```

## 其他观察（不阻断发布）

1. **`.docx` 依赖声明**：`pdf_extract.py` 新增 `python-docx` 时 `requirements.txt` 未同步。
   发布侧已补充 `python-docx>=1.1`（属于部署配置，不是业务逻辑）；`requirements.lock.txt`
   也已包含 `python-docx==1.2.0`。`tests/test_pdf_extract.py`、`tests/test_docx_input.py`、
   `tests/test_web.py::test_e2e_upload_docx` 覆盖该路径。
2. `metadata_verify.verify_reference()` 对 DOI 变体逐个尝试时，遇到 `status == "error"`
   会立即 `break` 返回 `Unknown`，不再尝试去掉 `_c` / 小写等其余变体；网络抖动时可能
   本可命中的 DOI 被判为 Unknown（稳健性建议，非阻断）。
3. `_cached_json` / `_cached_text` 只缓存成功响应，HTTP 失败不落缓存；离线重跑会反复
   重试网络（可使用预热缓存目录规避）。
4. Web 端允许 `.doc` 后缀，但 `extract_text()` 会抛“请另存为 .docx”的可读错误，
   任务以 `error` 结束（设计取舍）。
5. CLI 未接入 claim-support 判定（仅 Web 端有），属于功能差异，不是回归。
6. Web 服务无鉴权 / 限流；`docs/deployment.md` 已要求默认绑定 `127.0.0.1`、
   走 SSH 隧道或防火墙，不直接暴露公网。

## 相关命令

```bash
# 全量测试（离线）
PYTHONPATH=src:.pylibs python3 -m pytest tests -q        # 157 passed

# 交付物一致性
PYTHONPATH=src python3 scripts/verify_artifacts.py       # [OK] all 32 checks passed

# 打包
PYTHONPATH=src python3 scripts/package_deliverable.py    # dist/citeguard-cn-0.3.0.zip
```
