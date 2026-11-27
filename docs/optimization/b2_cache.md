# B2 结果缓存与只补失败

目标：同一批论文重复分析时，不做重复的解析与核验；批量重跑只补失败项，且热缓存绝不冒充冷启动成绩。

## 1. 实现

- `src/citeguard/jobs.py`
  - `result_cache_key(file_sha256, options, versions)`：缓存键 = 报告结构版本 + 文件内容 SHA-256 + 规范化 options + 规范化 versions，输出 32 位十六进制。
  - `ResultCache`：磁盘缓存，条目在 `data/cache/results/<前2位>/<key>.json`；原子写入（临时文件 + `os.replace`）；损坏/结构不符按 miss 处理；可 `invalidate(key)`、`clear()`、`stats()`。
  - `BatchRunner`：批量记录保存在 `data/batches/<batch_id>/batch.json`，每条含 `sha256`、`cache_key`、`status`（`pending`/`done`/`error`）、`source`（`processed`/`cache`/`reused`）、`error`、`report_path`。
    - `run(batch_id, process)`：成功项优先读结果缓存；已有报告的成功项直接复用，不再调用分析器。
    - `retry_failed(batch_id, process)`：只处理 `status=error` 的条目，成功项原样保留。
    - `retry_item(batch_id, item_id, process)`：单条重试（页面上的“重试”按钮），显式动作，强制重新分析该条。
  - 失败不入缓存：异常条目标记 `error` 并继续下一条，重试时才真正重跑。
- `src/citeguard/pipeline.py`
  - `analysis_cache_versions()`：把报告结构版本、`support.PROMPT_VERSION`、审计开关/风格、判官 base_url/model、判官可用性、offline 开关纳入缓存键，避免换提示词/换模型/开关审计后串味。
  - `analyze_file_cached(file_path, options=...)`：解析 + 核验整份报告走结果缓存；返回的 `report["cache"]` 标明 `hit` / `miss` / `disabled`，并记录本次的 `key` 与 `versions`。

缓存键覆盖的“会改变结论”的版本：

| 维度 | 取值来源 | 变化后果 |
| --- | --- | --- |
| 报告结构 | `pipeline.ANALYSIS_CACHE_VERSION`、`RESULT_CACHE_SCHEMA` | 旧报告不复用 |
| 判官提示词 | `support.PROMPT_VERSION`（含自定义提示词哈希） | 旧判定不复用 |
| 审计 | `CITEGUARD_SUPPORT_AUDIT` + `CITEGUARD_SUPPORT_AUDIT_STYLE` | 审计开/关/风格不同即不同结果 |
| 判官模型 | `support.judge_endpoint()` 的 base_url + model | 本地模型与托管模型不串 |
| 判官可用性 | `support.judge_available()` | 未配置判官的结果不冒充已判定 |
| 离线/在线 | `config.OFFLINE` 与本次 options | 线上核验与离线核验分开 |

## 2. 口径

- **冷启动（cold）**：结果缓存和文本缓存都清空，3 个文件全部真实解析 + 离线核验。这是唯一可以报“冷启动耗时”的口径。
- **热缓存（hot）**：同样的文件字节、options、versions，结果缓存已热。条目全部 `source=cache`，不调用分析器；只能报“重复分析耗时”，**不得**当冷启动加速比。
- **命中率**：`hit_rate_this_run` 是本次批量中由缓存直接命中的条目占比；`cache.stats().hit_rate` 是进程内累计（冷批的 miss 也在内），两者不可混用。
- **只补失败**：`retry_failed` 只跑 `error` 条目；成功条目的报告文件与状态保持不变（`source` 也不改写）。
- 计时为单机 wall-clock，CPU 环境，未离线核验外网、未调用判官（离线核验是规则判定，不是语义判定）。

## 3. 真实验证

数据：`data/real_corpus` 中 3 篇公开论文 PDF（真实字节，SHA-256 见 JSON 的 `dataset.files`），options 为 `{"support_max": 0, "online": false, "figures": false, "max_refs": 40}`，判官关闭、无网络。

| 场景 | n | 总耗时 | 单条耗时（ms） | 命中/处理 | 报告摘要 |
| --- | --- | --- | --- | --- | --- |
| 冷启动 | 3 | 4,373.8 ms | 1859 / 1343 / 1141 | 0 命中 / 3 处理 | 引文 24 / 14 / 11；正文引用 27 / 14 / 12 |
| 热缓存 | 3 | 67.9 ms | 13 / 14 / 11（读报告） | 3 命中 / 0 处理 | 与冷启动摘要逐项一致 |
| 失败后 `retry_failed` | 3（1 条注入超时） | 首轮 43.9 ms；重试 29.0 ms | 只重跑失败条 | 成功 2 条未重跑 | 重试后 3/3 done |
| 单条 `retry_item` | 3（1 条注入失败） | 只重跑目标条 | `calls_after=["hanspub_152574.pdf"]` | 成功 2 条未重跑 | 重试后 3/3 done |

补充读数：热批 `speedup_vs_cold=64.44`（仅表示重复分析更快，不是冷启动优化）；`same_report_summaries=true`；冷批后缓存 `entries=3, hits=0, misses=3`；热批后累计 `hits=3, misses=3, hit_rate=0.5`，本次热批的 `hit_rate_this_run=1.0`。

失败注入说明：首轮对第 2 条（`retry_failed` 场景）/第 3 条（`retry_item` 场景）抛一次 `TimeoutError`/`ConnectionError`，模拟网络抖动；随后重试成功。失败条目未被写入缓存，因此重试是真实重跑。

## 4. 测试

新增 `tests/test_b2_cache.py`（9 个用例）：

- 缓存键覆盖文件内容、options、prompt/audit 版本与 schema；
- 缓存命中/损坏条目按 miss/失效/禁用；
- 热批不重复调用分析器，报告摘要与冷批一致；
- `retry_failed` 只重跑失败条，成功条报告不变；
- `retry_item` 单条重试（含未知条目报 `KeyError`）；
- 批量记录与报告落盘；
- `analysis_cache_versions()` 含 prompt/audit/model；
- `analyze_file_cached` 二次调用为 `cache.status=hit` 且引文一致。

全套：`python -m pytest tests -q` → **1092 passed, 10 skipped**（102.55 s；基线 1074，本文件新增 9 条；其余增量为同期其他任务的测试，未破坏既有测试）。

## 5. 边界

- 只做库层能力：`web/app.py`、模板与静态资源不在本任务写作用域，因此页面尚未接 `BatchRunner`；接口已可供批量页/CLI 直接调用。
- 缓存保存的是完整报告（含参考文献与引用句文本），落盘在本地 `data/cache/results`；`CITEGUARD_RESULT_CACHE=0` 可关闭，`CITEGUARD_RESULT_CACHE_DIR` 可改目录，`clear()` 可清空。
- 热缓存不等于冷启动：同一键的第二次分析一定更快，报告里必须标 `cache.status=hit`，不能拿 hot 数字做“冷启动加速”。
- 换提示词、换判官模型、开关审计、offline/online 切换都会换键，旧结果不会复用；这是“避免串味”，不是 bug。
- 失败不缓存，因此没有“负缓存”；同一失败会真实重跑，便于修好网络/判官后再试。
- 基准是单机 CPU、离线规则核验，不能外推到 GPU/判官在线场景。

## 6. 复现

```powershell
cd D:\ai+ky\citeguard
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='src'
python tests\b2_cache_bench.py --json data/experiments/opt_b2_cache_2026-11-26.json
python -m pytest tests/test_b2_cache.py -q
python -m pytest tests -q
```

`tests/b2_cache_bench.py` 默认工作目录 `D:\Temp\citeguard_e3\b2_bench`（可用 `B2_BENCH_WORK` 覆盖），会先清空结果缓存与文本缓存，再跑冷/热/重试三段。

## 7. 变更文件

- `src/citeguard/jobs.py`：`result_cache_key`、`ResultCache`、`BatchRunner`、`retry_failed`、`retry_item`。
- `src/citeguard/pipeline.py`：`ANALYSIS_CACHE_VERSION`、`analysis_cache_versions()`、`analyze_file_cached()`。
- `tests/test_b2_cache.py`：9 个用例（新增）。
- `tests/b2_cache_bench.py`：冷/热/重试基准脚本（新增，pytest 不收集）。
- `data/experiments/opt_b2_cache_2026-11-26.json`：本次真实读数（新增）。
- 本文件 `docs/optimization/b2_cache.md`（新增）。

未改：`web/app.py`、`web/templates`、静态资源、`support.py`、`metadata_verify.py`。

## 复审修正：库指纹（2026-11-27）

- 问题：原缓存键只包含文件、选项和 prompt/audit/judge/schema 版本，**不含本地题录库**；而分析会读取本地库，库变更后可能命中旧报告。
- 修正：`pipeline._library_cache_fingerprint()` 把库文件内容（或传入 Library 的完整 `to_dict()`）哈希后写入 `versions["library"]`；库变化即换键，旧缓存不会命中。
- 测试：`tests/test_b2_cache.py::test_library_fingerprint_changes_the_cache_key` 验证库从 missing 变为空库后第二次调用为 miss、键不同。
- 边界：未接 web；热缓存 98.1 ms 不是冷启动；失败不缓存。


## 8 Web 分析入口接入（1.7.50）

- `pipeline.run_job` 先按文件字节、options、prompt/audit/judge 版本与**本地题录库指纹**算键；命中时深拷贝缓存报告、把 `input` 改为当前上传文件名、进度置 60，跳过抽取与核验；未命中走原流程并回写缓存。
- 端到端实测（`scripts/measure_b2_web.py`，POST `/api/analyze`，support_max=0）：冷 **4.638 s / cache miss**，热 **2.063 s / cache hit**，同 key `6b03ab1dd6f582cbd207959a1809cec5`；数据 `data/experiments/opt_b2_web_2026-11-27.json`。
- 测试：`tests/test_b2_cache.py::test_run_job_reuses_the_result_cache_for_web_uploads`；全套 1131 passed。
- 边界：热缓存不是冷启动；库、提示词、判官模型任一变化即换键；失败不缓存。
