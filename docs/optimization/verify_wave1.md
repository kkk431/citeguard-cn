# Wave1 独立验收：B2 / E2 / G2 / G4

- 验收人：authority（独立验收，不改产品代码、不改测试）
- 验收时间：2026-11-26 23:53 – 2026-11-27 00:10（Asia/Shanghai）
- 仓库：`D:\ai+ky\citeguard`，HEAD `69f312e`（G2 提交）；Wave1 提交 `de6d351`（B2）、`5dfe3c2`（E2）、`69f312e`（G2）、`068cff7`（G4）
- 运行环境：Windows，应用 `http://127.0.0.1:8013`（现成服务），Edge `158.0.4370.33`（Playwright `channel="msedge"`）
- 证据索引：`data/experiments/opt_verify_wave1_2026-11-26.json`

## 1. 结论

| 项 | 结论 | 依据 |
|---|---|---|
| B2 结果缓存 + 只重跑失败 | **pass** | 9 项单测通过；独立重跑基准 cold 6614.1 ms → hot 98.1 ms（3 条），retry_failed 只重跑失败项（1 次调用，49.2→34.6 ms）；缓存键含 analysis/prompt/audit/judge 版本；失败不落缓存 |
| E2 CiteMap 使用引导 | **pass** | 4 项单测通过；1440/1280 实页探针 7/7：3 步引导、5 项图例、15 篇论文、4 个引注按钮、焦点 EDU-C1（人工 4/机器 4/无 2）、仅全文筛选后 6 篇且人工 0/机器 4；无横向溢出、无 console 错误 |
| G2 报告阅读器 | **pass** | 91 项 web 测试通过（含 2 项 G2 契约）；实页 16/16：minimap 15 格、严重度筛选（medium 3 行）、页码跳转「第 2 / 4 页」、页内证据查看器、缩放 150%、条目跳转抽屉 + 高亮、键盘 j；无溢出、无 console 错误 |
| G4 微交互 | **pass** | 91 项 web 测试通过（含 5 项 G4 契约）；实页 9/9：Ctrl+K 面板 16 入口/分组/筛选/焦点回原位、toast、骨架屏 4 行清除、reduced-motion 关动画；无溢出、无 console 错误 |

**总判定：4/4 通过。** 遗留 2 条 finding（1 medium、1 low），均不阻塞 Wave1，但需在对应能力进产品前处理（见 §6）。

## 2. 通用门禁（全部实跑）

| 命令 | 结果 |
|---|---|
| `python -m pytest tests -q` | **1094 passed, 10 skipped in 102.72s**（exit 0） |
| `python scripts/verify_artifacts.py` | **[OK] all 137 checks passed**（exit 0） |
| `python scripts/audit_evidence.py` | 265 paths checked，missing **0**，shots registered 136，unregistered **16**（exit 0；16 张恰为 Wave1 截图，见 §6 F1） |
| `python scripts/audit_frontend.py http://127.0.0.1:8013` | **58/58 checks passed**（含报告页键盘 `report_j_enter_esc`、`report_slash`、`palette_opens_ctrl_k`，无 console 错误、1280 无溢出） |
| `python scripts/e2e_smoke.py --base http://127.0.0.1:8013 --pdf data/real_corpus/hanspub_152575.pdf --out $TEMP/t36_e2e.json` | 全 PASS：references 15、citations 18、captions 10、cited_in 15、annotated_pdf 1,667,177 B、RIS/ENW/BibTeX/CSL/refs 导出、evidence bundle 10 文件、diff_self 200；job `4c2e857565fa` |
| `python $TEMP/t36_pages.py`（独立 Playwright 实页探针） | **82/82 checks passed**（1440x900、1280x800、reduced-motion 三次运行；console_errors 0，failed_requests 0） |

单文件测试：`tests/test_b2_cache.py` 9 passed；`tests/test_citemap_e2.py` 4 passed；`tests/test_web.py` 91 passed。

## 3. B2：结果缓存 + 只重跑失败

**交付物**：`src/citeguard/jobs.py`、`src/citeguard/pipeline.py`、`tests/test_b2_cache.py`、`tests/b2_cache_bench.py`、`docs/optimization/b2_cache.md`、`data/experiments/opt_b2_cache_2026-11-26.json`。

**写作用域**：`git show --stat de6d351` 仅上述 6 个文件；未触碰前端、`web/app.py` 或产品展示路径。

**代码核对**（`git show de6d351`）：
- `result_cache_key(file_sha256, options, versions)` = sha256(`schema` + 文件 sha + 规范化 options + 规范化 versions)；`versions` 含 `analysis=analyze_text-v1`、`prompt=support.PROMPT_VERSION`、`audit=on:<style>|off`、`judge_base`、`judge_model`、`judge_available`、`offline`。
- 写入原子（`tempfile.mkstemp` + `os.replace`），读时校验 schema 与 key；命中/未命中/写入计数可查。
- 失败不缓存：`_process_one` 异常路径直接返回，不调用 `cache.store`。
- `BatchRunner.retry_failed() = run(only_failed=True)`：只重跑 `status=error` 的项；`retry_item()` 强制单条重算；`done` 且已有报告时复用（`source="reused"`）。

**独立复现**（我自己起的环境变量，未用仓库里的缓存目录）：
```
B2_BENCH_WORK=$TEMP\t36_b2bench python tests/b2_cache_bench.py --json $TEMP\t36_b2bench.json
```
- cold：3 条全部 miss，wall **6614.1 ms**（2690 / 2255 / 1609 ms），写 3 条缓存；
- hot：3 条全部命中，wall **98.1 ms**（19 / 20 / 20 ms）；
- 加速比约 **67.4×**（t32 报告写 64.44×，差异来自不同基准文件）；
- retry：注入 1 次瞬时失败后 `retry_failed()` 只调用失败文件成功（calls `["hanspub_152573.pdf"]`，attempts 1/2/1），wall 49.2 → 34.6 ms；单条重试同样只调用目标文件。

**边界（文档已写）**：hot 数字不是冷启动性能；缓存存完整报告全文；prompt/模型/审计变更会换键；失败不做负缓存；仅本机离线基准；未接 web 模板（`docs/optimization/b2_cache.md` §边界）。

**结论：pass**（finding F2 见 §6）。

## 4. E2：CiteMap 使用引导

**交付物**：`web/static/js/citemap.js`、`web/templates/citemap.html`、`web/static/css/citemap.css`、`tests/test_citemap_e2.py`、`docs/optimization/e2_citemap_usage.md`、`data/experiments/opt_e2_citemap_usage.json`、4 张截图。

**写作用域**：`git show --stat 5dfe3c2` 仅 CiteMap 前端三件、测试、文档、JSON、4 张截图；未触碰 `web/app.py`、`src/citeguard/*`。

**测试**：`tests/test_citemap_e2.py` 4 passed（并入全量 1094 passed）。

**独立实页探针**（`/citemap?topic=ai_education`，1440x900 与 1280x800）：
- 3 步引导（`.ctm-step` = 3）、图例 5 项、论文 15 篇、引注按钮 4 个；
- 点击焦点按钮：状态「焦点：EDU-C1」，人工证据 4 / 机器候选 4 / 无证据 2；
- 仅全文筛选：`aria-pressed=true`，论文列表 6 条（`#ctm-paper-list .ctm-paper-item`），提示语「当前 6/15 篇论文有全文证据；其余论文已隐藏」，人工 0 / 机器 4；
- 两个宽度 `scrollWidth == clientWidth`，console 错误 0、失败请求 0。

**截图**：4 张（1440x2171、1280x2199 全页 + 焦点态），PNG 头解析尺寸与声明一致。

**边界（文档已写）**：机器候选 ≠ 人工证据；「未发现」≠「不存在」；无移动端截图；主题切换改变的是队列不是结论。

**结论：pass**（截图未登记入证据索引，见 F1）。

## 5. G2 / G4：报告阅读器与微交互

### G2
**交付物**：`web/static/js/report.js`、`web/templates/report.html`、新增 `web/static/css/report_reader.css`、`data/experiments/opt_g2_reader.json`、`docs/optimization/g2_reader.md`、6 张截图。

**写作用域**：仅报告页前端三件 + 证据/文档；未触碰 `web/app.py`、`src/citeguard/*`。

**独立实页探针**（`/report/4c2e857565fa`，1440/1280）：
- minimap 15 格（与 15 条参考文献一致）；
- 严重度筛选 medium：4 → 3 行，minimap 同步 3 格；
- 页码跳转「第 2 / 4 页 · 5–8 / 15 条」；
- 正文引注页按钮打开页内证据查看器（标题「第 2 页 · 页内证据」），缩放 +2 次到 150%（`#page-viewer-img` width 同步 150%）；
- 条目跳转打开 `#ref-drawer` 且目标卡片带 `kb-active`；
- 键盘 `j` 使 `#ref-list .ref.kb-active` 计数 1；
- 无横向溢出、console 错误 0。

**测试**：`tests/test_web.py` 91 passed，其中 G2 契约 `test_report_reader_ships_minimap_and_severity_filter`、`test_report_reader_zoom_and_existing_controls_are_preserved` 通过。

**边界（文档已写）**：minimap 只画当前筛选集；严重度是阅读优先级不是质量；页码跳转只分页参考文献列表，页内证据需点引注页按钮；缩放 50%–250%。

**结论：pass**。

### G4
**交付物**：`web/templates/base.html`、`web/static/js/app.js`、`web/static/css/refresh.css`、`tests/test_web.py`（+159 行）、`docs/optimization/g4_micro_interactions.md`、`data/experiments/opt_g4_micro_interactions_2026-11-26.json`、6 张截图。

**写作用域**：仅全局壳层（base/app/refresh）+ 测试/证据；未触碰 `web/app.py`、`src/citeguard/*`。

**独立实页探针**（`/workspace`，三组：1440、1280、1440+reduced-motion）：
- Ctrl+K：面板打开、16 个入口、分组「页面/动作/链接」、`body` 滚动锁定；筛选后入口数收敛；Escape 关闭且焦点回到 `#palette-open`；
- toast：`role=status`、文字渲染、可关闭（opacity → 0）；
- 骨架屏：`skeletonHTML(3)` 生成 4 行（1 标题 + 3 行）、`clearSkeleton` 后 `.cg-skel` 归 0；
- reduced-motion：`data-motion="reduced"`，`main` 动画为 none；
- 无横向溢出、console 错误 0、失败请求 0。

**测试**：`tests/test_web.py` 91 passed，含 5 项 G4 契约（motion/palette/toast hooks、token、remote dependency、command 保留等）。

**边界（文档已写）**：微交互只作用于壳层，不改变业务判定；动画可被 `prefers-reduced-motion` 关闭；未做移动端。

**结论：pass**。

## 6. Findings（不阻塞，但需在对应能力进产品前处理）

**F1（low，证据治理）**：16 张 Wave1 截图（E2 4 + G2 6 + G4 6）未登记进 `docs/evidence_index.md`，`audit_evidence.py` 报 `unregistered: 16`（文件都在，`missing: 0`）。建议负责人补齐索引（该文件不在本次验收写作用域）。

**F2（medium，B2 缓存正确性）**：结果缓存键排除了 `library` 选项（`src/citeguard/pipeline.py:214`：`key_options = {k: v for k, v in options.items() if k != "library"}`），但分析确实使用本地题录库（`pipeline.py:232,319,324,358-359` 的 `local_library_verdict`、`library_entries`、`library_hits`）。因此同一文件 + 同一 options/versions、但本地库变化时会命中旧报告，得到过期的本地核验结论/统计；`docs/optimization/b2_cache.md` 边界里未提这一点。建议：要么把库指纹（如 `LIBRARY_FILE` 的 size+mtime+sha）并入键，要么在文档与调用处明确「库变更需 `invalidate()`」。B2 尚未接入 web，故不影响本波验收。

**F3（info）**：B2 的 64.44× 是 hot-vs-cold 缓存加速比，文档已明确不是冷启动性能；我独立基准（不同 3 篇 PDF）复现 67.4×，冷启动仍约 2.2 s/篇（CPU、离线、无 support 判定），与文档口径一致。

## 7. 复现命令

```bash
# 通用门禁
python -m pytest tests -q
python scripts/verify_artifacts.py
python scripts/audit_evidence.py
python scripts/audit_frontend.py http://127.0.0.1:8013
python scripts/e2e_smoke.py --base http://127.0.0.1:8013 \
  --pdf data/real_corpus/hanspub_152575.pdf --out "$TEMP/t36_e2e.json"

# B2 独立基准（隔离目录，不污染仓库缓存）
B2_BENCH_WORK="$TEMP/t36_b2bench" python tests/b2_cache_bench.py --json "$TEMP/t36_b2bench.json"

# 实页探针（独立脚本，不在仓库内）
python "$TEMP/t36_pages.py"     # 82/82；JSON: $TEMP/t36_pages.json
```

## 8. 限制

- 独立实页探针不截图（截图由各任务提供，本次只解析尺寸并核对 JSON）；视觉细节未逐像素复核。
- `audit_frontend.py` / `e2e_smoke.py` 用本机现成服务 8013；未重启应用，未覆盖冷启动行为。
- 均为 proxy 口径：无 GPT-4o judge、无人工金标；E2 的机器候选不是证据。
- 未做移动端与 Safari/Firefox。

## 复核闭环（队长，2026-11-27）

- F1（16 张 Wave1 截图未登记）：已在 `docs/evidence_index.md` 补 E122–E124，`audit_evidence` 显示 0 unregistered。
- F2（B2 键缺库指纹，medium）：已在 `src/citeguard/pipeline.py` 加入 `_library_cache_fingerprint`，键包含 `versions["library"]`，并补 `test_library_fingerprint_changes_the_cache_key`；`tests/test_b2_cache.py` 10 passed。
- F3（64.44× 为热缓存）：保留原边界，不当作冷启动性能。
