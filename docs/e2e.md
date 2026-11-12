# 端到端冒烟（E2E smoke）

一条命令验证「上传 → 任务 → 报告 → 批注 PDF → 导出 → 证据包 → diff」整条链路，避免只测单元、没测接线。

```powershell
$env:PYTHONPATH='src'
python scripts/e2e_smoke.py --base http://127.0.0.1:8013 `
  --pdf data/real_corpus/hanspub_152575.pdf `
  --out data/experiments/e2e_smoke.json
```

当前结果（2026-11-11，v1.0.11，job `94c2214965b1`）：**14/14 通过**。

| 检查 | 结果 |
|---|---|
| health / job_done | 1.0.11 / done |
| report_references / citations / captions | 15 条 / 18 处 / 10 个图表标签 |
| report_cited_in | 15/15 条有正文引用 |
| annotated_pdf | 1,667,177 B；X-Annotated: 7；X-Citations-Annotated: 17 |
| export ris/enw/bibtex/csl/refs | 8,900 / 4,612 / 5,720 / 10,178 / 3,594 B |
| evidence_bundle | 10 个文件（含 report.ris/enw/manifest.json） |
| diff_self | 200，summary 存在 |

边界：只跑一篇真实论文；不覆盖 Word 客户端（需人工）；diff 用同一份报告自比，验证接口形状而非修改效果。

证据：`data/experiments/e2e_smoke.json`；报告页截图 `docs/evidence/shots/phase-36-e2e-report-1.0.11.png`（E46）。

## 离线 CI（纯文本，13 项，1.3.3）

真实语料 PDF 有版权、不入库，所以 CI 用一段自带引用的小文本，服务以 `CITEGUARD_OFFLINE=1` 启动：

```bash
python -m uvicorn web.app:app --port 8013 &
python scripts/e2e_smoke.py --base http://127.0.0.1:8013 \
  --text /tmp/smoke_paper.txt --out /tmp/e2e_smoke.json
```

- 文本模式跳过 `annotated_pdf`（没有 PDF 可批注），其余 13 项全查：参考文献 3 条、引注 2 处、图表标签 1 个、5 种导出、证据包 9 文件、diff 自比。
- `.github/workflows/ci.yml` 的 `smoke` job 就是这么跑的；2026-11-12 本地（v1.3.2）**13/13 通过**，产物 `data/experiments/e2e_offline_1.3.2.json`。
- 离线模式下核验状态是 `Unknown`（“没联网，未核验”），不是 `Exact`；冒烟只验证链路，不把 Unknown 当准确率。

## 一条命令的边界

- 需要服务已启动，脚本不负责起服务（CI 里由 workflow 起）。
- 不测 LLM 判定质量，只测“能跑通、有产物、字段在”。
- 任何一项失败会以非零退出码结束，并打印 `FAIL <check>`；CI 会贴服务日志。
