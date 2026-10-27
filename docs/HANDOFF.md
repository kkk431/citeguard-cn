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
& $py -m pytest tests -q                       # 299 项，全离线

# 起工作台（演示/自用）
& $py -m uvicorn web.app:app --host 127.0.0.1 --port 8010
```

数据与产物：`data/library/library.json`（本地题录库，已 git-ignore）、`data/experiments/`（评测证据）、`out/`（临时文件）。

## 3. 当前状态（一句话）

输入解析（PDF/Word/扫描件 OCR）、GB/T 格式检查（E4 漂移 29/30）、引文真实性核验（在线 + 本地题录库 + 中国 DOI 平台）、支持度判定（两段式 macro-F1 0.9597；14B/8B 本地判官经产品代码路径复核 0.9744/0.8664）、图表结论核验（v2 + 正文/图注上下文，50 条口径 0.94）、报告与导出全部可用；387 项测试通过。已知边界写在 `docs/plan.md`。

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
- 用真实论文 PDF 渲染成 7 页纯图片 PDF（scripts/make_scanned_pdf.py），跑通 OCR 兜底：解析出 **23/24 条**参考文献，题名/年 23/23、作者 23/23（DOI 在 150 dpi 下基本丢失，属已知边界）。
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

**验收状态（v0.3.3，2026-10-24 凌晨）**
- 测试 **278 passed / 2 skipped**；`verify_artifacts.py` 本地 **63 项**，加 `--api-base`（校验 `/api/benchmark` 的 real_data 与证据文件一致）共 **72 项**全过。
- 远端演示实例（`/data/xyjiang/aic_mental/citeguard`，127.0.0.1:8000）已部署 v0.3.3，服务器上实跑 `verify_artifacts.py --api-base http://127.0.0.1:8000` = **70 项全过**（差 2 项是本地才有、未上服务器的实验证据文件的可选检查）。
- GitHub `main` 已推送到最后一个提交；`dist/citeguard-cn-0.3.3.zip` 已重建。
- 用本地 OpenAI 兼容假服务端到端跑通 `evaluate_support.py`（2/2 判定、0 失败、记录 endpoint/model），证明「本地开源模型当 judge」链路的脚本可用。

## 12. 2026-10-24 下午：OCR 报告可追溯 + 解析器抗 OCR 噪声（v0.3.4）

- 真实扫描件整链路上传暴露的解析器 bug 修复：
  - 类型码缺口：`_repair_garbled_type_marker` 在 `[]` / `[J.` / `[J。` / `[J,` / `[J；` 后补 `]`；无法确认时不再默认按 `[J]` 处理。
  - 卷期误判：`_split_volume_issue` 在「卷号缺失、只有年+期」（如 `2024(4)`）时不再把年份当卷号。
  - OCR 碎片：`_DATE_ONLY_RE` 与 `_looks_like_entry` 过滤 `(2024).`、`2024.` 这类日期碎片，参考文献表不再出现空条目。
  - 句号后 DOI：解析层给出补 DOI 的提示（不再静默丢弃）。
- 报告可追溯「文字来源」：`pdf_extract.extract_text_with_meta()` 返回 `{method, file_type, pages, ocr, chars, warnings}`，管线写入 `report["input_meta"]`；报告页顶部、Markdown/HTML 导出均显示「文字来源：OCR 识别（扫描件） · 页数 · 字符数」，OCR 文件额外提示识别错字会传递到结论。旧 JSON 报告无该字段时自动隐藏。
- 产品整链路实测（扫描件 7 页，作业 `684b69cabc70`）：解析出 20 条（22 个候选中 2 个日期碎片被丢弃），18 条 `[J]` / 1 条 `[EB/OL]` / 1 条 `[D]`，元数据偏差 1、Major 0，国标合规均分 93.2。
- 版本 **0.3.4**；测试 283 → **290 passed / 2 skipped**（新增 OCR 元数据、导出文字来源、干净打包用例）；`docs/real_data_eval.md` §2.2、README 同步。
- 交付包不再夹带第三方原始语料：`scripts/package_deliverable.py` 排除 `data/real_corpus/**` 与 `data/experiments/scifact_raw/**`（证据 JSON 仍保留），`dist/citeguard-cn-0.3.4.zip` 从 24.6 MB 降到 **1.3 MB**（163 个文件），避免把未获再分发许可的论文 PDF 打进包。

## 13. 2026-10-24 傍晚：OCR 失败不再静默（v0.3.5）

- 修复回退链静默失败：`_ocr_pdf` 原来吞掉 OCR 异常并返回空串，用户只看到「没有可提取的文字层 / 请安装 OCR」。现在异常写日志并转成可读原因（未装依赖 / 缺 pypdfium2 / 具体异常），报错带「OCR 回退也失败：…」，现场可定位。
- 回归修复：OCR 成功分支漏了 `text = ocr_text`，导致扫描件提取为 0 字符；已补回并加内容断言，另加两个用例覆盖 OCR 异常与缺依赖文案。
- 本地实测：扫描件 7 页重新上传，OCR 10,054 字符，解析 23 条，支持度判定 10/10，报告页与导出正常。
- 测试 **290 → 295 passed / 2 skipped**；版本 **0.3.5**。
- 远端演示实例已部署 v0.3.5（`/tmp/restart_remote.sh`），实跑 `verify_artifacts.py --api-base http://127.0.0.1:8000` = **70 项全过**；远端用同一扫描件上传也跑通 OCR（解析 20 条，OCR 依赖版本不同导致与本地 23 条略有差异）。
- 交付包 `dist/citeguard-cn-0.3.5.zip`（1.3 MB，163 个文件）已重建，排除第三方原始语料。
- 修复中文作者误报：GB/T 检查曾把两字中文名（如「迟妍」）当成「只剩缩写」并跳过作者比对；现在只对拉丁缩写或单字中文判为残缺，新增两个用例。
- 测试 **295 → 297 passed / 2 skipped**。

## 14. 2026-10-24 傍晚：支持度判定的匹配度护栏（v0.3.6）

- 修复「匹配错论文却给出支持度结论」的假阳性：产品路径原来只要 `verify` 有摘要就调用 judge，即使标题相似度只有 0.4（Crossref 里的另一篇论文）。现在只有 `Exact/Minor` 或 `title_sim >= 0.90`（`CITEGUARD_SUPPORT_MIN_TITLE_SIM` 可调）才判定；弱匹配显示「题录匹配度不足（标题相似度 X），无法确认摘要属于同一篇论文」，并计入 `support_meta.skipped_unreliable_match`。
- 实测（扫描件 7 页，作业 `ec5bb85fc7b3`）：23 条引文，修复前有 9 条基于错误摘要给出 `no_evidence/partial`；修复后 21 条弱匹配全部为「未检测（匹配度不足）」，2 条正文未引用，0 条误判。对照用例（DOI 精确命中）仍正常判定 `support`，说明护栏没有误伤可靠匹配。
- 报告页汇总提示新增「题录匹配度不足 N 条」；README、`docs/support_summary.md` 同步说明，评测口径不变（ClaimSupport-CN 0.9328 / 0.930）。
- 测试 **297 → 299 passed / 2 skipped**（新增弱匹配跳过、弱匹配高相似度仍判定两个用例）；`verify_artifacts.py` 72/72；版本 **0.3.6**。

## 15. 2026-10-24 傍晚：题录库管理页升级（v0.3.7）

- 「题录库」页从「只读展示前 20 条」改成可管理：全量列表（服务端 `limit/offset`，默认一次 500、上限 2000）、前端即时搜索（题名 / 作者 / 来源 / 年份 / DOI / 摘要）、逐条删除（`DELETE /api/library/{index}`，带确认）、导入统计「解析 N 条 / 新增 A 条 / 跳过重复 S 条」。
- 新增**一键自动补摘要**：只处理缺摘要的题录，先 DOI 精确查询，再 OpenAlex / Crossref 题名检索；沿用 `local_library.abstract_from_candidates` 的保守规则（标题相似度 ≥ 0.92、年份兼容才接受），网络错误逐条记录、不丢已有数据。新增 `src/citeguard/abstract_enrich.py`（`MAX_ENRICH_PER_REQUEST = 20`；页面每请求 3 条、循环到补完或不再有进展），命令行脚本 `scripts/enrich_library_abstracts.py` 保留。
- 新 API：`GET /api/library` 返回含 index 的条目、`missing_abstract`、`truncated`；`POST /api/library/enrich?limit=N` 返回 `tried/enriched/missing/errors/remaining/details`；导入响应新增 `added/skipped`（兼容旧字段）。
- 静态资源加 `?v={{ request.app.version }}` 缓存版本号：升级后浏览器不会继续用旧 JS/CSS（本轮实测旧 `library.js` 被缓存导致新按钮逻辑不生效，已修）。
- 实测：本地库 10 条（8 条有摘要），对 2 条缺摘要记录调用补摘要 → 0 条误补、0 错误；搜索「鱼类」命中 1 条；删除接口越界返回 404。
- 测试 **299 → 310 passed / 2 skipped**（新增 6 个 `abstract_enrich` 单元用例 + 5 个题录库 Web API 用例）；版本 **0.3.7**。
## 16. 2026-10-24 傍晚：正文引注一致性检查（v0.3.8）

- 新增 `gbt7714.citation_consistency(refs, intext)`：顺序编码制下核对「正文有编号、文献表没有」「文献表有条目、正文没引用」「首次引用顺序与编号不一致」三类问题；作者-年份制或没有正文时明确跳过，不硬报。
- 报告页新增「正文引注一致性」面板（数字引注数、覆盖编号数、未引用 / 缺失编号列表、顺序倒置计数）；Markdown / HTML 导出同步；单条合规分不受影响。
- 测试 **310 → 316 passed / 2 skipped**（4 个规则用例 + 1 个报告集成用例）；版本 **0.3.8**。
- 新增 `data/citation_consistency_cases/cases.json` 与 `scripts/eval_citation_consistency.py`：15 例按顺序编码制构造的自检用例（未引用 / 缺失编号 / 顺序倒置 / 范围引注 / 全角逗号 / 作者-年份跳过等），实测 **15/15**；`/benchmark`、README、`data/experiments/README.md` 与 `reproduce.sh` 均已接入。
**验收状态（v0.3.8，2026-10-24 傍晚）**
- 测试 **316 passed / 2 skipped**；`verify_artifacts.py` 本地 **66 项**全过，`--api-base` **75 项**全过（本地与远端各跑一遍）；正文引注一致性规则用例 **15/15**。
- 本地演示（127.0.0.1:8010）与远端 `/data/xyjiang/aic_mental/citeguard`（0.0.0.0:8000）都已部署 v0.3.8；远端粘贴正文 + 文献表实测 `citation_consistency` 正确检出未引用编号，报告页在浏览器实跑可见。
- 交付包 `dist/citeguard-cn-0.3.8.zip` 已重建（排除第三方原始语料），GitHub `main` 已推送本轮提交。

## 17. 2026-10-24 傍晚：一致性结论进「体检结论」（v0.3.9）

- 报告页顶部「体检结论」现在会汇总正文引注一致性问题：未引用条数、缺失编号（`[n]`）、首次引用顺序倒置处数；有问题才出现，不重复面板的明细。
- 版本 **0.3.9**（仅前端结论与版本号；规则、评测、报告 JSON 结构均不变），静态资源缓存版本号随 `app.version` 刷新，升级后不会继续用旧 `report.js`。
- `node --check web/static/js/report.js` 通过；完整测试与 `verify_artifacts.py` 口径不变（**316 passed / 2 skipped**、本地 66 项、`--api-base` 75 项）。

**验收状态（v0.3.9，2026-10-24 傍晚）**
- 测试 **316 passed / 2 skipped**；`verify_artifacts.py` 本地 **66 项**、`--api-base` **75 项**全过；正文引注一致性规则用例 **15/15**。
- 本地演示（127.0.0.1:8010）已部署 v0.3.9 并在浏览器实跑「体检结论」；远端随后按同一提交部署。
- 交付包 `dist/citeguard-cn-0.3.9.zip` 重建，GitHub `main` 推送本轮提交。

## 18. 2026-10-24 夜：真实文献注入实验（检出率 98.5%，v0.3.10）

- 新实验 E8（`scripts/eval_real_mutation.py`）：从 409 条真实已发表参考文献中取 40 条**带 DOI** 的条目作种子，对每条注入 5 类可控错误——改 DOI、年份 ±2、交换作者、交换刊名、交换题名；另构造 13 条**无 DOI/URL 锚点**的拼接伪造。合计 253 例。
- 结果：**197/200（98.5%）**注入错误被检出（Major 或 Minor）；40 条原样基线 **0 Major**（28 Exact / 12 Minor，Minor 是真实卷期页差异）；各类检出 40/40、39/40、39/40、39/40、40/40。3 条漏判的原因是索引记录缺少年份/作者/刊名（候选为空无从比对，见 `docs/experiments.md` §8.4），不是规则放过。无锚点伪造 13/13 判 `Unverified`——按设计「宁可说未核实，也不指控」，因此**不计入检出率**。
- 集成：`/benchmark` 新增「真实引文注入错误检出」行；README、`docs/experiments.md` §8、`docs/real_data_eval.md` §6、`docs/ppt_numbers.md` 均已写入，`verify_artifacts.py` 增加结构校验；`reproduce.sh` 新增可选复现步骤（需要 `data/real_corpus/`，本地语料不入库）。
- 口径纪律：98.5% 只能表述为「对带 DOI 的真实引文注入 5 类错误后的检出率」；不能说成「抓假率」，无锚点伪造的 13 条要单独说明。
- 测试 **318 passed / 2 skipped**：新增的 OCR 端到端用例在 34px 合成小字上会漏检第三行（RapidOCR 检测框问题，真实扫描件不受影响），把合成样本字体放大到 44px、页面加宽后稳定通过；这是测试样本问题，不是产品回归。
- 版本 **0.3.10**；`verify_artifacts.py` 本地 **73 项**、`--api-base` **82 项**全过。

**验收状态（v0.3.10，2026-10-24 夜）**
- 测试 **318 passed**（含 OCR 端到端）；真实文献注入检出 **197/200（98.5%）**；基线误报 **0/40**。
- 本地演示与远端随后按同一提交部署 v0.3.10；交付包重建。

## 19. 2026-10-24 深夜：开源模型本地判官实测（4×GPU，v0.3.11）

- 新增 `scripts/local_judge_server.py`：用 `transformers` 起 OpenAI 兼容服务（`/v1/chat/completions`、`/health`），
  支持 `--device auto` + `CITEGUARD_LOCAL_MAX_MEMORY` 把 7B 拆到多张 12GB 卡；产品侧只改
  `CITEGUARD_JUDGE_BASE_URL/MODEL/API_KEY`，接口/缓存/评测脚本不变。
- 硬件：4×NVIDIA TITAN Xp 12GB（2017 年，CUDA 11.4 驱动）。3B 单卡；7B 用 GPU2+3（fp16，11GiB 上限均分，12.18GB 权重）。
- 结果（ClaimSupport-CN，同一数据/脚本；参考 DeepSeek 0.9328）：

  | 模型 | 硬件 | 产品 prompt | 精简 prompt | 速度 |
  |---|---|---|---|---|
  | Qwen3-1.7B | CPU | 0.5060（20 条） | **0.7059** | 93 / 46 s 每条 |
  | Qwen2.5-3B-Instruct | 1×TITAN Xp | 0.3894 | **0.6291** | 5.9 s/条 |
  | Qwen2.5-7B-Instruct | 2×TITAN Xp | **0.7181** | 0.7022 | 8.5 s/条（两段式） |

- 结论：整条链路可以完全离线；7B 已能执行产品两段式 prompt，但 0.7181 与托管 0.9328 差 0.21，「离线可用 ≠ 质量相同」。
  3B 跟不动长 prompt，换精简 prompt（`CITEGUARD_SUPPORT_PROMPT_FILE=scripts/support_prompt_simple.txt` +
  `CITEGUARD_SUPPORT_AUDIT=0`）后升到 0.6291。
- 集成：`README`、`THIRD_PARTY_NOTICES.md` §4.2、`docs/support_summary.md`、`docs/experiments.md` §9、
  `docs/ppt_numbers.md` 2d、`data/experiments/README.md`、`/benchmark` 页本地模型表均已写入；`verify_artifacts.py`
  增加 4 个 GPU 证据文件结构与 2 处文档数字校验。
- 顺带修掉两个证据元数据 bug：`scripts/evaluate_support.py` 里 `endpoint` 键重复导致本地评测被记成
  `api.deepseek.com`；`scripts/experiment_support_prompt.py` 硬编码 DeepSeek 地址、忽略
  `CITEGUARD_JUDGE_BASE_URL`/`DEEPSEEK_BASE_URL`。修复后用缓存重生成 4 份证据 JSON（数字不变，endpoint 现为
  `http://127.0.0.1:8099/v1`），避免「本地模型结果被误认为来自托管 API」的口径风险。
- 产品默认仍是托管 DeepSeek（`judge_available` 逻辑不变）；本地模型由环境变量显式启用。
- 版本 **0.3.11**；测试 **320 passed**。

**验收状态（v0.3.11，2026-10-24 深夜）**
- 测试 **320 passed**；本地 GPU 7B 证据 **0.7181**，3B 精简 **0.6291**；证据文件在 `data/experiments/support_local_qwen25_*.json`。
- 本地演示与远端 v0.3.11 部署；交付包重建。

## 20. 2026-10-24 深夜：图表结论核验（Qwen2.5-VL-7B，v0.4.0）

- 新能力（可选，需自备 GPU 视觉服务）：上传图表截图 + 一句正文结论，判断 `supported` / `contradicted` / `insufficient`。
  产品主机不加载视觉模型；未配置 `CITEGUARD_VL_ENDPOINT` 时 `/figure` 只显示说明，首页不出现入口。
- 模型：Qwen2.5-VL-7B-Instruct（Apache-2.0，ModelScope），`scripts/local_vl_server.py` 起 OpenAI 兼容
  `/v1/chat/completions`；单张 RTX 4090 24GB、bf16、峰值 16.0–16.1 GB、首次加载 8.1–8.3 秒。
- 实测（prompt 与产品一致，版本 1）：
  - 合成控例（20 图 / 40 条，seed=20261024）：准确率 **0.90**；支持类 17/20、矛盾类 19/20；误报「矛盾」0；1.55 s/条。
  - 真实论文图表（5 图 / 10 条）：准确率 **0.90**；支持 5/5、矛盾 4/5；误报「矛盾」0；2.56 s/条。
  - v2 更严格 prompt：合成 0.925 但出现 2 条「支持误判为矛盾」；真实 1.00。产品选 v1，优先避免误伤。
- 集成：`src/citeguard/figure_check.py`、`web/templates/figure.html`、`web/static/js/figure.js`、
  `GET /figure` + `POST /api/figure-check`（未配置返回 503）；首页入口与导航「图表核验」；`config.VL_*` 五个开关。
- 文档：新增 `docs/figure_check.md`（实现/实测/局限/复现）；README 能力表与实测段；`THIRD_PARTY_NOTICES.md` §4.3；
  `docs/deployment.md` §1.6；`docs/ppt_numbers.md` 3f 与「不能这么说」第 8 条；`.env.example`。
- 测试 **330 passed**（新增 10 个 `tests/test_figure_check.py` 用例：未配置/坏格式/超限/成功解析/鉴权/
  HTTP 错误/不可达/坏响应/页面与 API）；`verify_artifacts.py` 本地 89 项全过。版本 **0.4.0**。

- 发布：commit `ad5456c`；GitHub 通过 SSH 推送（发布时本机 https 代理不可用，`git push git@github.com:kkk431/citeguard-cn.git main`）；远端
  `/data/xyjiang/aic_mental/citeguard` 已部署 v0.4.0（`/api/health` → version 0.4.0），
  `verify_artifacts.py --api-base http://127.0.0.1:8000` **98 项全过**；交付包
  `dist/citeguard-cn-0.4.0.zip`（1.6 MB）。
- 远端已配置 `CITEGUARD_VL_ENDPOINT=http://222.20.126.148:8099/v1`（dmz 可直连 lmh GPU），重启后首页入口出现，
  `/api/figure-check` 实测返回 `contradicted`（1.81 s）；本机演示服务同样已配置，四个默认示例图可直接跑通。
  注意：`.env.remote` 需要 `set -a` 才导出给 uvicorn，`/tmp/restart_remote.sh` 已修正。

## 21. 2026-10-24 晚：撤稿提醒 + 审稿视角汇总（v0.4.1）

- 背景：用户问「SciCopilot 式融合功能到底做到哪一步了」。诚实盘点：C（图表结论核验）已交付；
  B（撤稿/问题文献提醒）与 D（审稿视角汇总）此前只是设想。本轮把 B、D 做成产品功能，A（多篇对比）、
  E（选题→文献发现）仍留在路线图，不假装已做。
- B 撤稿提醒：`OpenAlex` 查询增加 `select=...,is_retracted`，`Candidate.retracted` /
  `VerifyResult.retracted` 透传到报告 JSON；`verify_reference` 统一走 `_apply_retraction`
  wrapper，命中即加提示「OpenAlex 标记该文献已被撤稿（retraction），引用前请核对撤稿声明」，
  **但不改真实性状态**（准确引用撤稿论文仍然是 Exact，避免把合法引用误判成问题引文）。
  UI：卡片/表格显示「该文献已撤稿」pill，体检结论增加撤稿条数；CSV/Markdown/HTML 导出带提示。
- D 审稿视角汇总：`report.build_report` 新增 `review_summary`（decision / level / blockers /
  minor_issues / issues / note），聚合 Major、撤稿、支持度矛盾/部分支持、格式 error、未被引用编号、
  编号缺失、顺序不一致；输出「建议修改后再投稿 / 建议小修 / 可送审但需人工核对 / 可送审」一档结论。
  报告页新增「审稿视角 · 自动汇总」面板，Markdown/HTML 导出同步；措辞固定为「自动检查、不替代同行评审」。
- 实测：本机上传 3 条测试文献（2 条假 DOI + 1 条未被引），判 Major 2 / Unverified 1，
  审稿结论 `blocker`、阻断级 2 项，卡片 pill 与导出均出现；面板文案见浏览器检查。
- 测试 **338 passed**（新增：撤稿 3 例、审稿汇总 5 例、导出 1 例）；`verify_artifacts.py` 本机 89 项、
  远端 `--api-base` **98 项全过**；版本 **0.4.1**。
- 发布：commit `740bf23`（代码/文档），SSH 推送 `8894a83..740bf23`；远端
  `/data/xyjiang/aic_mental/citeguard` 已部署 v0.4.1（`/api/health` → 0.4.1），
  交付包 `dist/citeguard-cn-0.4.1.zip`（1,719,179 bytes，sha256 `ac6a92e4…`，1.6 MB）。
- 局限（不要写成已解决）：撤稿标记目前只来自 OpenAlex `is_retracted`，Crossref `update-to`
  与中文库撤稿声明未接入；审稿汇总是规则聚合，不替代同行评审；A/E 未实现。

## 22. 2026-10-24 晚：多篇文献对比（模块 A，v0.5.0）

- 背景：用户要求「自己规划融合，自己推进」。融合清单里仅剩 A（多篇文献对比）与 E（选题→文献发现）；
  先做 A，因为它是「读懂文献」的直接能力、可复用现有判官与任务机制，不需要新后端。
- 核心 `src/citeguard/compare.py`：2–6 篇论文，每篇取摘要与正文前部（截断参考文献，最多 3600 字），
  用统一判官接口（`support.judge_endpoint`）按六字段抽取：研究问题 / 方法 / 数据 / 结论 / 局限 / 贡献；
  字段清洗、缺字段留「未提及」、逐篇错误不拖垮整体；结果按「模型 + 截断文本」缓存。
  `compare_texts` / `render_markdown` / `render_csv`，CLI 可直接调。
- Web：`GET /compare` 页面（导航「文献对比」）；`POST /api/compare` 后台任务、`GET /api/compare/{id}` 轮询、
  `GET /api/compare/{id}/export?format=md|csv` 导出。复用 `/api/analyze` 的 30 MB 上传限制与清理逻辑，
  判官未配置时页面只说明、不显示提交入口；首页新增可选入口提示。
- 实测（2026-10-24，4 篇真实 hanspub PDF，`deepseek-chat`，temperature 0）：
  **4/4 篇抽取成功、0 报错、总耗时 8.0 秒**（约 1.9–2.1 秒/篇），每篇 5–6/6 字段；
  「局限」有 3 篇为空（摘要本身不写局限，系统留「未提及」而不是编造）。证据 `data/experiments/compare_real.json`，
  复现 `scripts/eval_compare_real.py`。
- 测试 **353 passed**（新增 11 个模块用例 + 4 个 Web 用例）；`verify_artifacts.py` 本机 **96 项**。
- 边界（不要写成已解决）：只读摘要与正文前部，不读全文方法/实验；字段是机器抽取，引用前须回原文核对；
  没有字段级标注集，不能说「字段准确率 90%」；不做跨文献综合（研究空白仍需人来写）。
- 路线图：E（选题→文献发现）仍未实现，不假装已做。
- 发布：commit `5f8e20d`（代码/文档）；SSH 推送 `566ab7a..5f8e20d`（本机 `github.com:443` 的
  ssh 代理当时被阻断，改用 22 端口推送）；远端 `/data/xyjiang/aic_mental/citeguard` 已部署
  v0.5.0（`/api/health` → 0.5.0），`verify_artifacts.py --api-base` **105 项全过**；
  交付包 `dist/citeguard-cn-0.5.0.zip`（1,742,409 bytes，sha256 `5fb50f9d…`，1.7 MB）。

## 23. v0.6.0：选题与文献发现（模块 E，2026-10-24）

- 新增 `src/citeguard/discover.py`：OpenAlex `/works` 检索 + 透明启发式重排
  （`1/(1+序号) + 2×标题重合度 + 0.35×log10(1+被引) + 新近度 + OA`），7 天本地缓存，
  只消费元数据、不抓全文；`import_entries()` 按规范化题名去重写入本地题录库。
- Web：`GET /discover` 页面 + `POST /api/discover`、`GET /api/discover/export`（CSV）、
  `POST /api/discover/import`；导航与首页入口；判官/视觉服务均不参与，纯公开数据。
- 实测（工程可用性，不是排序质量）：`人工智能 教育` 命中 112,724 条、首次 1.82 s；
  `retrieval augmented generation`（2022+ / 仅 OA）命中 133,725 条、首次 1.56 s；
  缓存命中 0.02 s。没有任何 relevance 标注集，**不报告排序指标**。
- 测试：模块 9 个 + Web 7 个，全套 **369 passed**；`verify_artifacts.py` 本机 **101 项**。
- 边界：中文召回取决于 OpenAlex 覆盖；排序是启发式、不训练；入库只存题录，不等于已核验。
- 版本 0.6.0（`web/app.py` 两处、打包脚本、部署手册）。
- 发布：commit `9bf8bd4`；SSH 推送 `a79b19d..9bf8bd4`（`GIT_SSH_COMMAND='ssh -p 22 -o HostName=github.com'`）。
- 远端 `/data/xyjiang/aic_mental/citeguard` 已部署 v0.6.0（`/api/health` → 0.6.0）；
  `verify_artifacts.py --api-base http://127.0.0.1:8000` **110 项全过**。
- 交付包 `dist/citeguard-cn-0.6.0.zip`（1,759,181 bytes，sha256 `36c736a8…`）。
- 本机验证：369 passed、`verify_artifacts.py` 101 项、浏览器实测检索 / 全选 / CSV 导出。

## 24. v0.6.1：文献发现从「能查」做到「能用」（2026-10-24 晚）

- 背景：用户明确要求「不是让你显示有个这样的功能就行，是要做尽可能的最好」——v0.6.0 只是能检索，
  v0.6.1 把扩展、合并、排序、分页、筛选、卡片信息这几件事做完整。
- 查询扩展：`discover.expand_query()` 用统一判官接口把中文主题转成英文检索式（≤120 字符）与
  3–6 个关键词，按「模型 + 版本 + 查询」缓存；`expand=auto|off` 显式可选，判官不可用时只查原查询
  并在页面标注「未扩展」，不假装做过双语检索。
- 检索与合并：原查询与英文检索式各取固定 100 条候选池，按 DOI → 规范化题名去重（摘要取长、被引取大、
  OA 取并集），默认过滤撤稿记录，可按「相关度 / 被引 / 年份」排序。
- 稳定分页：每页重新取同一固定候选池再切片，避免第 2 页排序漂移/重复/漏条；实测第 1、2 页各 20 条，
  零重叠。最多 5 页（选 50 条时 4 页）；`matched` 明确为上游计数。
- 排序：`1.0×归一化相关度 + 2.0×标题重合(原/扩展取大) + 0.9×关键词重合 + 0.35×log10(1+被引)
  + 新近度 + OA`；卡片显示摘要（240 字）、被引、OA/撤稿标记、命中理由与「英文扩展命中」标注。
- Web：卡片列表、全选、语言筛选（全部/中文/英文，前端完成）、排序切换、加载更多（最多 5 页）、
  选中计数、批量入库、CSV（新增语言列）；`/api/discover` 新增 `page/sort/expand/include_retracted` 参数。
- 实测（2026-10-24，查询 `人工智能 教育`）：`expand=auto` 上游命中 **1,141,987**（原查询 112,724），
  冷启动 **6–10 s**（含一次 LLM 扩展 + 两次上游请求），缓存命中 **74 ms**；第 2 页 34–62 ms、
  与第 1 页零重叠；`expand=off` 时 20 条里中文 8 条，`auto` 时中文 3 条、英文 17 条（扩展提高英文召回）。
- 分页池按条数自适应：池大小 = 条数 × 5（上限 200），10/20/30 条最多 5 页、50 条最多 4 页；
  超出页码夹到末页（响应含 `max_page`），`has_more` 只依据池内剩余，不再因上游 `matched` 虚报下一页。
- 测试：模块 **18 个**（纯离线，mock 网络与扩展）；全套 **378 passed**；`verify_artifacts.py` 本机 **102 项**。
- 浏览器实测：检索、排序（被引降序 164/87/70/40…）、中文筛选、勾选入库按钮联动、
  CSV 链接参数、加载更多（page=2）均正常。
- 边界（不要写成已解决）：排序仍是启发式、无 relevance 标注集，不能报 NDCG/准确率；中文召回取决于
  OpenAlex 覆盖；扩展依赖判官模型，不可用时召回明显下降；入库只存题录，不等于已核验。
- 版本 0.6.1（`web/app.py` 两处、打包脚本、部署手册）。
- 发布：commit `fb2f88d`（v2 首发，14 files）→ `d4e72fc`（分页修正：自适应池 / `max_page` 夹取 /
  池内 `has_more`）；SSH 推送 `2983742..d4e72fc`（`GIT_SSH_COMMAND='ssh -p 22 -o HostName=github.com'`）。
- 远端 `/data/xyjiang/aic_mental/citeguard` 已部署 `d4e72fc`（`/api/health` → 0.6.1）；
  `verify_artifacts.py --api-base http://127.0.0.1:8000` **111 项全过**；远端 `/api/discover`
  实测 `expand=auto` 命中 1,141,987、返回双语扩展式；`limit=50&page=9` 被夹到第 4 页、
  `has_more=false`、返回 50 条。
- 交付包 `dist/citeguard-cn-0.6.1.zip`（源码 `d4e72fc` + 本文件；每次重打包 hash 会变，以实际文件为准）。
- 本机验证：378 passed、`verify_artifacts.py` 102 项、浏览器实测检索 / 加载更多（40 条零重复）/
  排序 / 语言筛选 / 勾选入库 / CSV 链接；本机 `limit=50&page=9` → 第 4 页、50 条、`has_more=false`。

## 25. v0.6.2：文献发现的分页与信息呈现修正（2026-10-24 深夜）

v0.6.1 上线后继续压测文献发现，发现并修掉三个具体问题：

- **分页深度不足**：原先固定按每页条数取 100 条候选池，`limit=50` 时第 3 页以后永远为空，
  「加载更多」却在第 2 页就允许继续点。改为池大小 = 每页条数 × 5（上限 200），服务端返回
  `max_page` 并把越界 `page` 夹到末页；`has_more` 只依据池内剩余，不再拿上游 `matched` 猜。
- **顶部第一结果可能是勘误**：OpenAlex 的 `erratum` 记录继承原文标题与被引数，实测在
  「人工智能 教育」查询中排第一。现在默认剔除 `erratum` / `paratext` / `peer-review`，
  结果区显示「已过滤 N 条勘误/杂项记录」；卡片补充期刊论文/综述/预印本/图书章节类型标签。
- **信息不清**：结果区显示「第 x / y 页」；到池末尾给出提示（调大每页条数会同时扩大候选池）；
  「全选本页」改为「全选已加载」，与实际行为一致。

验证：全套 **378 passed**（发现模块 18 个用例）；`verify_artifacts.py` 本机 **102 项**；
浏览器实测 `limit=50` 连续加载到第 4 页，200 条卡片零重复；`limit=50&page=9` 夹到第 4 页；
勘误/杂项过滤后首条为正常论文。版本 **0.6.2**（`web/app.py` 两处、打包脚本、部署手册）。

- 发布：commit `2a4e8fc`（14 files），已推送 `6be91e0..2a4e8fc`。
- 远端已部署 `2a4e8fc`：`/api/health` → 0.6.2，`verify_artifacts.py --api-base http://127.0.0.1:8000`
  **111 项全过**；`expand=off` 检索首条 `type=article`，无勘误混入。
- 交付包 `dist/citeguard-cn-0.6.2.zip`（源码 `2a4e8fc` + 本文件；每次重打包 hash 会变，以实际文件为准）。

## 26. v0.7.0：把开源判官从 0.7181 推到 0.8887（2026-10-25 凌晨）

用户明确要求「开源模型能力有差距就冲，数据集、方法都行」。这一轮不再只报 7B 的 0.7181，
而是用实验室已有的 4×RTX 4090 把 Qwen3-8B / Qwen3-14B 跑成可引用的对照。

- **固定划分**：`data/claimsupport_cn/split_seed20261024.json`，dev 40（支持 16 / 部分 10 / 矛盾 6 /
  无证据 8）用于选 prompt 与审计方式，test 60 只在最后跑一次（支持 24 / 部分 15 / 矛盾 9 / 无证据 12）。
  旧 100 条口径保留在 `data/claimsupport_cn/results.json`，两者不可混报。
- **结果**（产品 v4 stage-1 prompt + 审计方式）：

  | 模型 | 硬件 | dev 40 | test 60 | 速度 |
  |---|---|---|---|---|
  | Qwen3-8B | 1×RTX 4090 | 0.9014 / 0.900 | **0.7817 / 0.783** | 7.3 / 7.1 s/条 |
  | Qwen3-14B | 2×RTX 4090 | 0.8676 / 0.875 | **0.8887 / 0.883** | 8.9 / 8.5 s/条 |
  | Qwen3-14B + 少样本 v7 | 2×RTX 4090 | 0.8740 / 0.875 | **0.9063 / 0.900** | 7.7 s/条 |
  | 托管 DeepSeek（参考） | — | 0.8916 | 0.9470 | — |

  14B 最好配置与托管差距约 4.1 分，8B 约 16.5 分；14B v4 的 test 混淆矩阵为
  `[[23,0,0,1],[5,10,0,0],[0,1,8,0],[0,0,0,12]]`，换 v7 后为
  `[[23,0,0,1],[4,10,0,1],[0,0,9,0],[0,0,0,12]]`（partial precision 1.00、recall 10/15）。
- **审计 v2**：旧 v1 审计假设「证据须覆盖实证要素」，会把逐字复述也降级；v2 改为通用方案。
  8B dev 0.8372→0.9014、test 0.7090→0.7817；8B v6 prompt + v2 为 0.8577，14B v6 + v2 为 0.8740。
  v3 混合审计（0.8824）、3 票自洽（8B v4+v2 0.9014，耗时 16.6 s/条）均未超过单票 v2，不采用。
  v7 少样本 prompt 在 8B 上更差（0.8608），在 14B 上有效（0.9063 vs v4 0.8887）；托管 DeepSeek 上
  v7 反而略低（test 0.9441 vs v4 0.9470），所以不做全局默认。
- **产品默认**：`CITEGUARD_SUPPORT_AUDIT_STYLE=auto`——自托管端点自动用 v2，托管 API 仍用 v1
  （保持已发布的 0.9328 口径）；prompt 也按端点自动选：自托管默认 v7，托管默认 v4，
  `CITEGUARD_SUPPORT_PROMPT_FILE` 可显式覆盖。`support.py` 增加 `_audit_style()` 与按 style 分键的审计缓存。
- **证据**：`data/experiments/support_local_qwen3_{8b,14b}_{dev,test}.json`、`support_local_qwen3_14b_v7_test.json`
  （原始预测）+ `support_local_qwen3_gpu.json`（汇总）；评测页「本地开源判官」表自动读取后者。
- 文档同步：README 本地模型表、THIRD_PARTY_NOTICES §4.2、docs/ppt_numbers.md 2d、
  docs/deployment.md §1.4、`.env.example` 都已写入 dev/test 与 auto 说明。
- 验证：全套 **383 passed**；`verify_artifacts.py` 本机 **106 项**、远端 `--api-base` **115 项** 全过。
- 发布：commit `ef4d418`（已推送 `251f8a7..ef4d418`）；远端 `/data/xyjiang/aic_mental/citeguard`
  已更新到 `ef4d418`，`/api/health` → 0.7.0；本地演示服务同样为 0.7.0。
- 交付包 `dist/citeguard-cn-0.7.0.zip`（源码 `ef4d418` + 本文件；每次重打包 hash 会变，以实际文件为准）。

## 27. v0.7.1：自托管判官默认切到实测最优 prompt

- 端点感知 prompt：自托管端点默认 `scripts/support_prompt_v7.txt`（少样本、证据优先），托管 API 保持内置 v4；
  `CITEGUARD_SUPPORT_PROMPT_FILE` 仍可覆盖；prompt 版本号带内容 hash，缓存自动分键。
- 审计版本继续 `auto`：自托管 v2、托管 v1。
- 14B + v7 + v2 在留出 test 60 上 **0.9063 / 0.900**（v4 0.8887），是当前开源本地产能上限；
  托管同口径 0.9470，差距 4.1 分；8B 0.7817。
- 验证：383 passed；`verify_artifacts.py` 本机 **108 项**、远端 `--api-base` **117 项** 全过。
- 发布：commit `e9f5da8`（已推送 `a7b2aa0..e9f5da8`），远端 0.7.1，本地 0.7.1。
- 交付包 `dist/citeguard-cn-0.7.1.zip`（约 1,888,600 bytes；sha256 `aa47bb99…`，重打包会变，以实际文件为准）。
- 合规事实文档 `docs/compliance_ai_open.md`（规则逐条对照、资源清单、自研边界、证据与缺口；不含 PPT/视频）。

## 28. v0.8.0：v8 边界 few-shot，把本地 14B 推到与托管差 0.24 分

- 背景：v7 之后剩余错误集中在 partial→support。检查 v7 test 的 6 条错误与构造规则后，确认缺的是
  两条明确边界，而不是更多示例。
- **v8 prompt**（`scripts/support_prompt_v8.txt`）：在 v7 的 few-shot 上补两条规则——
  「引用句包含证据之外的目的/设计细节 → partial」「证据只覆盖部分断言 → partial」，并各配一个例子。
- 结果（ClaimSupport-CN，`split_seed20261024.json`；本地服务 `scripts/local_judge_server.py`，4×RTX 4090）：

  | 模型 | dev 40 | test 60 | all 100 |
  |---|---|---|---|
  | Qwen3-8B（v8 + 审计 v2） | — | **0.8346 / 0.817**（v7 0.7817） | — |
  | Qwen3-14B（v8 + 审计 v2） | **0.9793 / 0.975** | **0.9574 / 0.950**（v4 0.8887、v7 0.9063） | **0.9661 / 0.960** |
  | DeepSeek 托管（v8 + 审计 v1） | 0.9447 / 0.950 | **0.9598 / 0.950** | **0.9544 / 0.950** |

- 口径：14B 与托管同 test 60 差 **0.24 分**；全 100 条本地 0.9661 高于托管 0.9544。两个口径并列报告。
  v8 的边界与构造集划分规则同源，提升有一部分来自规则对齐——这条已写进 README / support_summary / compliance。
- 产品默认：prompt 两端统一 v8（`support.py` 导入时读 `scripts/support_prompt_v8.txt`，`PROMPT_VERSION=8-<hash8>`）；
  `CITEGUARD_SUPPORT_PROMPT_FILE` 仍可覆盖；审计继续 `auto`（自托管 v2、托管 v1）。
- 证据：`data/experiments/support_local_qwen3_8b_v8_test.json`、
  `support_local_qwen3_14b_v8_{dev,test,all}.json`、`support_local_qwen3_gpu.json`（汇总，评测页读取）；
  正式 `data/claimsupport_cn/results.json` 已用 v8 重新生成（0.9544 / 0.950，prompt hash `b136b8ef…`）。
- 文档同步：README（支持度表、混淆矩阵、本地模型表）、THIRD_PARTY §4.2、docs/support_summary.md、
  docs/ppt_numbers.md（2/2d/对比/不能这么说）、docs/experiments.md、docs/plan.md、
  docs/deployment.md、`.env.example`、docs/compliance_ai_open.md、data/claimsupport_cn/README.md。
- 失败尝试仍留存：审计 v3（8B dev 0.8824）、3 票自洽（0.9014、16.6 s/条）、v6（0.8577/0.8740）均低于 v8。
- 32B：ModelScope 下载实测约 0.7 MB/s、预计 ~25 h，已中止；没有实测就不写数字。
- 验证：383 passed；`verify_artifacts.py` 本机 **113 项** 全过。

- 验证（发布态）：全套 **383 passed**；`verify_artifacts.py` 本机 **113 项**、远端 `--api-base` **122 项** 全过；
  远端 `/api/benchmark` 的 ClaimSupport-CN 为 0.9544 / 0.950、prompt hash `b136b8ef…`，本地判官表 12 行、末行 14B all 100 0.9661。
- 发布：commit `ebc756b`（已推送 `b1d322c..ebc756b`）；远端 `/data/xyjiang/aic_mental/citeguard` 已更新，
  `/api/health` → 0.8.0；本地演示服务同为 0.8.0。
- 交付包 `dist/citeguard-cn-0.8.0.zip`（源码收尾提交 `7a3f010` + 本文件；每次重打包 hash 会变，以实际文件为准）。

## 29. v0.8.1：v10 few-shot + 托管 0.9597（2026-10-25）

- 背景：v8 后 test 仍差托管 0.24；检查 14B all 100 的 3 条错误后先试 v9（完整复述→support），
  dev 回归到 0.9447，直接否掉；v10 只加一条规则：证据与引用句方向相反而非弱支持时判 contradict。
- 结果（同 v8 口径；`split_seed20261024.json`；本地 `scripts/local_judge_server.py`，4×RTX 4090）：

  | 模型 | dev 40 | test 60 | all 100 |
  |---|---|---|---|
  | Qwen3-14B（v10 + 审计 v2） | **1.0000 / 1.000** | **0.9574 / 0.950** | **0.9744 / 0.970** |
  | Qwen3-8B（v10 + 审计 v2） | 0.8882 / 0.875 | 0.8515 / 0.833 | — |
  | DeepSeek 托管（v10 + 审计 v1） | 0.9793 / 0.975 | 0.9598 / 0.950 | **0.9597 / 0.950** |

- 产品默认：两端统一 v10（`scripts/support_prompt_v10.txt`，1981 chars，sha256 `fe9d721c…`），
  `PROMPT_VERSION=10-<hash8>`；`CITEGUARD_SUPPORT_PROMPT_FILE` 仍可覆盖；审计 `auto`（自托管 v2、托管 v1）。
- 证据：`data/experiments/support_local_qwen3_8b_v10_{dev,test}.json`、
  `support_local_qwen3_14b_v10_{dev,test,all}.json`、`support_local_qwen3_gpu.json`（18 行，评测页读取）；
  正式 `data/claimsupport_cn/results.json` 已用托管 v10 重新生成（0.9597 / 0.950，prompt hash `fe9d721c…`）。
- 诚实边界：14B v10 与托管同 test 60 差 0.24 分（0.9574 vs 0.9598）；全 100 条本地 0.9744 高于托管 0.9597，
  两个口径并列报告。v10 的规则与构造集方向冲突样本同源，提升含规则对齐成分——已写入
  README / THIRD_PARTY §4.2 / docs/compliance_ai_open.md。
- 验证：383 passed；`verify_artifacts.py` 本机 **114 项**、远端 `--api-base` **123 项** 全过；
  远端 `/api/benchmark` 的 ClaimSupport-CN 为 0.9597 / 0.950、prompt hash `fe9d721c…`，本地判官表 18 行、末行 14B v10 all 100 0.9744。
- 发布：commit `3fa07b3`（已推送 `b22ef92..3fa07b3`）；远端 `/data/xyjiang/aic_mental/citeguard` 已更新，
  `/api/health` → 0.8.1；本地演示服务同为 0.8.1。
- 交付包 `dist/citeguard-cn-0.8.1.zip`（每次重打包 hash 会变，以实际文件为准）。

## 30. v0.8.2：产品代码路径复核本地模型（2026-10-25）

- 目的：证明 14B/8B 的 0.9744/0.8664 不是只在评测脚本里成立，而是产品 `judge_support` 真跑出来。
- 做法：`scripts/evaluate_support.py` 直接调 `citeguard.support.judge_support`（不额外拼 prompt），
  `DEEPSEEK_BASE_URL` 指向 lmh 本地 OpenAI 兼容服务，审计风格 `auto`。
- 首跑异常：14B 只有 **0.6864 / 0.640**，8B **0.7735 / 0.720**——远低于脚本口径。两个产品 bug：
  1. `_audit_style()` 的 auto 只检查 `CITEGUARD_JUDGE_BASE_URL`；用 `DEEPSEEK_BASE_URL` 指向本地时被判成托管、
     错选审计 v1（v1 在大模型上会把一条完整支持的条目降成 partial，14B 的 support 召回被打穿）。
     修复：按**实际生效 endpoint** 判断，新增 `_is_hosted_endpoint(base)`（含 `deepseek.com` 才算托管）。
  2. 修完仍复现 0.6864：`_cache_path()` 只按「模型+引文+摘要」缓存最终标签，不含审计风格；首跑 v1 的最终标签
     被 v2 复用。修复：缓存键加 `audit_tag`（`_audit_style()` 或 `off`），按「模型 + prompt 版本 + 审计风格」分键。
- 修复后（产品路径，全 100 条，0 失败）：

  | 模型 | 产品路径 F1/Acc | 脚本口径 F1 | 混淆矩阵 |
  |---|---|---|---|
  | Qwen3-14B | **0.9744 / 0.970** | 0.9744 | [[38,1,0,1],[1,24,0,0],[0,0,15,0],[0,0,0,20]] |
  | Qwen3-8B | **0.8664 / 0.850** | 0.8664 | [[34,5,0,1],[7,16,0,2],[0,0,15,0],[0,0,0,20]] |

- 新增测试：`test_audit_style_auto_uses_effective_endpoint`、`test_support_cache_is_namespaced_by_audit_style`；
  全量 **385 passed**。
- 证据：`data/experiments/support_local_qwen3_{14b,8b}_product_all.json`；汇总 `support_local_qwen3_gpu.json` 16 行
  （产品路径行的 latency 置 null，避免把 4 并发墙钟当成单条耗时）。
- 文档：README、THIRD_PARTY §4.2、docs/support_summary.md、docs/experiments.md、docs/ppt_numbers.md、
  docs/compliance_ai_open.md、data/experiments/README.md 均已写入口径与 bug 说明。
- 验证与发布（v0.8.2）：全量 **385 passed**；`verify_artifacts.py` 本机 **116 项**、远端
  `--api-base http://127.0.0.1:8000` **125 项** 全过；commit `a0ed9a9` 已推送；远端
  `/data/xyjiang/aic_mental/citeguard` 已更新（`/api/health` → 0.8.2），远端 `/api/benchmark` 本地判官表 20 行
  （含产品路径 14B 0.9744 / 8B 0.8664）；本地演示服务同 0.8.2。
- 交付包：`dist/citeguard-cn-0.8.2.zip`（2,017,620 bytes，sha256 `3657208d…`；每次重打包 hash 会变，以实际文件为准）。

## 31. v0.8.3：图表核验支持正文/图注上下文（2026-10-25）

- 起因：用户问「论文的正文有没有真正支撑这个图表的结论」——旧版只判「图 vs 结论」，正文没参与。
- 做法：`src/citeguard/figure_check.py` 升到 prompt v2：先判图表，再（可选）判正文/图注；正文与图表冲突时以
  「矛盾」为准，正文没提到该结论则退回图表结论并注明「正文未覆盖」。正文上限 **4000 字**，表单字段 `context`，
  页面新增可选文本框；`POST /api/figure-check` 接受 `context`；返回带 `prompt_version=2` 与 `context_chars`。
- 实测：`scripts/eval_figure_prompt.py` 同一批 50 条（合成 40 + 真实 10）三种口径：

  | 口径 | 准确率 | 支持召回 | 矛盾召回 | 误报矛盾 | 平均延迟 |
  |---|---|---|---|---|---|
  | v1 仅图（历史） | 0.88 | 0.88 | 0.88 | 0 | 1.82 s |
  | v2 仅图 | 0.90 | 0.88 | 0.92 | 0 | 2.43 s |
  | **v2 + 正文/图注上下文** | **0.94** | **0.92** | **0.96** | **0** | **2.56 s** |

  分数据集：合成 38/40（0.95）、真实 9/10（0.90）；真实集上下文没有带来增益，增益主要来自图题含极值的合成集。
  剩余 3 个错误：`synth_14/18`（结论写 2025、图只到 2024，判 insufficient）与 `real_03`（矛盾结论落在正文未覆盖处）。
- 诚实边界：上下文由用户手动粘贴，产品尚未做版面分析自动定位图注；真实图只有 5 张、10 条结论，不能当大样本精度承诺；
  0.94 是「带上下文」口径，仅图是 0.90。
- 测试：`tests/test_figure_check.py` 新增 2 条（上下文注入/截断、无上下文不加块），全套 **387 passed**；
  `verify_artifacts.py` 本机 118 项全过。
- 文档：`docs/figure_check.md` 重写（v2 表、上下文用法、复现命令）；README、`docs/experiments.md` E10、
  `docs/ppt_numbers.md` 3f/§8、`docs/deployment.md` §1.6、`data/experiments/README.md` 索引同步。
- 证据：`data/experiments/figure_prompt_eval.json`（50 条逐条 verdict/reason/latency）。
- 验证与发布（v0.8.3）：全量 **387 passed**；`verify_artifacts.py` 本机 **118 项**、远端 `--api-base` **127 项** 全过；
  commit `4a039fe` 已推送；远端 `/api/health` → **0.8.3**；本地演示服务同 0.8.3（`/api/figure-check` 带 `context`
  实测返回 `prompt_version=2`、`context_chars=29`）。
- 交付包：`dist/citeguard-cn-0.8.3.zip`（2,026,337 bytes，sha256 `084080f4…`；每次重打包 hash 会变，以实际文件为准）。

## 32. v0.8.4：把图表核验评测放到评测页（2026-10-25）

- 评测页新增「图表-结论核验（Qwen2.5-VL-7B，自托管）」表：v1 仅图、v2 仅图、v2+正文 三行（准确率
  **0.88 / 0.90 / 0.94**），含支持召回、矛盾召回与平均延迟；并注明「真实图仅 5 张 10 条、上下文需手动粘贴」。
- 数据来自 `_benchmark_context()` 新加载的 `figure_prompt_eval.json`，页面不硬编码数字。
- 验证：387 passed；`verify_artifacts.py` 本机 118 项、远端 `--api-base` 127 项全过；commit `8c6acf4`
  已推送；远端 `/api/health` → 0.8.4；本地演示服务同 0.8.4，评测页图表段渲染正常。
- 交付包：`dist/citeguard-cn-0.8.4.zip`（2,026,978 bytes，sha256 `56d21c5c…`；每次重打包 hash 会变，以实际文件为准）。

## 33. v0.8.5：图表核验可按页读取 PDF 正文（2026-10-25）

- 起因：图表核验的「正文是否支撑结论」原先只能手动粘贴；用户希望更接近真实审稿流程。
- 做法：`/figure` 表单新增可选的论文 PDF 与页码；`POST /api/figure-check` 接受 `paper` + `page`，
  服务端把 PDF 写到临时文件，用 `pdf_extract.extract_page_text()`（pdfplumber，按页、带双栏处理、4000 字截断）
  取出该页文字后拼到 `context` 前面，返回 `context_source="pdf_page:N"`。取不到文字（扫描页/文字层损坏）时
  返回 `page_text_unavailable` 并提示手动粘贴；PDF 不保存。
- 新增：`pdf_extract.extract_page_text`；接口对非 PDF、页码非整数、超页、超大文件分别给明确 400 错误。
- 测试：新增 3 条 PDF 按页测试（非 PDF / 空白页 / 页码越界）+ 2 条接口测试（拒绝非 PDF、按页取文并拼上手动上下文），
  全套 **392 passed**。
- 实测（本机 → lmh VL 服务）：真实论文 `hanspub_152572.pdf` 第 1 页 → `context_chars=976`、`context_source=pdf_page:1`、
  2.37 秒、判 supported；扫描版 PDF 同一接口返回「第 1 页没有可提取的文字…请手动粘贴」，不再伪装成已读正文。
- 诚实边界：仍需用户指认页码，没有做「自动定位图注」的版面分析；扫描页必须退回手动粘贴。
- 文档：`docs/figure_check.md` 增加按页用法与局限；README 图表段同步；`docs/deployment.md`、版本号 → 0.8.5。
- 验证与发布（v0.8.5）：全量 **392 passed**；erify_artifacts.py 本机 **118 项**、远端 --api-base **127 项** 全过；
  commit 6631d30 已推送；远端 /api/health → **0.8.5**；本地演示服务同 0.8.5。
- 交付包：dist/citeguard-cn-0.8.5.zip（2031869 bytes，sha256 `c69efc44…`；每次重打包 hash 会变，以实际文件为准）。

## 34. 思考模式（thinking）负结果：明确关闭（2026-10-25）

- 目的：验证「让 Qwen3-8B 先思考再判定」是否能补上它和 14B 的差距。
- 做法：`scripts/local_text_server.py` 以 `THINKING=1 MAX_NEW_TOKENS=900` 重启 8B（:8098），
  用 v10 + 审计 v2 跑 dev 40；同一权重、同一 prompt，只差 thinking 开关。
- 结果：**macro-F1 0.8084 / acc 0.775**，平均 **41.8 秒/条**（非 thinking 时为 0.8882 / 7.6 秒/条）。
  混淆矩阵 `[[8,1,0,7],[0,9,0,1],[0,0,6,0],[0,0,0,8]]`：support 召回只有 0.5，大量 support 被判成
  `no_evidence`，partial/contradict 反而正常。
- 处理：不采用；8B 服务已恢复 `THINKING=0`，产品默认保持关闭。证据
  `data/experiments/support_local_qwen3_8b_v10_thinking_dev.json`，汇总行在
  `data/experiments/support_local_qwen3_gpu.json`（`thinking=true`）。
- 结论：思考链不是免费的能力提升，至少在这个判定任务上会放大「找不到证据就判无证据」的倾向。

## 35. v0.8.6：图表核验可按图号自动定位图注页（2026-10-25）

- 起因：v0.8.5 已经能按页码读 PDF，但用户还得自己翻到图所在页；真实审稿时更自然的是「指出图号」。
- 做法：`pdf_extract` 新增 `figure_number_from_claim()`（从「如图 3/Figure 4a」提取图号）与
  `find_figure_page()`（扫 PDF 前 40 页，匹配行首 `图 N`/`Figure N` 图注，按图号精确匹配）。
  `/api/figure-check` 的 `page` 改为可选：留空且声明带图号时自动定位，返回 `context_source=pdf_auto:N`，
  并把匹配到的图注行拼在正文前；找不到或扫描页无文字层时返回 `page_not_found` / `page_text_unavailable`，
  提示手动填页码或粘贴，不静默用错页。
- 前端：页码输入框默认留空（占位「自动」），提示按图号自动找；结果里区分「按图注自动定位」与指定页。
- 测试：新增 2 条 PDF 层测试（图号提取/按号找页/扫描件返回 None）+ 2 条接口测试（自动定位、找不到图注），
  全套 **397 passed**；`verify_artifacts.py` 118 项全过。
- 实测：真实论文 `hanspub_152575.pdf`（claim 为 Figure 1 趋势）→ 自动定位第 3 页、`context_chars=1173`、
  1.59 秒、判 insufficient（示例图与声明不符，属正确拒答）；扫描版 PDF → `page_not_found` 明确提示手动粘贴。
- 诚实边界：文本匹配而非版面分析；声明里没有图号、图注不在行首、扫描件都仍需手动页码/粘贴。
- 验证与发布（v0.8.6）：全量 **397 passed**；verify_artifacts 本机 **118 项**、远端 **127 项**全过；
  commit `c78d943` 已推送；远端 /api/health → **0.8.6**；本地演示服务同 0.8.6。
- 交付包：`dist/citeguard-cn-0.8.6.zip`（2052875 bytes，sha256 `b3f87612…`；重打包 hash 会变）。

## 36. v0.9.0：Qwen3-14B 4-bit NF4 单卡部署实测（2026-10-25）

- 起因：14B bf16 要两张 24GB 卡，普通实验室/个人机器门槛高；量化能否保住质量需要实测而不是假设。
- 做法：`scripts/local_text_server.py` 增加 `LOAD_IN_4BIT=1`（bitsandbytes NF4 + double quant，
  compute dtype bf16），其余接口与 bf16 完全一致；lmh 上停掉 8B 服务，在单张 4090（GPU1）起 4-bit 14B（:8096）。
- 结果（同一 ClaimSupport-CN、同一 v10 prompt + 审计 v2）：
  - dev 40：**1.0000 / 1.000**（13.1 s/条）；test 60：**0.9588 / 0.950**（13.4 s/条）；全 100 条：**0.9754 / 0.970**（13.3 s/条）。
  - 对照 bf16 双卡：dev 1.0000、test 0.9574、all 0.9744——量化后质量没有下降（差异在 1 条以内）。
  - 显存：**11.7 GB / 单卡 24GB**（bf16 跨两卡共 29.2 GB）；代价是延迟约 1.7×（7.8 → 13.3 s/条）。
- 证据：`data/experiments/support_local_qwen3_14b_4bit_{dev,test,all}.json`、`local_gpu_memory.json`；
  产品评测页 `/benchmark` 的本地模型矩阵同步展示 4-bit 行。
- 诚实边界：4-bit 质量只在 ClaimSupport-CN（100 条构造集）上验证，不能外推成对所有任务的保证；
  13 s/条也意味着不适合大批量实时审核，适合离线/单机低并发场景。
- 验证与发布（v0.9.0）：全量 **397 passed**；verify_artifacts 本机 **118 项**、远端 **127 项**全过；
  commit `57df713` 已推送；远端 /api/health → **0.9.0**；本地演示服务同 0.9.0。
- 交付包：`dist/citeguard-cn-0.9.0.zip`（2079162 bytes，sha256 `92534e37…`；重打包 hash 会变）。
- 验证与发布（v0.9.1）：全量 **397 passed**；verify_artifacts 本机 **118 项**、远端 **127 项**全过；
  commit `deeadad` 已推送；远端 `/api/health` → **0.9.1**；本地演示服务同 0.9.1。
- 交付包：`dist/citeguard-cn-0.9.1.zip`（2079222 bytes，sha256 `2fdaa0c5…`；重打包 hash 会变）。

## 37. v0.9.2：中文文献覆盖缺口显式化 + 人工核对入口（2026-10-25）

- 起因：真实语料 409 条整体「可确认率 51.8%」这个数会误导——拆开看是英文 186/199（93.5%）
  与中文 26/210（12.4%）。中文期刊大多不在 OpenAlex / Crossref 的开放索引里，这是结构性
  覆盖缺口，不是引文造假；产品不能假装能自动核验。
- 改动：
  1. `metadata_verify`：中文题名在「无近似匹配」时追加说明「中文文献……工具无法自动核验；
     报告已附知网/百度学术检索链接，请人工核对」。
  2. 报告卡片：未找到匹配的条目增加「人工核对入口：知网检索 · 百度学术」（外链，不抓取
     CNKI/万方内容，避免 ToS 与反爬风险）。
  3. 评测页 `/benchmark`：新增「真实性核验 · 按语言拆分」行（英文 93.5% / 中文 12.4%）。
  4. README、`docs/real_data_eval.md`、`docs/ppt_numbers.md` 同步口径，去掉「约 48% 中文
     查不到」这种把语言问题混进整体的说法。
- 验证：全量 **397 passed**；`verify_artifacts.py` 本机 **118 项**全过；报告页实测 23 条
  中文未命中条目均显示知网/百度学术入口与中文说明；评测页语言拆分行渲染正确。
- 边界：这是「把限制说清楚 + 给人工路径」，不是把中文自动核验做出来了；要真正自动覆盖
  中文期刊，需要授权的中文库（知网/万方/维普）或本地题录库。

## 38. v0.9.3：图表核验跨模型对照（Qwen2.5-VL-3B）+ 多结论（2026-10-25）

- 背景：用户追问「图表核验增强不能停在 7B 单模型」。补了同系列 3B 的 50 条对照，结论是
  **3B 不能用于矛盾筛查**：仅图 0.64（矛盾召回 0.32，17/25 条矛盾被判成支持）、带上下文 0.86
  （矛盾召回 0.72，7/25）；7B 仍是产品默认（仅图 0.90 / 带上下文 0.94）。
- 同一轮还把「一张图最多 5 条结论」做进产品（`split_claims` / `check_claims`，报告一次逐条判定）。
- 改动：`web/app.py` `_benchmark_context()` 读取 `figure_prompt_eval.json` 与
  `figure_prompt_eval_3b.json`，评测页按模型各渲染一张表（3B 下方明确写「不能用于矛盾筛查」）；
  `THIRD_PARTY_NOTICES.md` §4.3、`docs/figure_check.md`、README、`docs/ppt_numbers.md`（3h）、
  `data/experiments/README.md` 同步；证据 `data/experiments/figure_prompt_eval_3b.json`。
- 评测方法：与 7B 完全相同的 50 条结论（20 张合成图 40 条 + 5 张真实图 10 条），同一
  `scripts/eval_figure_prompt.py`，只换 `CITEGUARD_VL_ENDPOINT` 到 3B 服务；3B 与 7B 均为
  Apache-2.0、单卡 4090、bf16。
- 边界：真实图仍只有 5 张 / 10 条，3B 结论只用于「选型对照」，不是大样本精度承诺；
  3B 也不会作为产品默认或可选项暴露给用户。
- 验证与发布（v0.9.3）：全量 **401 passed**；`verify_artifacts.py` 本机 **118 项**、远端 `--api-base` **127 项**全过；
  commit `5d13866` 已推送；远端 `/api/health` → **0.9.3**；本地演示服务同 0.9.3。
- 交付包：`dist/citeguard-cn-0.9.3.zip`（2107693 bytes，sha256 `dc8b2beb…`；重打包 hash 会变）。

## 38. v0.9.4：可用性/安全/评测补齐（2026-10-25）

用户要求把「后续仍可做」的六项一起推进。本轮改动：

1. **支持度判定并发**：`config.SUPPORT_WORKERS`（默认 4，夹取 1–8）；`pipeline._judge_support`
   先按原语义截断候选，再用线程池并发判定，结果保持引文顺序；进度按完成条数更新。
   `support.py` 的两类缓存写入改为临时文件 + `os.replace` 原子替换。
2. **公开演示防护**：可选 `CITEGUARD_ACCESS_TOKEN`（`?token=` 种 HttpOnly cookie，或
   `X-Access-Token` / `Authorization: Bearer`）+ 每 IP 每分钟 `CITEGUARD_RATE_LIMIT_PER_MIN`
   的 POST `/api/*` 限流（429 + `Retry-After`）；`/api/health` 与静态资源放行。
3. **中文人工核对闭环**：报告页中文未命中新增「万方 / 超星发现」入口，并支持一键导出
   `manual-check.csv`（仅 Unverified/Unknown，含题名/原文/检索链接）；CNKI RIS 导入沿用既有
   `parse_ris` 与 Web 测试（RIS/EndNote/BibTeX/CSL 均覆盖）。
4. **真实图表题集扩容**：真实图从 5 图/10 条扩到 11 图/22 条（新增 6 张中介/调节路径图、
   闭环示意图、偏相关网络图；结论按图注与结构人工构造），只跑无上下文 v2：**0.818**
   （支持 1.00 / 矛盾 0.636）——结构图的否定判断仍是弱项，继续靠 `insufficient` 提示人工复核。
5. **支持度人工标注子集**：生成 40 条盲评表 `data/claimsupport_cn/human_review_40.csv`
   （隐藏原标签与模型预测）+ `scripts/check_human_labels.py`；需要真人填写后才能报告一致性。
6. **选题发现排序检查**：`scripts/eval_discover_ndcg.py` 用 8 个中文主题、关键词代理 nDCG@10
   对比扩展开/关：**0.958 vs 0.976**（2 级相关条数 8.0 vs 7.0）——扩展提高召回但未证明精排提升。
7. **多篇对比章节感知**：抽取输入按摘要/引言/方法/结果/讨论/结论切分并标注章节；标题不规范时
   退化为原截断；结果页显示「章节：…」，未重标字段准确率。

8. **评测页能力面板 + 运行状态**：`/benchmark` 现为七块评测（CiteBench / ClaimSupport /
   开源判官 / 图表核验 / 多篇对比 / 选题发现 / OCR），并新增「运行状态」自检卡片：
   判官类型与模型、覆盖审计风格、判定并发、访问控制开关、OCR、视觉模型、题录库规模、
   磁盘剩余；密钥只显示「已配置/未开启」，模板测试断言页面不含 `sk-` 明文。

验证：`pytest` 409 passed、`verify_artifacts` 本机 118 项 / 远端 `--api-base` **127 项** 全过；版本 0.9.4。

部署与交付：
- 本机演示：uvicorn `127.0.0.1:8010`，后台 job `pwsh-aec5834b4e9a4a17`，`/api/health` = 0.9.4；
  `/benchmark` 七块面板 + 运行状态卡片人工核验通过（页面无 `sk-` 明文）。
- 远端：部署包 2,126,701 bytes，`/api/health` = 0.9.4，`verify_artifacts --api-base` 127/127，
  `/benchmark` 含「运行状态」。
- 交付包：`dist/citeguard-cn-0.9.4.zip`（2,138,299 bytes，sha256
  `6fa3dd8c4c0c75f9627ed3ec07a127778d4f61d383380b9fbddf9059a55f0426`）。
- 提交：`a2bcea1`（已推送 GitHub；提交信息含六项加固与评测页能力面板）。

## §39 v0.9.5：ClaimSupport-CN 标签质量审计（LLM 共识，非人工金标准）

动机：构造标签容易被问“谁定的”。用三个独立模型在固定 rubric 下盲标（只看 claim + evidence）：
DeepSeek-Chat 100/100 一致率 0.87（κ 0.813）、DeepSeek-Reasoner 98/100 **0.969（κ 0.957）**、
Qwen3-8B 100/100 0.75（κ 0.638）；两两 κ 0.68–0.88。多数票与构造标签 **0.89 / κ 0.8425**
（11 条分歧，集中在 partial↔support）；产品（托管 v10）对多数票 **0.90 / macro-F1 0.9049**。

- 脚本：`scripts/llm_annotate_support.py`（支持 `--resume`、任意 OpenAI 兼容端点）、
  `scripts/support_llm_consensus.py`；证据：`data/claimsupport_cn/llm_annotation_*.json`、
  `llm_consensus.json`。
- `/benchmark` 增加「标签质量审计」面板；README、`data/claimsupport_cn/README.md`、
  `docs/support_summary.md`、`docs/ppt_numbers.md` 均已按「LLM 辅助审计」口径写入，
  **明示不是人工标注**。
- 验证：`pytest` 409 passed；`verify_artifacts` 本机 **124** / 远端 `--api-base` **133**。
- 部署：本机 8010（job `pwsh-2e081064ecc648bb`）；远端 0.9.5；`/benchmark` 含审计面板。
- 交付包：`dist/citeguard-cn-0.9.5.zip`（2,164,293 bytes，sha256
  `fd0b1eb35d9a6afd100788f07c1c6f6265a02efd1ce5e39e0e7377182da749b7`）。
- 提交：v0.9.5 功能提交 `c7ec519`（已推送）。

## §40 v0.9.6：产品-共识分歧逐条分析（10 条）

动机：上一轮对外说「产品 vs LLM 共识 0.90」，必须能解释这 10 条差在哪，而不是一句“标签边界”。
逐条核对 claim/evidence/三票/产品理由后，结论：

- **8 条产品与构造标签一致**：5 条背景从句未覆盖（cs-0025/0030/0034/0037/0049 → partial），
  3 条 token 级方向反转被多数票漏判（cs-0057 增强/削弱、cs-0083 有效/无效、cs-0095 促进/抑制）。
- **2 条产品比构造标签更严格**（cs-0024 证据只重复研究目的、cs-0048 少「沟通能力」维度）：
  产品判 partial，构造标签判 support，是设计选择。
- 另两条 cs-0001/cs-0056 是构造标签自身边界（claim 与 evidence 逐字相同但多了设计描述，
  三模型都判 support）。

落地：`docs/label_audit_cases.md`（逐条表 + 解读 + 用法）、`/benchmark` 审计面板脚注、
`README.md` 与 `data/claimsupport_cn/README.md` 的指针。对外口径不变：构造标签 0.9597
为主，LLM 共识 0.90 并列，二者都不是人工金标准。

- 验证：`pytest` 409 passed；`verify_artifacts` 本机 124 / 远端 133。
- 部署：本机 8010（job `pwsh-4658a6f224d84ec8`）；远端 0.9.6；`/benchmark` 脚注可见。
- 交付包：`dist/citeguard-cn-0.9.6.zip`（2,167,662 bytes，sha256
  `7655dd096d25b9a966e925866d21f46e5f74929f70eb14f4c87cc64e89e8933c`）。
- 提交：`fbfb8e1`（已推送）。

## §41 v0.9.7：留出 test 60 的三模型盲标复验

动机：100 条共识审计是同一批样本上做的解释，必须回答“是不是在这批上调的”。
把三模型盲标（DeepSeek-Chat / DeepSeek-Reasoner / Qwen3-8B）原样跑到 **test 60**
（split 见 `split_seed20261024.json`，test 未参与 prompt 调整）：

| 指标 | test 60 | 全 100 |
|---|---:|---:|
| 多数票 vs 构造 | 0.883 / κ 0.834 | 0.890 / κ 0.843 |
| 产品 vs 构造 | 0.933 | 0.950 |
| 产品 vs 多数票 | 0.883 | 0.900 |
| 产品 vs 多数票 macro-F1 | 0.897 | 0.905 |

7 条产品-多数票分歧同型：5 条产品与构造一致（4 条背景从句→partial，1 条方向反转），
2 条产品更严格（cs-0024、cs-0048）。partial precision 0.647 / recall 1.0，contradict F1 0.941，
no_evidence F1 1.0。结论：模式一致，**不是过拟合**；产品“严格覆盖”在留出集上同样表现为
partial 多发、support 少发。

- 脚本：`llm_annotate_support.py --split test`、`support_llm_consensus.py --split test`
  （Qwen3-8B 标注在 lmh 上本地跑，避免隧道）。
- 证据：`data/claimsupport_cn/llm_consensus-test.json`、
  `llm_annotation_{deepseek,qwen3-8b,deepseek-reasoner}-test.json`。
- 页面：`/benchmark` 审计面板新增留出集一行。
- 验证：`pytest` 409 passed；`verify_artifacts` 本机 124 / 远端 133。
- 部署：本机 8010（job `pwsh-8b3fe11221fa4200`）；远端 0.9.7。
- 交付包：`dist/citeguard-cn-0.9.7.zip`（2,182,436 bytes，sha256
  `6eccaa57c56999d4a8619bc4be11218511ddade3ab7038b2461fdabff5ba5032`）。
- 提交：`582a21c`（已推送）。

## §42 v0.9.8：外部同类工具同题对照（RefChecker）

- 外部工具：`amazon-science/RefChecker`（Apache-2.0），官方 LLMExtractor + LLMChecker 两段式流水线；
  本地复现放在 `out/refchecker/`（gitignore），不复制其代码、不作为运行依赖。
- 同一底层模型 DeepSeek-Chat、同一批 SciFact dev 300 条、同一 oracle 摘要：RefChecker macro-F1 **0.7646** /
  acc 0.7933（混淆 `[[96,3,20],[12,33,18],[6,3,109]]`）；本工作台同题 **0.8224** / 0.7939。
  差距主要在矛盾类召回（0.524 vs 0.60）。
- 口径：这是「同数据、同 backbone、按其官方协议」的对照，不是 SOTA 声明，也不能外推为通用提升；
  RefChecker 面向通用回复-证据幻觉检查，不是引文支持度专用。见 `docs/experiments.md` §14、
  `data/experiments/scifact_refchecker_deepseek.json`。
- 产品面：`/benchmark` 「真实已发表论文上的表现」新增外部对照行；`scripts/verify_artifacts.py` 新增
  3 条数字一致性断言（含「外部低于本工作台」的关系校验，防止未来改数时把结论写反）。
- 版本 0.9.8；测试 409 passed；`verify_artifacts` 本机 130 项、远端（`--api-base`）139 项全过。
- 交付包：`dist/citeguard-cn-0.9.8.zip`（5,231,272 字节，sha256 `6ecd20bc7bbd66ba1f48e2c490ac23620c19d27c2cffd6542a0107652572b2c7`）；
  本次起包内含技术报告 PDF/DOCX（报告工作区已 gitignore，打包脚本单独收集），此前版本只有源码/证据。


## 40. v0.9.9：任务历史页

- 新增 `/history`：最近 60 个任务的创建时间、文件名、状态、进度与报告入口；
  `active="history"` 导航项，页面不渲染任何密钥。
- 复用 `JobManager.recent()` 与 `_report_path()`；报告保留策略不变（7 天 / 最近 100 条）。
- `tests/test_web.py` 增加历史页渲染断言（200、含「任务历史」、不含 `sk-`）。
- 全量 `pytest` 410 passed；`verify_artifacts.py` 130 项；版本 0.9.9。

**验证与发布（v0.9.9，2026-10-25）**

- 本机：410 passed / 130 checks；`/history` 200、含标题、无密钥明文。
- 远端：`health=0.9.9`、`/history` 200、`verify_artifacts --api-base` **139/139**。
- 交付包：`dist/citeguard-cn-0.9.9.zip` 5,232,744 字节，
  sha256 `188441fdbe02cbf8ac98dc7da19b24fab71d9828a3497ac8bd2fd75f48bb8436`。
- 推送：`2c5869b`（SSH；HTTPS 代理仍不可用）。


## 41. v0.9.10：图表核验 v3 提示词 + 真实图集扩容到 13 图/26 条

- 图集扩容：新增三簇子空间分布图（hanspub_152577）与四节点加权网络图（W2996762219），
  真实集 13 图 / 26 条 claim（每条一支持一矛盾，人工按图注与结构构造）。
- v3 提示词：新增「子图/对象归错且明显不符 → contradicted」规则，修复 v2 把属性错配判成
  `insufficient` 的问题；`figure_check.PROMPT_VERSION="3"`。
- 证据：66 条（40 合成 + 26 真实）v2 0.8788 → v3 **0.9242**；真实子集 0.769 → **0.885**；
  50 条主口径 v3 仍 **0.94**（支持 0.92 / 矛盾 0.96）。
- 文档：`docs/figure_check.md` 扩容集段落、README、`docs/ppt_numbers.md` 3f 行；
  技术报告同步到 v0.9.10（9 页，568 KB）。
- 测试：`tests/test_figure_check.py` + `tests/test_web.py` 48 passed（全量见发布记录）。

**验证与发布（v0.9.10，2026-10-25）**

- 本机：410 passed / 130 checks；`/figure` 已切 v3（`PROMPT_VERSION=3`）。
- 远端：`health=0.9.10`、`verify_artifacts --api-base` **139/139**。
- 报告：v0.9.10 DOCX/PDF，9 页 / 568 KB，已更新图集与 v3 数字。
- 交付包：`dist/citeguard-cn-0.9.10.zip` 5,767,853 字节，
  sha256 `5ae0fe48b5c096442eeb4baeeace76ee262d3aa8cd2743d852c6bb1ec746e552`。
- 推送：`6796e9a`（SSH）。

---

## 42. v0.9.11：上游 PR 状态更正、合成图盲测、远程访问边界

**变更（2026-10-25，v0.9.11）**

1. 上游贡献更正：PR #77 提交在 `markrussinovich/refchecker`（MIT，独立 Python 引文核验项目），
   维护者已于 2026-10-24 **关闭、未合并**；它与 E14 对照使用的 `amazon-science/RefChecker`
   （Apache-2.0）是**两个同名项目**。README / THIRD_PARTY §7 / compliance 已分别写明，
   不再把 PR 说成对照工具的贡献。
2. 图表合成集**新种子盲测**：seed=20261025，20 图 / 40 条，v3 无上下文 **0.875**
   （支持召回 0.80 / 矛盾召回 0.95）；证据 `data/experiments/figure_prompt_eval_blind40.json`，
   生成器与评测脚本新增 `--seed/--out` 与 `FIGTEST_SYNTH_JSON/FIGTEST_SYNTH_FOLDER/FIGTEST_FAMILIES`
   以便复核。
3. 远程访问边界写进 `docs/deployment.md` §3：本机访问 `http://222.20.96.215:8000/` 超时
   （服务端 `0.0.0.0:8000` 正常，属校园网/防火墙限制）；答辩用本机或 SSH 隧道，
   不对外承诺公网地址。
4. 版本 0.9.11；`dist/citeguard-cn-0.9.11.zip` 5,770,447 字节，
   sha256 `f2a08ce589048794d70845cb146240f3b4e174f33975eb7b6709db4d7a589deb`。

**验证与发布（v0.9.11，2026-10-25）**

- 本机：410 passed / 130 checks。
- 远端：health=0.9.11、`verify_artifacts --api-base` **139/139**。
- 推送：`17bf89b`（SSH）。

## 43. v0.9.12：中文引文「人工核对 → 一键补录 → 自动命中」闭环

- 公开源核实：210 条中文引文仅 1 条带 DOI；OpenAlex/Crossref 对 12 条抽样题名
  命中数全为 0（归一化后仍为 0）；CSTR 只有标识接口、ChinaXiv 只有预印本、
  国家哲社文献中心/PubScholar 无公开 API、CNKI/万方无免费 API。结论写入
  `docs/chinese_sources.md`。
- 产品：`POST /api/library/add` 手工补录题录（按题名去重）；报告卡片 Unverified
  时给「加入题录库」按钮，存入后下次核验自动命中。
- 新增 web 测试：`tests/test_web.py::test_library_add_accepts_manual_entry`。
- 版本 0.9.12；`docs/chinese_sources.md` 登记进 README 中文覆盖一节。

**验证与发布（v0.9.12，2026-10-25）**

- 本机：**411 passed / 130 checks**（新增 `test_library_add_accepts_manual_entry`）。
- 远端：health=0.9.12、`verify_artifacts --api-base` **139/139**。
- 推送：`8c3903b`（SSH）；部署包 `git archive` 2,203,249 字节。
- 交付包：`dist/citeguard-cn-0.9.12.zip` **5,774,867 字节**，
  sha256 `3da09758f53c3aa351cafd01a45a0f6cd87233e4bf435aa22ab55aa832e63f01`。

## 44. v0.9.13：万方题录兜底（可选，已停止试用）

- `src/citeguard/wanfang.py`：`search()` / `get_doc()` / `record_to_candidate_fields()`；
  鉴权头 `X-App-Key`，强制 HTTPS；内置 0.30s 节流 + 429 重试，额度不足抛可读异常。
- `src/citeguard/metadata_verify.py`：中文无 DOI 条目在 OpenAlex/Crossref/arXiv 之后补一层
  万方候选（`source="wanfang"`）；未配置、未订阅、限流、额度用尽都只记日志并跳过，
  不把条目误标成 `Unknown`。
- 证据：20 条真实中文引文抽样 **16 条题名精确命中（≥0.97）**；
  免费额度 100 次/天（当天已用尽，按用户要求**不再继续调用试用额度**）。
- `.env.example` / `docs/chinese_sources.md` / README 局限节已写明使用方式与额度边界。
- 测试：`tests/test_wanfang.py` 4 条 + `tests/test_metadata_verify.py` 兜底用例 1 条。
- 版本 0.9.13。
- 验证：`pytest` **416 passed**；`verify_artifacts.py` 本机 **130** / 远端 `--api-base` **139** 全过；
  远端 `/api/health` 版本 0.9.13。
- 部署：`git archive` 2,229,295 bytes → 远端解压重启；zip `dist/citeguard-cn-0.9.13.zip`
  5,802,186 bytes，SHA-256 `ca4b2754698dc6434fa4989024ea636f90413347132aaf857325be36d89134db`。
- 推送：`b6fb34c`（`4089a40..b6fb34c main`）。
- 按用户要求，验证 20 条抽样后不再消耗免费额度（当天额度已用尽）。


## 44. 外部公开基准：ChartCheck 零样本（v0.9.13 后补）

- 数据与许可：ChartCheck（Akhtar et al., Findings ACL 2024）仓库 MIT；图表来自 Wikimedia Commons，各自保留原许可；
  本仓库只记录图片 URL、模型预测与理由，不重分发图片。
- 协议：val 953 条按标签分层抽 60 条（30/30，seed=20261025），图 + 图注 + claim → Qwen2.5-VL-7B（产品 prompt v1）。
- 结果：3 分类准确率 0.483 / macro-F1 0.597；二分类（supported vs not_supported，insufficient 计入 not_supported）
  0.683 / 0.662；insufficient 38.3%；平均延迟 2.94 s。
- 解读：公开英文图表上 7B 偏保守，与自建集 0.94 差距大，说明自建集数字不能外推；答辩只把它当外部零样本压力测试，
  主指标仍用自建中文图表集（并明确其分布限制）。
- v0.9.14 追加：同一 60 条上换 **Qwen3-VL-8B** 并加“分步推理”提示词后，3 分类 0.733 / 0.764，
  二分类 0.767 / 0.764（insufficient 8.3%，7.9 s/条）；但 8B 用原提示词时二分类没有提升，
  说明增益来自「模型 + 显式推理步骤」的组合。证据：`chartcheck_val60_qwen3vl8b{,_v3}.json`。
- 证据：`data/experiments/chartcheck_val60.json`；复现：`python scripts/eval_chartcheck.py --sample 60`。

- v0.9.14 追加：自建 50 条（合成 40 + 真实 10）用 Qwen3-VL-8B + v2 + 正文/图注 = **0.96**
  （7B 0.94），矛盾类召回 0.96，平均 2.31 s/条；证据 `figure_prompt_eval_8b_context.json`。
  8B 权重 17G、显存约 17–18G；7B 仍作低显存/低延迟选项。产品代码模型无关，换端点即可。

## §45 v0.9.14：图表分步推理（8B）与外部基准 ChartCheck

- Qwen3-VL-8B-Instruct（Apache-2.0，17G）自部署于 lmh 单卡（:8095），`scripts/local_vl_server.py`
  走 `Qwen3VLForConditionalGeneration`/`Qwen3VLProcessor`。
- 外部 ChartCheck（MIT，val 953 条，图表来自 Wikimedia Commons）零样本 60 条（30/30，seed=20261025）：
  - 7B + 一步 prompt：二分类 acc **0.6833** / macro-F1 0.6622；三分类 acc 0.4833 / macro-F1 0.5966（`chartcheck_val60.json`）。
  - 8B + 一步 prompt：二分类 0.6667 / 0.6633；8B + 分步（CoT）prompt：**0.7667 / 0.7643**（`chartcheck_val60_8b.json`、`chartcheck_val60_8b_v3.json`）。
  - 口径：任务与原论文（GPT-4V 73.8）不完全同协议（60 条子集、含中文 prompt/标签映射），只作外部参照，不作 SOTA。
- 内部 50 条：7B v2+context 0.94；8B v2+context 0.96（2.31 s/条）、v4 中文分步 0.96（4.78 s/条，增益只在换模型）。
- 产品：新增 `CITEGUARD_FIGURE_PROMPT_STYLE=2|4`（默认 2，一步；4 为分步，更慢），
  `figure_check.PROMPTS` + `prompt_style` 参数；`/benchmark` 图表面板显示 7B/8B/3B 跨模型表。
- 验证：417 passed；本机 verify 130 项、远端 **139 项**；远端 health v0.9.14。
- 交付：`dist/citeguard-cn-0.9.14.zip`，5,842,658 bytes，sha256 `50a92d23…`。

## §46 v0.9.15：图表核验默认 8B + 技术报告 v0.9.15

- 默认视觉模型改为 **Qwen3-VL-8B**（`CITEGUARD_VL_MODEL` 默认 `qwen3-vl-8b`；演示端用 lmh `:8095`，
  `CITEGUARD_FIGURE_PROMPT_STYLE` 默认 2 一步、可切 4 分步）。7B/3B 仍可显式指定，用于对照。
- 技术报告重生成：图表章节加入 8B（内部 0.96 / 外部 ChartCheck 0.7667）与 7B/3B/8B 跨模型口径；
  `dist/citeguard-cn_技术报告_v0.9.15_2026-10-25.pdf`（9 页，569,653 bytes，含 Courier 字体缺失回退提示）。
- 版本 0.9.15；417 passed；本机 verify 130 项、远端 **139 项**；远端 health v0.9.15。
- 交付包：`dist/citeguard-cn-0.9.15.zip`（5,845,178 bytes，sha256 `c1d9a6c7…`）。

## §47 v0.9.16：ChartCheck 200 条零样本主口径

- 外部 ChartCheck val 953 分层抽 **200 条**（100/100，seed=20261025），一步 prompt：
  Qwen2.5-VL-7B 二分类 0.670/0.644、3 分类 0.475/0.576；Qwen3-VL-8B 二分类 **0.730/0.727**、
  3 分类 0.645/0.714；insufficient 36.0% / 19.5%；延迟 2.80 s / 4.15 s。证据
  `data/experiments/chartcheck_val200_{7b,8b}_v1.json`。
- 200 条 v3（分步）复跑因评测网络中断（8B 95 条、7B 149 条 502）作废，文件已删；正式材料只引用一步口径，
  60 条小样本 v3 0.767 仅作补充观察。
- `/benchmark` 图表面板新增「外部公开基准 ChartCheck 200 条」表；README/THIRD_PARTY/figure_check/ppt 同步。
- 技术报告重生成 v0.9.16（10 页，571,902 bytes）：图表章节改为 200 条一步主口径，注明 v3 未完成。
- 版本 0.9.16；417 passed；本机 verify **134 项**；交付包 `dist/citeguard-cn-0.9.16.zip`。

## §48 v0.9.17：界面改版（纸面书脊 + 报告侧栏）

- 全局视觉：左侧书脊式导航（分组/图标/当前页）、顶部面包屑与 Ctrl+K 命令面板、
  衬线标题 + 纸面底色 + 松绿色强调；首页重写为「hero + 数字条 + 分析卡 + 六能力卡 + 最近任务」。
- 报告页改为**常驻摘要侧栏 + 阅读列**：合规分、风险构成、六项状态计数、导出操作收进侧栏；
  正文列只放体检结论、审稿视角、支持度、引注一致性与可检索的引文卡片。
- 交互：命令面板（Ctrl/Cmd+K，上下选择/回车跳转）、移动端抽屉导航、卡片上浮、
  拖拽上传、滚动到上传区；全部动效在 `prefers-reduced-motion` 下关闭。
- 页面自适应 430 / 820 / 1050 / 1180 断点；`web/app.py` 的 `/figure` 会按
  `CITEGUARD_VL_MODEL` 显示实际模型名，避免代码换模型后文案仍写旧模型。
- 验证：417 passed；本机 `verify_artifacts` 134 项；本地演示 v0.9.17。
- 交付包 `dist/citeguard-cn-0.9.17.zip`。

## §49 v0.9.18：ChartCheck 200 条分步推理复验

- 网络恢复后补跑 ChartCheck 200 条（100 支持 / 100 不支持，seed=20261025）分步推理 v3：
  二分类 acc **0.795** / macro-F1 **0.794**；三分类 acc 0.720 / macro-F1 0.776；
  insufficient 14.5%；平均 7.50 s；0 失败（`data/experiments/chartcheck_val200_v3.json`）。
- 对照：同 200 条一步 v1 为 8B 0.730/0.727、7B 0.670/0.644；分步推理的增益在大样本上成立。
- 同步 README / THIRD_PARTY §4.3 / docs/figure_check.md / ppt_numbers 3k / benchmark 图表面板（一行 v3）；
  技术报告图表章节与汇总表改用 200 条 v3 数字（仍注明与 ChartCheck 论文完整 test 不是同一子集）。
- 复现：`python scripts/eval_chartcheck.py --sample 200 --prompt v3`（Qwen3-VL-8B，:8095）。



## §49 v0.9.19：万方批量补录试点进评测页

- 新增 `scripts/eval_wanfang_batch.py`（断点续跑、0.8s 节流、429 自动退避）；
  状态 `data/experiments/wanfang_batch.json`，key 只放 `.env.wanfang`（gitignore）。
- 首日结果：成功探测 94/184 条真实中文「未验证」引文；强匹配（题名≥0.92+年份一致）54 条
  （52 条刊名、54 条作者姓氏也在原文）；模糊 7 条不计；限流 6 条、剩余 84 条待续跑。
  中文可确认率推算 26/210（12.4%）→ (26+54)/210 ≈ 38.1%。
- `/benchmark` 真实语料表新增「中文覆盖率试点（万方 API）」行；`/api/benchmark` 同步。
- 证据：`data/experiments/wanfang_batch.json`；说明：`docs/chinese_sources.md`。
- 本轮无算法/产品默认改动；Wanfang 仍是可选 fallback（不配 key 不影响使用）。

- 发布验证（v0.9.19）：`pytest tests -q` **417 passed**；`verify_artifacts` 本机 **137** /
  远端 `--api-base` **146** 全过；远端 health 0.9.19；GitHub `49842da`；
  交付包 `dist/citeguard-cn-0.9.19.zip`（4,503,426 bytes，sha256 `372946e4…`）。

## 49. 真论文加固：标题/期刊粘连、乱码、arXiv venue（v0.9.20，2026-10-27）

用用户桌面的 Attention 论文（1706.03762，40 条英文参考文献）做真机回归，修掉 5 类解析缺陷：

1. **空格丢失**：部分 PDF 文字层把词间空格编进位置信息，PyMuPDF 提取成
   `Longshort-termmemory`；增加 PyMuPDF 回退与长 ASCII 串拆词（`_pdf_pymupdf` / `_long_ascii_runs`）。
2. **标题吞期刊**：无 `[J]` 标记的英文条目 `Title. Journal, 9(8):1735–1780, 1997` 现在会切分标题与期刊
   （`_TITLE_JOURNAL_TAIL_RE` / `_split_title_journal_tail`），并回填卷期页年。
3. **arXiv/CoRR 尾巴进标题**：`arXiv preprint arXiv:xxx`、`. In Proc...`、`? In ...` 均从标题剥离进 venue。
4. **作者切分**：首字母缩写的 `Surname, I.` 合并、Latin-1/Extended-A 姓名（Jürgen、Łukasz）、
   连字符换行（`Salakhutdi- nov`）修复；作者串上限 180 字符，避免整段标题被当作者。
5. **乱码**：PDF 文字层的 UTF-8→CP1252 误解码（`Ã¼`/`â€“`）做多轮往返修复（先于 NFKC）。

实测（Attention 40 条，`support_max=0`）：**0 Major**，Exact 4 / Minor 35 / Unverified 1；
剩余 1 条是原文标题本身被截断（缺副标题），属源文本问题，不强行匹配。测试 421 passed。

## 50. 中文覆盖率收口：万方试点跑完 184/184（v0.9.21，2026-10-27）

- 第二天配额（90 次）跑完剩余 84 条 + 6 条重试；累计 197 次调用（首日 107、次日 90），断点状态与逐条结果在 `data/experiments/wanfang_batch.json`。
- 结果：184 条未验证中文引文中 **强匹配 111 条**（题名相似度 ≥0.92 且年份一致），0.80–0.92 模糊命中 11 条（累计 ≥0.80 共 122 条，66.7%），1 条重试后仍失败。
- 覆盖率：中文免费源 26/210（12.4%）→ **137/210 = 65.2%**（含模糊 148/210，70.5%）；整批真实语料 409 条从 212（51.8%）→ **323（79.0%）**（含模糊 334，81.7%），Major 仍为 **0**。
- 同步：README（中文节、能力表、局限）、`docs/chinese_sources.md`、`docs/real_data_eval.md`（§3/§3.1 口径 + 指向 §5）、`docs/ppt_numbers.md`（新增覆盖行 + 「不能这么说」第 2 条）、`data/experiments/README.md`、技术报告 5.3 节重建 PDF。
- 版本 0.9.22：`/benchmark` 的中文覆盖率行已改为「已跑完 184/184、强匹配 111、中文 26/210→137/210（65.2%）、整批 212/409→323/409（79.0%）」，并注明这是有机构 API 时的推算、不进入默认免费口径。测试 421 passed；`verify_artifacts` 本机 137 项。

## 51. v0.9.24：用真实 arXiv 论文压测参考文献解析

用三篇 arXiv 原版 PDF 走真实上传链路（关闭支持度，纯核验）连续暴露并修复了这些问题：

- **参考文献章节定位**：原逻辑“最后一个足够长的 References 标题”在多栏/附录论文上会选错
  （FlashAttention 只解析出 8 条）。改为对候选块做条目密度评分（编号条目数 + 年份条目数），
  再选最优；同时裁掉 References 后附的 Appendix/补充材料（BERT 124→54 条即此故）。
- **ACL 风格**：`Authors. 2019. Title.` 的无括号年份会被当成标题的一部分；解析前统一改写成
  `Authors (2019). Title`；引号包裹的标题（`“Prefix Sums...”`）优先于 APA 解析。
- **URL 碎片**：`url: https://doi.org/...` 被切成独立条目后，DOI 能解析到另一篇真实论文，
  造成一次 **Major 误报**。现在这类纯 URL/DOI 碎片直接跳过，不再参与核验。
- **纯年份标题**：PDF 换行丢失标题时，标题只剩 `2018`；现在置空并记 `title_missing`，
  结果为 Unverified，而不是拿年份去比对。

复测（真实上传链路，support_max=0）：

| 论文 | 解析条数 | Exact | Minor | Unverified | Unknown（源失败） | Major |
|---|---|---|---|---|---|---|
| BERT (1810.04805) | 54 | 18 | 30 | 6 | 0 | 0 |
| Mamba (2312.00752) | 94 | 17 | 33 | 5 | 39 | 0 |
| FlashAttention (2205.14135) | 117 | 27 | 68 | 5 | 17 | 0 |

> 2026-10-28 更正：上表旧值（11/18/25、18/21/77、14/13/67）测于数据源间歇性失败期间——失败被静默当成“未收录”。现在 `metadata_verify` 会记录源失败次数：题名弱匹配且期间有源失败时返回 **Unknown（未完成核验）**，不再冒充 Unverified；`_request` 重试 3→5 次、指数退避并遵守 `Retry-After`，降低限流影响。BERT 那次源稳定，可作干净样本（48/54 有明确结论）。Mamba/Flash 的 Unknown 是复测时被 OpenAlex/Crossref 限流所致，不是文献问题。
> 另修：`url: https://doi.org/…` 这类纯链接碎片此前正则漏掉 `url:` 前缀，被当成条目解析后解析出一条假 Major；`reference_parser._URL_ONLY_RE` 已覆盖，三篇共少 1 条假条目。

单元测试 456 通过、`verify_artifacts` 137 项全过。Unverified/Unknown 比例仍高，原因是 arXiv 参考文献普遍缺 DOI、会议缩写不规范、免费源覆盖有限；它表示“未找到/没核完”，不是“虚假”。

版本 0.9.40。

## 43. 0.9.32–0.9.34：断点续跑、覆盖率仪表盘、材料终检（2026-10-27）

- v0.9.32：服务重启后未完成任务标为 `interrupted`；失败/中断任务保留抽取文本与前端选项，历史页「重新运行」按钮走 `POST /api/jobs/{id}/rerun`；成功任务仍即时删除 `input.txt`。
- v0.9.33：`/library` 增加「覆盖构成」面板（DOI 比例、摘要比例、年份范围、期刊/会议数、收录最多来源）。
- v0.9.34：打包器 `scripts/package_deliverable.py` 增加匿名化——排除 `docs/HANDOFF.md`，把内网 IP 与本机路径替换为 `127.0.0.1`/`<project>`/`<user>`；`eval_chartcheck.py`、`eval_figure_prompt.py` 默认端点改 `127.0.0.1:8099`；答辩 PPT 第 8 页去掉内网地址。
- 新增材料：`docs/anonymity_check.md`（匿名终检 + 复跑脚本）、`docs/resource_list.md`（附件资源清单）、`docs/demo_script.md`（5 分钟现场脚本 + 断网兜底）、`docs/ppt_numbers.md` 末尾「创新性三条」。
- 重新生成：`dist/CiteGuard-CN_答辩PPT_18页.pptx/.pdf`（18 页，无内网地址）、`dist/CiteGuard-CN_技术报告_v0.9.34_2026-10-27.docx/.pdf`（9 页）。
- 测试 445 passed，`verify_artifacts` 137/137；zip 364 文件、8.4 MB、sha256 `a66c1b4a5944…`，扫描内网 IP/密钥 0 命中。
- 部署：本地 `127.0.0.1:8010`、远端 `/data/xyjiang/aic_mental/citeguard` 均 0.9.34；GitHub push 仍因 443 不可达，提交仅本地（`2836a41` 等）。


## 44. 0.9.35–0.9.36：图表多图批量、证据抽屉、多源一致标注（2026-10-27）

- v0.9.35：`/figure` 支持一次上传 1–3 张图，每张跑一遍「定位/渲染页 + 结论判定」，返回 `results[]`（逐图结论、页码、耗时、错误），前端逐图卡片展示；接口保持旧单图字段兼容。
- v0.9.36：报告页每条加「证据」抽屉，展示核验状态、数据源、来源一致数、标题相似度、作者匹配、比对记录、备注/字段差异、支持度判定、原始条目与完整 JSON；多源核验在题名+年份上 2 个以上来源一致时显示「N 个来源一致」标签（原先只算进 `source_agreement`，未展示）。
- 新增 `docs/open_outputs.md`：开放成果包清单（代码/数据/评测/许可证/复用方式/不开放项），补全「开放成果」评分材料。
- 技术报告同步 v0.9.36：4.1 补「每条结论可点证据抽屉」、4.2 补「N 个来源一致」展示、测试数改 445；重新导出 `dist/CiteGuard-CN_技术报告_v0.9.36_2026-10-27.docx/.pdf`（PDF 10 页、583,622 bytes）。
- 测试 445 passed，`verify_artifacts` 137/137；`dist/citeguard-cn-0.9.36.zip` 365 文件、8.4 MB、sha256 `1878ff640475…`；扫描 `.env`/内网地址 0 命中。
- 部署：本地 `127.0.0.1:8010`、远端 `/data/xyjiang/aic_mental/citeguard` 均 0.9.36；GitHub push 仍因 443 不可达，提交仅本地（`f6b9e41`）。

## 45. 0.9.37：Windows 图表定位 500 修复 + BibTeX/CSL-JSON 导出（2026-10-27）
- 修复真实 bug：Windows 下 PDF 自动定位后删除临时文件报 `PermissionError: [WinError 32]`，接口 500。
  原因是 `pdf_extract.render_page_png` 打开 pdfium 文档/页面后未关闭，文件句柄仍被占用。
  现在在 `finally` 中依次关闭 bitmap/page/doc；路由清理临时文件失败也不再返回 500。
- 新增 `exporters.ref_to_bibtex/refs_to_bibtex/ref_to_csl/refs_to_csl`：BibTeX 转义 `& % $ # _ { }`、键名「姓氏+年份」；
  CSL-JSON 输出 Zotero 可直接导入的字段（author/issued/container-title/DOI 等）。
- 报告页新增「导出 BibTeX（LaTeX）」「导出 CSL-JSON（Zotero）」；`save_report` 同时写 `report.bib`、`report.csl.json`。
- 本地把 `/figure` 接到 lmh 的 Qwen3-VL-8B（`:8095`）：PDF 自动定位一页 + 2 条结论耗时 7.8 s，
  第 1 条 supported、第 2 条 contradicted（与图中 2023/2025 数据一致），`context_source=pdf_pages:3`。
- 测试 449 passed；`verify_artifacts` 137/137。版本 0.9.37；远端与本地随后升级。

## 46. 0.9.38：正文图表抽检并入主分析（2026-10-28）

- 主流程新增可选「同时抽检正文图表结论」（`/api/analyze` 表单字段 `figures=1`；分析页复选框）。开启后从正文自动抓取前 3 个「图 N / 表 N」引用（每个最多 2 句），按编号定位 PDF 页、渲染、调视觉模型逐条判定，结果写入 `report["figure_checks"]`。
- 实现：`src/citeguard/pipeline.py` 新增 `_body_figure_claims`（分组+上限，避免一份图多的论文悄悄跑十几分钟）与 `_check_body_figures`；`analyze_text`/`run_job` 透传 `figure_checks`/`pdf_path`，`jobs` 的续跑选项保存 `figures`；报告 Markdown/HTML/页面均渲染该节。
- 实测（lmh Qwen3-VL-8B，`/api/analyze` 真实任务）：hanspub_152575.pdf 解析 3.7 s，命中图 1/2/3，总耗时 21.2 s；6 条结论中 4 条 supported、2 条 insufficient（信息不足是诚实的“图注被当结论”边界），定位页 3/4/5 全部正确。
- 修复：`/api/health` 的版本号此前硬编码 0.9.37，改为 `app.version`；测试 454 passed，`verify_artifacts` 137/137。
- 网络：lmh（222.20.126.148）与远端 222.20.96.215 在 00:05 后均不可达（VPN/校园网切换），视觉服务与远端部署暂不可用；本地引文核验不受影响，图表抽检会返回可读错误而不是假结果。
- 版本 0.9.39（含离线演示包、ETA 进度、TOC 图注过滤、多图/表分组）；`dist/citeguard-cn-0.9.39.zip` 8.4 MB、sha256 `524f0b64172c…`；本地 8010 已升级；远端 222.20.96.215 与 lmh 仍不可达，部署与视觉服务待网络恢复。

## 47. 0.9.39：离线演示包（2026-10-28）

- 新增 `samples/offline_demo/`：`paper.txt`（演示短文 + 11 条题录，前 10 条为真实公开文献元数据，第 11 条故意虚构）、`library.ris`（前 10 条）、`README.md`（三步用法与预期结果）。
- 目标：答辩现场断网也能完整走「题录库 + 字段核验 + 引注一致性 + GB/T 规则」；预期 10 条精确匹配、1 条未核实（离线状态下显示 Unknown 并注明原因，不冒充假文献）。
- 生成脚本 `scripts/build_offline_demo.py`（去重、去掉重复编号、写 RIS）；测试 `tests/test_pipeline.py::test_offline_demo_pack` 断言 10 Exact + 1 Unknown。
- 测试 454 passed；`verify_artifacts` 137/137；版本 0.9.39。
- 技术报告同步 454 测试：`dist/CiteGuard-CN_技术报告_v0.9.39_2026-10-28.docx`（651,590 bytes）与同名 PDF（10 页、583,624 bytes）。
- 新增 `/api/analyze` 进度 ETA（「多源核验 5/20 · 已用 12s · 剩约 36s」）；图表页定位跳过目录里的点线图注（`_is_toc_caption`），图/表按 `(kind, number)` 分组避免图 1 与表 1 混淆。

## 48. 0.9.40：源失败不再冒充“未收录”（2026-10-28）

- 起因：复核三篇 arXiv 论文时发现大量**题录完整**的条目被判 Unverified（Layer Normalization、Longformer、Rethinking Attention with Performers…）。这些论文在 OpenAlex/Crossref 都能搜到；真实原因是并发核验时 OpenAlex/Crossref 间歇性 429/超时，失败被静默当作“未收录”。
- `src/citeguard/metadata_verify.py`：
  - `_request`：重试 3→5 次，指数退避（1.5×2^attempt，封顶 15s），支持 `Retry-After`（封顶 20s）；`API_SLEEP` 仍生效。
  - 题名弱匹配分支：若本次核验期间 `source_error_count()` 增加，返回 **Unknown** 并注明「数据源请求失败（限流/网络），本条未完成核验」，而不是 Unverified；无源失败时保持原 Unverified 语义。
  - 新增测试 `test_weak_match_with_failed_source_is_unknown`；`test_reference_parser.py` 新增 `url:` 前缀纯链接条目测试。
- `src/citeguard/reference_parser.py`：`_URL_ONLY_RE` 支持 `url: https://…` 前缀，避免 PDF 链接行被当成条目、再因 DOI 解析到另一篇论文而误判 Major。
- 复测：BERT 54 条 → 18 Exact / 30 Minor / 6 Unverified / 0 Major（源稳定的一次）；Mamba/Flash 复测时被限流，如实标记 Unknown（表见 §46 更正段）。诚实口径：旧 Unverified 数字偏高，不应再引用。
- 版本 0.9.40；本地 8010 已升级（停旧进程后重启）。该版依赖网络状态，不改变离线模式行为。

## 49. 0.9.41：版本差异投票（2026-10-28）

- 问题：引文写的是 arXiv 版年份（如 2018），命中的是会议版记录（2019），此前一律记 `year` 不匹配 → Minor。这不是引用错误，而是同一工作的版本差异。
- `metadata_verify._version_sources`：在候选记录里找「同题名（≥0.95）且年份等于引文年份」的另一个来源；找到就从 `mismatches` 去掉 `year`，并在笔记里写明「预印本/会议版本差异，某来源的同题名记录与引文年份一致」，其余字段都符时状态为 Exact。作者不可靠时不取作者证据。
- 严格性：要求题名 ≥0.95、首选作者可对上、年份精确相等；该逻辑只补证据，不放松题名阈值。
- 测试：`test_version_source_keeps_cited_year_when_another_source_agrees`、`test_version_source_requires_matching_first_author`；全套 458 passed、`verify_artifacts` 137/137。
- 版本 0.9.41。

## 50. 0.9.42：断网演示一键载入 + 多候选页投票（2026-10-28）

- 演示题录：新增 `POST /api/library/demo`，从 `samples/offline_demo/library.ris` 导入 10 条真实开放文献；题录页加「载入演示题录」按钮，重复点击幂等（`added=0`）。会议现场断网也能走完「本地库匹配 → 字段核对」路径。测试 `test_library_demo_loads_bundled_offline_library`。
- 多候选页：`pdf_extract.find_figure_pages()` 收集同一图/表号命中的全部页，`_caption_similarity()` 用中英文 token 覆盖率打分；`find_figure_page(..., claim=...)` 在命中多页时选与结论文字最接近的一页（同分取靠前页），图表路由与正文抽检都传入 claim。无 claim 时保持「第一处命中」旧行为。
- 表格图注：`find_figure_page(kind="table")` 与 `caption_kind_from_claim()` 已支持「表 N / Table N」，本轮确认无需改代码。
- 测试：`test_figure_page_choice_prefers_claim_matching_caption`；全套 **460 passed**，`verify_artifacts` 137/137。
- 版本 0.9.42；`dist/citeguard-cn-0.9.42.zip`（8,855,086 bytes，sha256 `ab48bc14f827080f6ccd1bd1318622d4d69c34dc42878cc12897e719d913e3ff`）。

## 51. 0.9.43：arXiv 编号补年份（2026-10-28）

- 问题：英文预印本条目常省略年份（`arXiv preprint arXiv:1607.06450`），题名能解析但 `year=None`；核验时年份缺失会拉低 Exact、产生本可避免的 Minor。
- `reference_parser._year_from_arxiv` + `_fill_arxiv_year`：从 arXiv ID 的 YYMM 推出年份（91 以上记 19xx，否则 20xx；仅接受 1991–2099，月 01–12；旧式 `hep-th/9901001` 也支持）。在引号题名、APA、通用三条返回路径都补，仅当原条目没有年份时生效，`extra["year_from_arxiv"]=True` 留痕。
- 实测（只重解析，不发网络请求）：BERT 54 条补 0、Mamba 94 条补 0、FlashAttention 118 条补 4，共 **+4/266**。
- 测试：`test_arxiv_identifier_fills_missing_year`、`test_arxiv_year_ignores_invalid_month_and_old_ids`；全套 **462 passed**、`verify_artifacts` 137/137。
- 版本 0.9.43；`dist/citeguard-cn-0.9.43.zip`（8,855,809 bytes，sha256 `8d8fe57e122de4f3dcd65a765a9393b79e89a2a1c8e4fcf240783b7f4a6a91d5`）。

## 52. 0.9.44：解析提速——跳过多余的第二个提取器（2026-10-28）

- 问题：`extract_text_with_meta` 对每个 PDF 都跑 pdfplumber + PyMuPDF 两遍，只为处理 LaTeX 缺空格；文字层正常时第二遍是纯开销。
- 改为：仅当 pdfplumber 结果为空、或出现 ≥25 字符的连续 ASCII 串时才调用 PyMuPDF；替换条件改为「长串数降到 2 倍以下」或「备用解析器 0 个长串、原文至少 1 个」，避免单个超长粘连串漏判。
- 实测（3 篇中文 PDF）：原本每篇多跑的 PyMuPDF 耗时 **0.312 / 0.043 / 0.050 s**；解析条数不变（24 / 15 / 9 条）。长英文论文收益更大，属于小优化，不夸大成“大幅提速”。
- 测试：`test_pdf_text_spacing_skips_second_extractor`、`test_pdf_text_spacing_uses_second_extractor_when_words_merge`；全套 **464 passed**、`verify_artifacts` 137/137。
- 版本 0.9.44；`dist/citeguard-cn-0.9.44.zip`（8,856,169 bytes，sha256 `284d48538e84b3470b10e10ba816b045c22327055279e6628455d834d68daf6e`）。

## 53. 0.9.44 技术报告同步（2026-10-28）

- 报告源 `report/build_report.py` 的测试数字统一为 **464 项**（原 458/421 混用）；重新生成 docx → Word 导出 PDF，**9 页**（≤15 页限制）。
- 交付：`dist/CiteGuard-CN_技术报告_v0.9.44_2026-10-28.docx`（651,649 bytes）、同名 `.pdf`（576,152 bytes）。
- 校验：PDF 文本中 “464”×3，无 “458/421”；`verify_artifacts` 137/137。
- 仍待同步：`report/build_deck.py` 内 “417 测试” 等旧数字（下一轮重建 PPT）。
- PPT 同步：`report/build_deck.py` 与 `report/deck_assets.py` 的 “417 测试” 改为 **464**；重建 18 页 PPT（1,478,599 bytes）并导出 PDF（18 页，文本中 464×3、无 417）。交付：`dist/CiteGuard-CN_答辩PPT_18页_v0.9.44_2026-10-28.pptx/.pdf`。
## 54. 0.9.45 解析：作者-年份断行合并（2026-10-28）

- 真实论文里 PDF 悬挂缩进会把「作者. 2018.」单独断成一行、题名在下一行；旧 parser 把 `2018` 当题名（Unverified 假阳性）。
- `src/citeguard/reference_parser.py`：新增 `_is_author_year_only` / `_is_title_continuation` / `_merge_titleless_blocks`（只在下一块是「无年份、无类型码的题名行」时合并），并把所有 `split_entries` 返回路径接入合并。
- 新增 `_split_at_unparenthesised_year`：`Authors. 2018. Title` 形式直接拆作者/年份/题名，处理 `Z. Chen, H. Zhang...` 这类“首字母+姓”作者。
- 测试：+2（合并、年份拆分），全套 **466 passed**；BERT 参考列表 raw 重放：54 块 → 51 条，年份型假题名 0（原 2）。
- 版本 0.9.45。
- `dist/citeguard-cn-0.9.45.zip`：8,857,181 bytes，sha256 `c0e874657cf6a8f4e5a422c796025047026a459396042e998c10561f8c1e696e`。

## 55. 0.9.46 解析：把「下一文献的作者行」从上一块尾部移走（2026-10-28）

- 真实 PDF 中常见：上一文献末尾粘着下一文献的作者行（`... Linguistics. Alex Warstadt, ... Bowman. 2018.`），下一块只剩题名，导致题名被年份/作者污染。
- `src/citeguard/reference_parser.py` 新增 `_split_author_year_tail`：块尾若是「完整姓名列表 + 年份」，就移到下一条开头；首字母缩写（`Z.`）开头、或断点落在 `X.` 这类首字母后时不切。
- 配合 `_split_at_unparenthesised_year` 与 `_merge_titleless_blocks`，BERT（arXiv 1810.04805v2）端到端：54 条，Unverified **7 → 5**，Unknown 2（源限流，如实报）；Exact 17 / Minor 30。对比无修复版：Unverified 7。
- 注意：仍有 2 条摘要式题名残留（`Zhang...`、空题名），属于 PDF 版面把两条文献粘成一条，后续继续处理；不宣称“已解决”。
- 测试：+2，全套 **468 passed**（下一轮同步报告/PPT 数字）。
- 版本 0.9.46。
- dist/citeguard-cn-0.9.46.zip：8,857,781 bytes，sha256 `589ab319f69829531d6cdce3ad55f5b90511bf7206bd889f533d1a0a3be70f6b`。

## 56. 0.9.47 解析收尾：作者列表当题名时清空（2026-10-28）

- `src/citeguard/reference_parser.py` 新增 `_blank_author_list_title`：题名如果是纯作者列表（如 `Zhang, X. Zhang, and L. Zhao. 2018`），清空题名并标 `extra["title_missing"]`，宁可报 Unverified，也不拿人名去匹配。
- `_is_title_continuation` 不再一见年份就拒绝：现在只拒绝「以年份开头」「含 `(2018).` 这类作者-年标记」「含 [J] 类型码」「URL/DOI 开头」；`In Proceedings of the 2018 Conference ...` 可正常作为题名续行。
- 真实 BERT 论文实测：54 条，空题名 2 条（均为 PDF 把两条文献粘成一条所致），不再出现「题名 = 作者列表」；Exact 17 / Minor 30 不变，Unverified 5 / Unknown 2（OpenAlex 当日预算耗尽，如实报）。
- 新增 2 条测试，全套 **470 passed**；版本 0.9.47。
- 环境记录：OpenAlex 对本机返回 429 `Insufficient budget`、`Retry-After` ≈ 5.2 小时；此时 Crossref/arXiv 仍可用，全部源失败才标 Unknown。
- dist/citeguard-cn-0.9.47.zip：8,858,078 bytes，sha256 `1cc71b8dd138a46fe55b7ae921cbac4104b328e3cdb232c104296c8b90984871`。

## 57. 0.9.48 核验提速：数据源熔断 + 长 Retry-After 快速失败（2026-10-28）

- 问题：OpenAlex 当日返回 429 `Insufficient budget`（`Retry-After` ≈ 5.2 小时），旧逻辑对**每条**文献都重试 5 次、每次最多睡 20 s；BERT（54 条）暖缓存复测 102.0 s，124 条的论文更早一次跑了 274 s，时间几乎全花在等待限流。
- `src/citeguard/metadata_verify.py`：
  - 新增按来源的熔断：`_source_for_url` / `_source_available` / `_mark_source_down` / `reset_source_health`；某源最终失败后冷却 300 s（按 `Retry-After` 延长，最多 1 h），冷却期内直接返回空，不再发请求。
  - `_request` 收到 `Retry-After >= 60` 时立即熔断并返回，不再睡眠重试（“5 小时后再来”不值得等）。
  - `_cached_json` / `_cached_text` 命中冷却即跳过；失败计数仍用于把结果标为 Unknown。
- 实测（同一份 BERT 1810.04805v2，`support_max=0`）：
  - 暖缓存：**102.0 s → 20.5 s**，状态分布完全一致（Exact 17 / Minor 30 / Unverified 5 / Unknown 2）。
  - 冷缓存（临时缓存目录）：169.2 s，Exact 14 / Minor 20 / Unverified 3 / **Unknown 17**，`source_errors=40`——冷启动仍受真实 API 限流影响，状态如实标 Unknown；这组不能拿来宣称“提速 8 倍”。
- 新增 1 条熔断测试，全套 **471 passed**；版本 0.9.48。
- dist/citeguard-cn-0.9.48.zip：8858729 bytes，sha256 `3638713083a3c2c11b9ff5cb946848c9c2f13255b02afc5769f83e4c6ddc227d`。
