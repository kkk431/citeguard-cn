# CiteGuard Live：划词核验模块与接口契约

CiteGuard Live 面向“读到一个看起来像论文结论的句子，想快速知道有没有论文摘要
支持/反驳它”的场景。浏览器扩展把**用户选中的那一句**发给本地服务；服务检索
OpenAlex / Crossref 的候选文献，只读摘要片段，返回四档标签、置信度和可逐字核对
的证据句。

它**不是**事实核查器，也**不读网页全文**。本文件是模块与 HTTP 接口的契约，路由由
队长在 `web/app.py` 接入；本文档不修改任何 web 文件。

## 1. 模块

- 实现：`src/citeguard/live_check.py`（标准库 + 项目内 `metadata_verify` / `support`）。
- 纯函数：`check_claim(claim, page_url="", page_title="") -> dict`。
- 无模型也可用：未配置判定模型时，使用本地规则（关键词/数字覆盖 + 方向线索）兜底，
  `reason` 会明确写“使用本地规则兜底”。
- 离线可降级：`CITEGUARD_OFFLINE=1` 时不检索外部文献，返回 `no_evidence`，
  `reason` 写明离线模式。
- 不伪造证据：`evidence.quote` 必须是某个候选摘要的精确子串；对不上就返回
  `evidence: null`，并把置信度压低。

### 1.1 处理流程

1. 规范化 claim：去首尾空白，截断到 500 字；空句直接返回 `no_evidence`。
2. 识别当前页面：`page_url` 中的 DOI 或 arXiv ID → OpenAlex work；失败时用
   `page_title` 搜索并取题名最相近的一条（相似度阈值见 §8）。识别不到就跳过。
3. 页面引用候选：若识别到当前论文，读取其 `referenced_works`（最多 40 条），
   分批查询 OpenAlex，转成候选并还原摘要；引用候选排在关键词候选之前。
4. 提取检索词：CJK 连续块 + 英文实词（去掉引用标记、标点、常见停用词）；若过短，
   用 `page_title` 兜底。页面候选已覆盖且有摘要时，跳过这一步与关键词检索。
5. 否则调用（顺序执行、各自异常隔离）`metadata_verify.search_openalex` 与
   `search_crossref`，各取前 5；把页面候选与关键词候选按 DOI / 标题 / URL 去重合并。
6. 用“摘要/标题词项覆盖 0.8 + 数字覆盖 0.2”排序，保留前 5 个候选；页面候选优先。
7. 若配置了判定模型：对最多 3 个有摘要的候选调用 `support.judge_support`；
   取 support > contradict > partial > no_evidence 的最优结果；证据句用
   `support.evidence_grounded` 校验并回退到摘要中完整句。
8. 否则（或模型调用失败）：本地规则兜底。支持需覆盖 ≥0.45、claim 中数字全部命中、
   最短子句覆盖 ≥0.35；部分支持/矛盾按覆盖与方向线索判定；阈值见模块常量。
9. 返回固定结构；候选列表最多 5 条，摘要截断 2000 字。

### 1.2 四档标签

| label | 含义 | 备注 |
| --- | --- | --- |
| `support` | 候选摘要中的句子支持选中句 | 仍只是摘要级、单篇级证据 |
| `partial` | 关键词或数字只匹配一部分，或方向不完全一致 | 不能当作完整支持 |
| `contradict` | 候选摘要句的方向与选中句相反 | 需人工点开核对 |
| `no_evidence` | 没有检索到可判断的摘要证据 | **不等于选中句为假** |

`confidence` 是启发式/模型自报的 0–1 分，不是统计置信区间；`reason` 必须是人话，
`candidates` 用于让用户自行追溯。

### 1.3 CLI

```bash
PYTHONPATH=src python -m citeguard.live_check --claim "AI tutoring improves learning outcomes"
PYTHONPATH=src CITEGUARD_OFFLINE=1 python -m citeguard.live_check --claim "任意句子"
```

成功时 stdout 输出缩进 JSON；异常时 stderr 输出 `{"ok": false, "error": ...}`，
退出码 2。`--page-url` / `--page-title` 可选。

## 2. HTTP 接口契约（供队长接入）

### 2.1 `POST /api/live/check`

请求：

```json
{
  "claim": "AI tutoring improves student learning outcomes",
  "page_url": "https://example.org/article",
  "page_title": "Example article"
}
```

| 字段 | 必填 | 类型 | 约束 |
| --- | --- | --- | --- |
| `claim` | 是 | string | 去空白后 1–500 字；非空；超长返回 400 |
| `page_url` | 否 | string | ≤2048；用于识别当前论文（DOI/arXiv）并优先取其 `referenced_works`；不抓取网页正文 |
| `page_title` | 否 | string | ≤300；claim 过短时作为检索兜底，也用于从页面标题反查当前论文 |

成功 `200`：

```json
{
  "label": "support",
  "confidence": 0.78,
  "reason": "未配置判定模型，使用本地规则兜底：候选摘要句关键词覆盖 83%，数字命中 100%",
  "evidence": {
    "title": "Tutoring and outcomes",
    "url": "https://openalex.org/W12345678",
    "quote": "Intelligent tutoring systems improve student learning outcomes in higher education."
  },
  "candidates": [
    {
      "title": "Tutoring and outcomes",
      "authors": ["Test Author"],
      "year": 2024,
      "venue": "Journal of Test Studies",
      "doi": "10.1234/live.test",
      "url": "https://openalex.org/W12345678",
      "source": "openalex",
      "abstract": "Intelligent tutoring systems improve …",
      "score": 0.86,
      "label": "support",
      "confidence": 0.78
    }
  ]
}
```

约束：

- `evidence` 为 `null` 或对象；对象的 `quote` 必须逐字出现在**某个候选**的 `abstract`
  中；没有可核对证据时必须是 `null`。
- `candidates` 最多 5 条；`abstract` 最多 2000 字；`label`/`confidence` 仅在候选
  参与判定时出现。
- `no_evidence` 也是 200：扩展需要拿到 `reason` 和候选列表，不应该用错误弹窗
  代替“没有找到证据”。
- 离线模式建议同样返回 200 + `no_evidence`（模块默认行为）；若服务端要用 503
  表达离线，扩展已能显示人话错误，但请在接口文档中固定一种行为。

错误响应建议：

| 状态码 | 场景 | 响应体 |
| --- | --- | --- |
| 400 | JSON 解析失败、`claim` 缺失/空/超长、字段类型不对 | `{"ok": false, "code": "bad_request", "error": "..."}` |
| 401 | 服务启用 `ACCESS_TOKEN` 且请求未带令牌（现有 `_guard` 中间件） | `{"ok": false, "code": "unauthorized", "error": "..."}` |
| 404 | 路由不存在 | 保持 FastAPI 默认或 `{"ok": false, "code": "not_found"}` |
| 429 | 现有按 IP 限流 | `{"ok": false, "code": "rate_limited", "error": "..."}` |
| 500 | 未预期异常（不要泄露堆栈） | `{"ok": false, "code": "internal_error", "error": "..."}` |
| 503 | 可选：服务端主动离线策略 | `{"ok": false, "code": "offline", "error": "..."}` |

注意：

- 旧版 `/api/support/check` 在离线时返回 503；Live 的四档语义不同，推荐 200。
- 现有 `_guard` 对所有非 static/health 路径生效，并且对非 GET 做限流。若服务配置了
  `ACCESS_TOKEN`，扩展默认不带令牌，需要队长决定：为 Live 放行，或要求扩展加令牌
  （v2 暂不保存令牌）。
- 扩展从 `chrome-extension://` 页面用 host permission 访问 `127.0.0.1`；Chrome
  扩展侧通常不需要服务端 CORS。若同时允许普通网页调用，才需要 CORS 配置。

### 2.2 路由接入示例（队长实现，勿放进本模块）

```python
from fastapi import HTTPException
from pydantic import BaseModel
from citeguard.live_check import check_claim

class LiveCheckRequest(BaseModel):
    claim: str
    page_url: str = ""
    page_title: str = ""

@app.post("/api/live/check")
def api_live_check(req: LiveCheckRequest):
    claim = req.claim.strip()
    if not claim:
        raise HTTPException(status_code=400, detail="claim 不能为空")
    if len(claim) > 500:
        raise HTTPException(status_code=400, detail="claim 最多 500 字")
    return check_claim(claim, page_url=req.page_url.strip(), page_title=req.page_title.strip())
```

若项目统一错误体是 `{"ok": false, "code": ..., "error": ...}`，请用异常处理器包一层；
不要改变 `check_claim` 的 200 响应结构，扩展依赖 `label`/`confidence`/`reason`/
`evidence`/`candidates` 五个字段。

## 3. 扩展 v2

目录：`extension/v2/`（Manifest V3，Chrome/Edge 116+）。

- 入口：网页选中文本 → 右键“用 CiteGuard Live 核验选中句”；或点工具栏图标。
- 展示：四档、置信度、原因、证据句（标题/URL/逐字 quote）、候选列表（可展开）。
- 设置：`options.html` 可改本地服务地址，默认 `http://127.0.0.1:8013`，扩展自动
  追加 `/api/live/check`；“测试连接”会明确显示 200/404/401/超时。
- 无服务时：侧边栏显示“无法连接本地服务（地址）…”，并提供“设置/重试”。
- 不保存访问令牌；不读网页正文；不下载 PDF。
- 详细安装与与旧版差异见 `extension/v2/README.md`。

## 4. 真实页面选取标准与状态

**原则**：不伪造页面、不伪造截图、不把“演示页”写进证据。正式验收页面需满足：

1. 公开可访问的 HTML 页面（不是登录墙、不是纯 PDF、不是图片），文本可选中。
2. 页面包含一句可核查的陈述（研究结论/数据/政策表述），最好附近有论文题名、
    DOI 或参考文献，便于对照候选。
3. 句子长度 12–500 字，中文或英文均可；避免纯提问、纯观点、纯修辞。
4. 稳定性：有固定 URL，验收期间不依赖个性化登录或临时生成的页面。
5. 多样性：AI 教育、医学影像各至少 2 个，兼顾中英文；不把同一篇论文的多个页面
   当作多个独立样本。

本轮候选 5 个均为**公开论文页/出版页**（摘要可见、可选中），用于验证“摘要级证据”
链路；后续可替换为机构新闻/政策页等更接近真实阅读场景的页面。DOI 解析状态来自
CiteMap 语料构建阶段的 Crossref / doi.org 校验（2026-11）。`/api/live/check` 路由
已由队长接入，产品内网页 `/live` 可完成「选中句 → 候选 → 四档」闭环；**浏览器扩展
侧的真实侧边栏交互与截图仍待验收**。

| # | 页面（真实链接） | 主题 | 可核验的句子示例（论文摘要） | DOI/链接状态 | 端到端状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | https://www.nature.com/articles/s41467-024-51260-6 | 医学影像（肝脏病灶） | LiLNet 在良恶性分类上达到 94.7% 准确率/97.2% AUC | DOI 10.1038/s41467-024-51260-6 已解析 | 网页 `/live` 可核验；扩展侧待验收 |
| 2 | https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1268549/full | AI 教育（中国高校） | 中国研究生对 AI 聊天机器人的使用受绩效期望/努力期望等影响 | DOI 10.3389/fpsyg.2024.1268549 已解析 | 网页 `/live` 可核验；扩展侧待验收 |
| 3 | https://doi.org/10.2196/85538 | 医学影像（AI 器械审批） | 2020–2025 年中国批准 154 款 AI 医疗器械，放射学占 106 款 | DOI 10.2196/85538 已解析 | 网页 `/live` 可核验；扩展侧待验收 |
| 4 | https://doi.org/10.1186/s13244-022-01331-3 | 医学影像（卒中 CT） | 多中心模型辅助后放射科医生敏感度从 0.254 提升到 0.333 | DOI 10.1186/s13244-022-01331-3 已解析 | 网页 `/live` 可核验；扩展侧待验收 |
| 5 | https://doi.org/10.1016/S2589-7500(22)00063-2 | 医学影像（公平性） | 深度学习模型可从医学影像预测自报种族，AUC 0.81–0.99 | DOI 10.1016/S2589-7500(22)00063-2 已解析 | 网页 `/live` 可核验；扩展侧待验收 |

> 验证记录不等于“页面内容正确”。第 1–5 条的端到端结果（选中句 → 侧边栏）需在
> 路由接入后由队长/验收人补齐截图；届时应记录：页面 URL、选中句、返回 label/
> confidence、证据句是否逐字出现在候选摘要、耗时与错误情况。

## 5. 已验证 / 未验证

已验证：

- `pytest tests/test_live_check.py -q`：19 passed（网络全部 monkeypatch，无外网）。
- `PYTHONPATH=src CITEGUARD_OFFLINE=1 python -m citeguard.live_check --claim ...`：
  输出可解析 JSON，退出码 0。
- `node --check extension/v2/{background,sidepanel,options}.js`：通过；
  `manifest.json` 可被 JSON 解析。
- 单测覆盖：空句、离线、网络失败、候选去重/截断、数字不一致→partial、
  证据句逐字子串、模型伪造证据句被丢弃、模型调用失败降级、OpenAlex 候选解析、
  JSON 可序列化、CLI；页面 DOI/arXiv 识别、引用列表转候选与摘要还原、40 条上限、
  页面候选优先且去重、页面识别失败回退关键词检索（见 §8）。
- 真实网络冒烟（2026-11，OpenAlex）：DOI `10.1038/s41467-024-51260-6` → 33 条
  引用、31 个候选（19 个有摘要），页面识别 1.33s + 引用查询 2.36s；arXiv
  `2305.01185` → 86 条引用、40 个候选（29 个有摘要），1.46s + 2.55s。

未验证（需后续/队长）：

- 真实 OpenAlex/Crossref 网络下的检索质量与耗时：已做两条真实页面冒烟（见上），
  但 30 句评测集的 hit@3 尚未复跑（由队长重跑）。
- `/api/live/check` 路由已接入 `web/app.py`；扩展侧端到端交互与截图仍待验收。
- 浏览器扩展在 Chrome/Edge 中的真实侧边栏交互与截图；需加载扩展后验收。
- 5 个真实页面的端到端核验；见 §4 状态表。
- 判定模型开启时的真实模型输出质量；无模型仅验证了本地规则兜底。
- 若服务启用 `ACCESS_TOKEN`，扩展未带令牌的限制（见 §3）。

## 6. 边界与隐私

- 只发送选中句 + 页面 URL/标题；不发送网页正文、cookie、登录信息。
- 只检索公开文献元数据/摘要；不下载或提交版权不明的 PDF 全文。
- 候选摘要可能为空、过时或被错误匹配；四档与置信度只是辅助阅读信号。
- `no_evidence` 不是“假”；`support` 也不是“已被科学界证实”。
- 不把模型生成的句子当作证据：没有逐字摘要子串就不返回 `evidence`。

## 7. 产品内网页试用（`GET /live`）

供评委不安装扩展也能走完「划一句 → 检索候选 → 四档判定」的闭环。路由由
`web/app.py` 的 `live_page()` 提供，模板是 `web/templates/live.html`，前端资源为
`web/static/js/live.js` 与 `web/static/css/live.css`。

- 入口：`GET /live`，页面 `active="live"`；工具组 tabs 为
  图表核验 / 多篇对比 / 文献发现 / CiteMap / Live 试用。
- 交互：输入一句话（1–500 字）→ 可展开填写页面标题/URL（可选）→ 点「核验这句」
  或按 `Ctrl/⌘ + Enter` → `POST /api/live/check`，请求体字段为
  `{"claim": ..., "page_title": ..., "page_url": ...}`。
- 结果区：四档标签（支持 / 部分支持 / 矛盾 / 无证据）、置信度条与百分比、理由、
  逐字证据句（标题可点开、原文句用 `textContent` 渲染）、最多 5 条候选（按相关度
  降序，标 OpenAlex/Crossref 来源、年份/期刊、分数与摘要片段）。
- 空状态解释四档；加载中、HTTP 错误、网络失败、空候选都有明确提示，错误时保留
  「重试」。`no_evidence` 与「没查到」不会被渲染成系统故障。
- 安全：所有接口数据通过 `textContent`/DOM API 写入，不拼接 `innerHTML`；页面
  不加载外部 CDN，不读取当前网页正文，不下载 PDF。
- 与扩展一致：网页只调用同一个 `/api/live/check`；服务端返回的
  `{"ok": true, ...}` 包装会被前端解包为 `check_claim` 的结果字段。

已验证：`pytest tests/test_live_page.py -q` 12 passed（模板直接渲染 + `GET /live`
200 + 静态资源 + 无外部 CDN + JS/CSS 静态契约）。页面端到端截图/浏览器交互需在
队长启动服务后补；截图存放位置由验收记录统一管理。

## 8. 页面引用列表增强（arXiv / DOI 论文页）

Live 的典型场景是“正在读一篇论文，划选中一句”。如果当前页能识别成 OpenAlex
work，就直接从该论文的 `referenced_works` 取候选，而不是只靠中文句子去猜英文
检索词。该增强只改变候选来源与排序，不改变四档判定与“只读摘要”边界。

### 8.1 何时生效

1. `page_url` 可解析出 DOI（含 `https://doi.org/...`、`doi:` 前缀）→ 用 DOI 查
   OpenAlex work。
2. `page_url` 是 arXiv 链接（`arxiv.org/abs/...` 或 `/pdf/...`）→ 先转成
   `10.48550/arxiv.{id}` 查 work。
3. 以上失败且提供了 `page_title` → 用标题搜索 OpenAlex，取题名最相近一条；
   归一化标题相似度需 ≥ 0.6，避免把无关页面硬认成论文页。
4. 都失败 → 返回 `None`，完全回退到原来的关键词检索，不抛错。

### 8.2 取哪些候选

- 读取当前 work 的 `referenced_works`，去重后最多 40 条（`MAX_REFERENCED_WORKS`）。
- 按每批 50 个 OpenAlex ID（`REFERENCE_BATCH_SIZE`）请求 `works` 接口，只取
  `id,doi,title,publication_year,authorships,primary_location,abstract_inverted_index`。
- 摘要从 `abstract_inverted_index` 还原；没有摘要的引用仍保留为候选，但不参与
  证据句生成。
- 引用候选排在关键词候选之前；合并时按 DOI / 标题 / URL 去重，最终仍只返回
  最多 5 条（`MAX_CANDIDATES`）。
- 若引用候选中已有摘要，则**跳过** OpenAlex/Crossref 关键词检索，减少延迟；
  若全部无摘要，再跑关键词检索并与引用候选合并。

### 8.3 边界与不保证

- 只适用于能识别出当前论文的页面（arXiv / DOI 论文页）；新闻、博客、政策页、
  登录墙页面通常无法识别，仍走原有关键词检索。
- 引用列表只覆盖“当前论文引用过的文献”。如果选中句引用的是当前论文**没有**
  引用的文献，或引用元数据缺失，不会因为本增强而命中。
- 仍然只读摘要/元数据，不下载或读取 PDF 全文；不判断页面正文是否抄错。
- 引用候选按 claim 词项/数字覆盖排序，中文 claim 与英文题名/摘要仍可能错位；
  本增强不承诺 30 句评测 hit@3 一定提升，需由队长复跑
  `scripts/eval_live.py` 给出前后对比。
- 网络失败、OpenAlex 限流、无 `referenced_works`、摘要缺失都静默降级，不把
  页面识别失败暴露成 500。

### 8.4 候选来源与延迟（估算）

| 页面类型 | 候选来源 | 额外请求 | 未缓存耗时（本机冒烟） |
| --- | --- | --- | --- |
| DOI / arXiv 论文页，引用有摘要 | 引用列表（优先） | 1 次 page-work + 1 次引用批量 | 约 2.5–4s |
| DOI / arXiv 论文页，引用无摘要 | 引用列表 + 关键词检索 | 1 + 1 + 2 次检索 | 约 4–6s |
| 普通网页，标题可反查 | 先标题查 work，再引用列表 | 1 次标题搜索 + … | 取决于是否识别成功 |
| 普通网页，识别失败 | 原关键词检索 | 2 次检索 | 与旧版相同 |

以上是本机、单次、未缓存的冒烟值；命中缓存会明显更快。真实候选质量与 30 句
hit@3 以队长复跑结果为准；不要把本表当作准确率或 SLA。

已验证的页面识别/引用冒烟：

- `https://doi.org/10.1038/s41467-024-51260-6` → work `W4401612605`，33 条引用，
  31 个候选（19 个有摘要）。
- `https://arxiv.org/abs/2305.01185` → work `W4401988281`，86 条引用，
  40 个候选（29 个有摘要，达到 40 条上限）。

