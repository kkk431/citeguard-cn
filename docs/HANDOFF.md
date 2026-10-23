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

输入解析（PDF/Word/扫描件 OCR）、GB/T 格式检查（E4 漂移 29/30）、引文真实性核验（在线 + 本地题录库 + 中国 DOI 平台）、支持度判定（两段式 macro-F1 0.9328）、报告与导出全部可用；253 项测试通过。已知边界写在 `docs/plan.md`。

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
- `/benchmark` 新增两块：ClaimSupport-CN 支持度结果（0.9328/0.930 + per-class + 混淆）与「真实已发表论文上的表现」（解析 100%/99.6%、真实性 112/89/208/**Major 0**、本地库 409/409、检索召回 92%、E4 29/30）。
- `/api/benchmark` 同步返回 `support_benchmark` 与 `real_data`。
- 答辩用数字一页纸：`docs/ppt_numbers.md`（每条数字的口径、复现命令、以及「不能这么说」的红线）。

**测试**
- `pytest` 239 → **247 通过**（新增 E4 规则 5 项、两段式 judge 3 项）。
- 文档同步：README 支持度表与混淆矩阵、`docs/support_summary.md`、`data/claimsupport_cn/README.md`、`docs/experiments.md` E4 章节、`docs/plan.md`。

## 8. 2026-10-23 深夜：功能拓宽 + 外部数据集 + 扫描件

**GB/T 参考文献表重排导出**
- 报告页新增「复制参考文献表 / 导出参考文献表」：把解析出的每条按 GB/T 7714-2025 重排（作者>3 补等、类型码、卷(期)、页码、DOI），输出 .refs.txt；Markdown/HTML 报告末尾附表，CSV 加「规范条目」列；/api/report/<id>/export?format=refs。
- 只做格式重排、不补缺失字段；测试 251→253。

**外部公开数据集（SciFact）**
- 同一 judge 零样本跑英文 SciFact dev 300 条（未训练/微调）：oracle 证据句 macro-F1 **0.8224** / acc 0.8267；整段摘要 **0.7939** / 0.8000。
- 许可证：claims CC BY 4.0、摘要 ODC-By 1.0、代码 Apache-2.0；原始数据不随仓库分发，只提交脚本与结果 JSON（scripts/eval_support_scifact.py、data/experiments/scifact_support_results.json）。
- 评测页新增加「外部公开基准 · SciFact 零样本」行。

**扫描件 OCR（真实 bug + 实测）**
- 用真实论文 PDF 渲染成 7 页纯图片 PDF（scripts/make_scanned_pdf.py），跑通 OCR 兜底：解析出 **23/24 条**参考文献，题名/年 23/23、作者 21/23（DOI 在 150 dpi 下基本丢失，属已知边界）。
- 修 2 个真实 bug：①strip_repeated_lines 把单独成行的 [n] 当页码模板删除（[#] 重复）→ 编号全丢、只解析 2 条；②新增 _merge_reference_numbers() 把 OCR 独立成行的编号并回条目。
- 新增 scripts/eval_ocr_scanned.py 与 data/experiments/ocr_scan_real.json；本地 OCR 依赖装在 out/ocrlibs（不入库）。

**本地开源模型（Qwen3-1.7B，CPU）**
- scripts/eval_support_local.py：transformers CPU 加载 Qwen3-1.7B（Apache-2.0），完全离线跑支持度任务；20 条试点：产品长 prompt 0.5060（93 s/条），精简 prompt **0.7059**（46 s/条）。
- 结论写进 THIRD_PARTY_NOTICES.md §4.2：接口可切开源模型、已验证可离线跑通；小模型质量/速度有限，生产离线建议 Qwen3-8B+GPU。

## 9. 2026-10-23 夜：真实语料扩到 22 篇 + 解析/格式再打磨（v0.3.1）

- 语料 10 → **22 篇**（20 篇汉斯 OA 中文论文 + 2 篇 OpenAlex 英文两栏论文，409 条发布版 / 529 条 PDF 参考文献）。
- 解析干净率（按类型应有字段判断）：发布版 **100%**（409/409）、PDF **99.8%**（逐条 527/529 = 99.6%）；参考文献标题定位 22/22。
- 真实语料暴露并修掉的问题：英文网页型引文被拆散（判 `EB`、机构作者整体保留、链接/DOI 从题名剥离）、裸链接行/页码粘连行过滤、DOI 里的数字被误当年份/页码、`Surname, I.N.` 并列表被拆开、`拉尔夫·泰勒` 间隔号译名、APA 尾部 URL 被当出版者。
- 核验（无本地库，409 条真实参考文献）：Exact 125 / Minor 87 / Unverified 197 / **Major 0**（30.6% / 21.3% / 48.2%）。
- 新增**网页型引文链接核验**（`[EB/OL]`）：23 条真实网页引文中 13 条「链接可达且页面标题一致」判 Exact（+13 Exact），3 条页面标题不一致、7 条访问受限/内网被跳过；链接失效只提示不判「疑似虚构」。带 SSRF 防护（拒绝非 http(s)、内网/回环地址、非标准端口）、8s 超时、结果按 URL 缓存，`CITEGUARD_URL_CHECK=0` 可完全离线关闭。
- 本地题录库（408 条库 / 409 条 PDF 输入）：可判定 **409/409（100%）**，字段偏差 4 条（逐条核对均为 PDF 排版差异）。
- GB/T 重排导出修正：图书 `出版地: 出版者`、`EB` 不输出卷期页、作者缩写不出现双句点、出版者字段不再被 URL 污染。
- 版本 **0.3.1**；测试 253 → **270 通过**（2 skipped 为未装 OCR 依赖的用例）；E4 复跑仍 29/30、类型码 100%、必填 98.4%。
- 文档同步：README 数字表、「真实论文实测」、`docs/real_data_eval.md` §1–§4、`docs/ppt_numbers.md`、`docs/plan.md`、`docs/deployment.md`（v0.3.1）。

## 10. 2026-10-24 凌晨：网页型引文链接核验（v0.3.2）

- 新增 `[EB/OL]` 引文的**链接可达性核验**：抓取页面并读取 `<title>`，可达且与引文题名一致 → 判「真实一致」；标题不一致 → 提示人工核对；链接失效/需要登录 → 只提示「可能链接腐化」，**绝不判疑似虚构**。
- 真实语料（20 篇 409 条引文中的 23 条网页引文）：**13 条链接可达且标题一致（+13 Exact）**，3 条标题不一致，7 条 403/访问受限。真实引文确定结论 201 → **212 条（51.8%）**，Major 仍为 0。
- 安全：只允许 http/https、80/443 端口，目标 IP 必须是公网地址（拒绝 localhost/内网/回环/保留地址），响应体 300 KB 截断、8 s 超时、按 URL 缓存；`CITEGUARD_URL_CHECK=0` 可完全离线关闭（`docs/deployment.md` §1.5、`.env.example`）。
- 报告页新增「网页链接已核 / 链接失效·受限 / 页面标题不一致」标记与对应的提示文案；评测页 `/benchmark` 新增「网页型引文链接核验」行。
- 测试 270 → **275 通过**（新增 SSRF 拦截、可达+标题一致判 Exact、死链只判未核实、标题不一致、blocked 回退 5 项）；README/`docs/real_data_eval.md` §3.1/`docs/ppt_numbers.md` 同步。

## 11. 2026-10-24 凌晨：判定后端可插拔（v0.3.3）

- 支持度 judge 从「只能 DeepSeek」改成**任意 OpenAI 兼容 `/chat/completions`**：`CITEGUARD_JUDGE_BASE_URL` / `CITEGUARD_JUDGE_MODEL` / `CITEGUARD_JUDGE_API_KEY`（未设置时回退 `DEEPSEEK_*`），可指向 Ollama / vLLM / llama.cpp-server / LM Studio 的本地开源模型，完全离线、无需商业 API。
- 缓存按「模型 + prompt 版本」分键：换模型自动重判，不会复用别的模型的判定。
- 可用性判定改为「有 key 或显式配置了本地 endpoint」；报告里未判定的原因文案同步更新。
- 文档：README「引用支持度」给 Ollama 示例并诚实标注小模型质量差异；`docs/deployment.md` §1.4、`.env.example`、`THIRD_PARTY_NOTICES.md` §1 同步。
- 测试 275 → **278 通过**（本地 endpoint 无 key 可判、模型切换不复用缓存、无 endpoint 降级「未检测」）。
- 新增 `data/experiments/README.md`：每个对外数字对应的结果 JSON、生成脚本、代码快照与口径一页索引；`reproduce.sh` 增加离线测试步骤并指向该索引。

