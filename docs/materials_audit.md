# 材料同步审计（优化期）

更新时间：2026-11-27。

| 材料 | 当前 | 需要同步的内容 | 状态 |
| --- | --- | --- | --- |
| 技术报告 | v1.7.50 / 15 页 / 1,702,624 B | A1/A2/B1/B3/C1/D1/E1/F1/H1 + Wave1 + Wave2 A3/G3/E3/D3D4 已写入；1130 tests；304 路径/163 截图 | 已更新 |
| 资源清单 | v1.7.50 / 2 页 / 144,778 B | 无新增第三方依赖；readability/Europe PMC/Qwen3-VL/4B 已在册 | 可保持 |
| 佐证材料 | v1.7.50 / 20 页 / 2,503,125 B | 已追加 A1–H1 优化增量（验收表+4 张真实截图） | 已更新 |
| 提交目录 | 8 文件 | 报告/资源清单/佐证均 v1.7.50；zip 27,610,841 B / sha `4e9417514ffe0e0653a34578aafe5b46738d5e019f5c64af36baefdfbec02f52` | 已更新 |
| GitHub | main `9318c6f` / tag v1.7.50 | release latest v1.7.50（https://github.com/kkk431/citeguard-cn/releases/tag/v1.7.50，页面指向 `9318c6f`）；CI `9318c6f` success（GitHub Actions 9318c6f） | 已更新 |
| 平台字段 | 名称/简介已定 | 报告/佐证更新后字段不变 | 待确认 |
| PPT/视频 | v1.7.35 / v1.7.36 | 用户明确不改内容 | 保持 |

## 已知风险

- 报告/PPT 版本不一致（PPT 停在 v1.7.35）是用户指定例外。
- 视频未补开放成果镜头是用户指定例外。
- 无公网在线演示，报告/提交说明已如实写本地/Docker。
- 佐证 PDF 仍是 v1.7.36/18 页，尚未追加 A1/F1 等优化证据。
- `THIRD_PARTY_NOTICES.md` 已含 readability/Europe PMC/Qwen3-VL/Qwen3-4B；F1 无新依赖。
- F1 只给修复动作，不补造缺失 DOI/作者；已修不等于正确。

- 2026-11-27：Wave1（B2/E2/G2/G4）验收与复审修正；B2 缓存键补本地库指纹；证据索引 0 unregistered。

- 2026-11-27：提交 zip 重打为 v1.7.48（27,352,706 B，sha ab9e700c…）；报告 15 页/1,701,614 B。

- 2026-11-27：v1.7.48 release 已创建并设为 Latest；tag 指向 e63dfd8。

- 2026-11-27：Wave2（A3/G3/E3/D3D4）验收通过（t41），3 条 low finding 已复审：F3 下拉加载禁用、F2 rows 口径、F1 自报口径；1130 tests。

- 2026-11-27：v1.7.49 tag 强移到 `396c8af`（SBOM 修复）；release 页面指向 `396c8af`；CI #415 正在跑。
- 2026-11-27：G6/H3/H4 收尾检查通过（1280/1440/1920 18/18、键盘 58/58、对比度 20/20、H3 3/3、H4 4/4）；无产品功能/版本变化，报告/提交包不需要因本轮重建；证据 E130。


- 2026-11-27：B2 缓存接入 Web 分析入口（冷 4.638 s / 热 2.063 s）；Docker `citeguard-cn:1.7.50` 构建并通过 health；镜像 943,589,044 B。
- 2026-11-27：技术报告重建 v1.7.50/15 页/1,702,624 B；资源清单 v1.7.50/2 页/144,778 B；佐证 v1.7.50/20 页/2,503,525 B；提交 zip 27,611,303 B / sha `31f25160…`。
- 已知不变：PPT v1.7.35、视频 v1.7.36（用户指定不改）；无公网演示。

- 2026-11-27：B2 Web 缓存提交 `9318c6f`；tag/release `v1.7.50` 已指向 `9318c6f` 并设为 Latest；CI success。
- 2026-11-27：技术报告 15 页/1,702,624 B；资源清单 2 页/144,778 B；佐证 20 页/2,503,125 B；提交 zip 27,610,841 B / sha `4e941751…`。

## 2026-11-27 · Batch 0 技术基线（v1.7.51）

- 报告：`dist/CiteGuard-CN_技术报告_v1.7.51_2026-11-27.pdf` 15 页 / 1,703,665 B；正文 1.7.51 / 1148 tests / Batch 0 段；Docker 仍写最近验证 1.7.50（未重建 1.7.51）。
- 提交目录：报告换 1.7.51；资源清单 1.7.50、佐证 1.7.50 为已知例外（Batch 0 无新依赖/未追加佐证）。
- 提交 zip：`dist/CiteGuard-CN_AIC-2026-67377639_v1.7.51.zip` 27,623,020 B / sha `2fa6816900915e4c93234dd52dd5eed51bbf3742b187c5353097e33f829ca76b`。
- 证据：E131；`evidence_audit` 314 路径 / 168 截图 / 0 missing / 0 unregistered；verify 137/137；licenses 4/4。
- Git：待提交/推送/tag v1.7.51/release latest。
- 已知例外：PPT v1.7.35、视频 v1.7.36、佐证 PDF v1.7.50、资源清单 v1.7.50、Docker 1.7.50；无公网演示。

### 2026-11-27 · v1.7.51 发布

- Git：commit `56db7ee`，tag `v1.7.51` 指向 `56db7ee`；CI #422 success（1m15s）。
- GitHub Release：`v1.7.51 — Batch 0 technical baseline` 已创建并设为 Latest。
- 报告：`CiteGuard-CN_技术报告_v1.7.51_2026-11-27.pdf` 15 页 / 1,703,665 B；提交目录 01 已替换。
- 提交 zip：`CiteGuard-CN_AIC-2026-67377639_v1.7.51.zip` 27,623,020 B / sha `2fa6816900915e4c93234dd52dd5eed51bbf3742b187c5353097e33f829ca76b`。
- 资源清单仍 v1.7.50（Batch 0 无新增依赖）；佐证 PDF 已重建 v1.7.51 / 21 页 / 2,514,087 B，已追加 Batch 0。
- 证据：E131；314 路径 / 168 截图 / 0 missing / 0 unregistered；tests 1148。
- 已知例外：Docker 最近验证 1.7.50；PPT v1.7.35、视频 v1.7.36；无公网演示。


### 2026-11-27 · Batch 1（v1.7.52）

- 报告：`dist/CiteGuard-CN_技术报告_v1.7.52_2026-11-27.pdf` 15 页 / 1,704,398 B；正文 1.7.52 / 1161 tests / Batch 1 段；Docker 仍写最近验证 1.7.50（属实）。
- 提交目录：01 换 v1.7.52；提交说明 v1.7.52；资源清单 v1.7.50、佐证 v1.7.51、PPT v1.7.35、视频 v1.7.36 为已知例外。
- 提交 zip：`dist/CiteGuard-CN_AIC-2026-67377639_v1.7.52.zip` 27,623,831 B / sha `5a559d9b05bc2e57697aa3a71c116fcea7e760a1763f9f85d01c01827053c9dd`。
- 证据：tests 1161；verify 137/137；evidence_audit 324 路径 / 170 截图 / 0 missing / 0 unregistered；E133/E134。
- Git：commit `5e5ee46`；tag v1.7.52 指向 `5e5ee46`；GitHub release latest `v1.7.52 — Batch 1 technical baseline` 已创建；CI #429 success（1m13s）。
- 已知例外：PPT v1.7.35、视频 v1.7.36、佐证 PDF v1.7.51/21 页（Batch 1 未追加）、资源清单 v1.7.50、Docker 1.7.50；无公网演示。

### 2026-11-27 · Batch 2（v1.7.53）
- 报告：`dist/CiteGuard-CN_技术报告_v1.7.53_2026-11-27.pdf` 15 页 / 1,705,476 B；正文 1.7.53 / 1162 tests / 328 路径 / Batch 2 段。
- 提交目录：01 换 v1.7.53；提交说明 v1.7.53；资源清单 v1.7.50、佐证 v1.7.51、PPT v1.7.35、视频 v1.7.36 为已知例外。
- 提交 zip：`dist/CiteGuard-CN_AIC-2026-67377639_v1.7.53.zip` 27,624,935 B / sha `58ae986ceb405d29acabe02c0c6897328a22d8f2a9522ac315fb2d58b7b33f41`。
- 技术基线：2.1 两跳实现但真实样例无新增正例；2.2/2.3/2.4 为既有能力证据化，不包装成新方法。
- Git：commit `9991c83`；tag v1.7.53 指向 `9991c83`；GitHub release `v1.7.53 — Batch 2 technical baseline` 已设为 Latest；CI 待确认。
- Docker：`citeguard-cn:1.7.53` 构建成功（949 MB），容器 `/api/health` 返回 `{"ok":true,"version":"1.7.53"}`；报告正文仍写“最近验证 1.7.50”（不虚报）。
- 已知例外：佐证 PDF 仍 v1.7.51/21 页（未追加 Batch 2）、资源清单 v1.7.50、PPT/v1.7.35、视频/v1.7.36。
