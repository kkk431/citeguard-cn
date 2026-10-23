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

输入解析（PDF/Word/扫描件 OCR）、GB/T 格式检查（E4 漂移 29/30）、引文真实性核验（在线 + 本地题录库 + 中国 DOI 平台）、支持度判定（两段式 macro-F1 0.9328）、报告与导出全部可用；247 项测试通过。已知边界写在 `docs/plan.md`。

## 4. 明天优先级

1. **真实用户测试**：脚本/指标/问卷/结果模板已写成 `docs/user_test_kit.md`，找 3–5 位研究生或青年教师跑一遍即可得到可引用的用户数据（E7 只是内部自测，不能当用户研究）。
2. **题录摘要引导**：把「导出题录时勾选摘要」写成图文步骤（知网/EndNote/Zotero 各一段），支持度判定才不至于大面积「未检测」；`scripts/enrich_library_abstracts.py` 可补已导入的库。
3. **性能**：大 PDF（100+ 条引文）的分页进度提示；同题材名检索的本地缓存命中率。
4. **OCR 后处理**：更多 `[J]`→`[]` 之外的扫描噪声（连字符、全角标点）回归。

## 5. 2026-10-23 上一批改动（已推送）

- 支持度 prompt v3：macro-F1 0.7951 → **0.9005**（v4 few-shot 试了更差，未采用）
- 本地题录库：多文件导入、文件夹导入、BibTeX/RIS 导出、摘要接入支持度判定
- 扫描件 OCR（可选依赖）+ OCR 噪声解析加固
- 格式引擎：作者数规则、DOI/年份/页码校验、文档级一致性检查；E4 漂移检出 10/30 → **15/30**
- 数据源限流/宕机时返回「无法核验」而不是「未找到匹配」
- 网页：批量上传、CSV 导出、格式错误筛选、手机宽度修正

## 6. 2026-10-23 白天续工（本次）

**核验正确性**
- 中国 DOI 平台（CNKI/万方签发、Crossref 查不到）落地页元数据接入为 `doi:landing`：解析题名/作者/来源，缓存候选，报告标注「卷期页可能未核对」。真实语料里 1 条由 Unverified → Exact。
- DOI 状态缓存升级到 v3（连候选一起缓存），修复「重启后 resolved_landing 丢候选变成 Unknown」的隐患。
- APA 裸题录作者列表合并修复：`Brehm, S. S., Miller, R. S., …` 不再被拆成 8 个「作者」（此前会误判作者不一致）。
- 作者比对改为**姓氏比对**（`Yu, H.` ↔ `Hui Yu`），并单独检查作者顺序；真实语料 Exact 76→74 / Minor 47→50 / Unverified 101→100 / Major 0，其中 1 条是新发现的真实作者顺序错误、1 条是书评记录（Minor 误报 +1，已加提示「可能是书评/同名不同作品」）。
- 新增 15 个单测覆盖上述行为（`tests/test_metadata_verify.py`、`tests/test_parser_styles.py`、`tests/test_local_library.py`）。

**题录库摘要补全**
- 新脚本 `scripts/enrich_library_abstracts.py`：从 OpenAlex/Crossref 给本地题录库补摘要（题名相似度 ≥0.92 且年份不冲突才采用）。
- 本机演示库 10 条里补上 8 条；补完后 `support_max=5` 的分析能正常判支持度（实测 5 支持 / 7 未检测，其中 2 条无摘要）。
- 题录库页面新增「带摘要」统计、缺摘要提示与摘要列。

**网页**
- 批量上传：逐篇提交 + 实时阶段/百分比 + 全部完成后**汇总面板**（篇数/条数/各状态/格式均分/一句结论）+「导出汇总 CSV」。
- 报告卡片：中国 DOI 平台/DataCite 来源用 warn 标签标出「卷期页未核对」；`exists_elsewhere` 的 DOI 直接给「DOI 原文页」链接；支持度面板解释「命中记录缺摘要」。
- 支持度进入「需处理」逻辑：与原文**矛盾 / 部分支持**的条目即使元数据一致也会进体检结论、按风险排序，并新增「支持度矛盾」「部分支持」筛选 chip；「复制修改建议」与 Markdown/HTML 导出都会写出矛盾理由与证据。
- 题录库：新增「带摘要」统计与缺摘要提示、导入后 toast 提示缺摘要条数、表格增加摘要列。
- 移动端：真实 390px 视口下 5 个页面无横向溢出（CDP 实测 `scrollWidth == 390`）；窄屏下拉宽表格改为面板内横滚、进度列隐藏、「怎么工作」单列、题录统计 2×2。
- 关于页补 DataCite / 中国 DOI 平台 / OCR 依赖的许可证说明；首页与关于页的多源说明同步更新。
- 真实浏览器验证：用 CDP 直接驱动批量上传（2 个文件）→ 汇总面板数值正确（21 条 / 13 真实 / 8 偏差 / 均分 92.9）、CSV 按钮存在；用构造报告验证支持度筛选点击后从 12 条过滤到 1 条。

**测试/文档**
- `pytest` 229 → **239 通过**（2 个 OCR 用例 skip 因未装可选依赖）。
- `docs/real_data_eval.md` 第 3 节换成本次实测与逐条 diff；新增第 5 节「中文覆盖率还能不能再挖」（检索召回 0.92、DOI 落地页覆盖面）。
- 新增 `docs/user_test_kit.md`（任务脚本 + 指标 + SUS 问卷 + 结果模板）；README 补引用支持度读法表与「真实用户研究还没做」的说明。
- 远程演示实例已更新并验证：`/api/health` 200、中国 DOI 落地页解析生效（CNKI DOI → Exact）、支持度 judge 可用、题录库补了 8 条摘要。

## 7. 2026-10-23 晚间：指标冲榜（PPT 用）

**支持度两段式判定（0.9005 → 0.9328）**
- 第一段 v3 prompt 给四分类 + 证据句；第二段只对 `support` 做「覆盖审计」：拆引用句要素，证据缺任一要素 → 降级 `partial`。
- 产品路径正式评测：macro-F1 **0.9328 / acc 0.9300**（`data/claimsupport_cn/results.json`）；独立实验脚本 0.9439（`data/experiments/support_two_stage_results.json`）。
- 失败实验已存档：结构化 checklist prompt（v5）0.8196（`support_v5_results.json`）；三票自一致性 0.9005（`support_v3_vote3_results.json`）；单段复测 0.8929（`support_v3_rerun_results.json`）。
- 开关：`CITEGUARD_SUPPORT_AUDIT=0` 可关闭第二段；默认开启，约 40% 条目多一次 judge 调用。

**GB/T 格式规则扩展（E4 15/30 → 29/30）**
- 新增 3 条规则：页码 ASCII 连字符 → info 提示一字线；期号显著大于卷号 → warning「卷/期可能颠倒」；`[D]` 出现卷/期 → error「类型码可能误标」。
- 修正 4 条漂移构造：单页/文章号基底无法通过替换连接号制造漂移，改为构造同宽度两页区间再替换。
- E4 复跑：漂移严格检出 **29/30（96.7%）**，类型码识别 100%、必填字段 98.4%；剩余 1 条卷/期互换因数字都小而无法判断，已在结果里保留 miss。

**评测页升级为「答辩数据面板」**
- `/benchmark` 新增两块：ClaimSupport-CN 支持度结果（0.9328/0.930 + per-class + 混淆）与「真实已发表论文上的表现」（解析 99.6%/99.2%、真实性 74/50/100/**Major 0**、本地库 224/224、检索召回 92%、E4 29/30）。
- `/api/benchmark` 同步返回 `support_benchmark` 与 `real_data`。
- 答辩用数字一页纸：`docs/ppt_numbers.md`（每条数字的口径、复现命令、以及「不能这么说」的红线）。

**测试**
- `pytest` 239 → **247 通过**（新增 E4 规则 5 项、两段式 judge 3 项）。
- 文档同步：README 支持度表与混淆矩阵、`docs/support_summary.md`、`data/claimsupport_cn/README.md`、`docs/experiments.md` E4 章节、`docs/plan.md`。
