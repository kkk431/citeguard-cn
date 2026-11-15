# Live 48h spike：页面文献列表 → `[n]` → 被引来源

> 目标：验证“页面里的 `[n]` 能不能稳定指到页面参考文献列表的第 n 条，并落到被引来源”。
> 这是解析/定位 spike，不判真伪、不接产品路由、不下载模型。结果 JSON：
> `data/experiments/live_spike.json`（仓库内路径，不在文档站内链接）。

## 0. 结论

| 问题 | 结论 |
| --- | --- |
| 3 个真实页面（2 arXiv + 1 Wikipedia）能否抽取正文与文献列表 | 能；`readability-lxml 0.9` 直出 3/3 |
| `[n]` → reference 映射率 | **146/146 = 100%**，目标 ≥80% **达到** |
| 每页 ≥5 条引用句的来源定位 | **17/17 = 100%**（按页面文献条目的 DOI 或标题复核） |
| 与现有 `check_claim` 的来源定位对照 | arXiv **12/12**；Wikipedia **不适用**（现有 Live 只对 arXiv HTML 建映射） |
| 失败页 / 限制 | 另 3 个 arXiv 页的 `readability-lxml` summary 会塌缩（0 条文献），需 raw body 兜底；标记“检出率”另需评估（见 §4） |

一句话：**映射本身足够稳，但“检出所有 `[n]`”与“页面结构覆盖”比“映射”更值得投入**；arXiv 与 Wikipedia 的锚点式标记可以直接复用，纯文本/非常规站点需要补扫描与兜底。

## 1. 方法

- 选页（真实、可公开访问，2026-11-16 抓取）：
  - `https://arxiv.org/html/2611.07772` — 软件工程实证研究（54 条文献，无 DOI 字段，靠标题匹配）。
  - `https://arxiv.org/html/2610.18926` — 医学影像配准（19 条文献，多数带 DOI）。
  - `https://en.wikipedia.org/wiki/Retrieval-augmented_generation` — 22 条 `cite_note`，11 条带 DOI，其余只有标题/URL。
- 抽取器：**readability-lxml 0.9（Apache-2.0，Python）**，通过 `Document.summary()` 取正文；文献列表始终从原始 HTML 解析（summary 可能丢列表）。
  - 备选 Readability.js 0.6.0（Apache-2.0）没有用：本机 Playwright 1.64 已装但浏览器二进制为空（`chrome-headless-shell` 不存在），不下载浏览器，故选纯 Python 路径。
  - `readability-lxml` 不在 `requirements.txt`，属于 spike 可选依赖；缺失时 `live_page` 给出安装提示（`pip install readability-lxml==0.9`）。
- 冒烟命令（不联网、纯函数）：

```powershell
cd D:\ai+ky\citeguard
$env:PYTHONPATH='src'
python -m pytest tests/test_live_page.py -q
```

- 复现 spike（联网；抓 3 页 + 调 `check_claim`，约 1–2 分钟）：

```powershell
cd D:\ai+ky\citeguard
python scripts/spike_live_pages.py --timeout 20
# 只做映射、不调 check_claim：
python scripts/spike_live_pages.py --no-check-claim
```

## 2. 映射结果（主结果）

| 页面 | 抽取模式 | 正文字符 | 文献条数 | `[n]` 标记数 | 已映射 | 映射率 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| arXiv 2611.07772 | readability-lxml | 77,971 | 54 | 78 | 78 | 100% |
| arXiv 2610.18926 | readability-lxml | 68,820 | 19 | 23 | 23 | 100% |
| Wikipedia RAG | readability-lxml | 17,559 | 22 | 45 | 45 | 100% |
| **合计** | | | **95** | **146** | **146** | **100%** |

前 5 条样例（JSON `pages[].samples`）：

| 页面 | 标记 | 映射到的文献 |
| --- | --- | --- |
| 2611.07772 | `[1]` | *Conducting realistic experiments in software engineering*（URL 为 dx.doi.org/10.1109/ISESE.2002.1166921，页面无 DOI 字段） |
| 2611.07772 | `[2, 3]` | *Are students representatives of professionals…* / *Empirical software engineering experts…* |
| 2610.18926 | `[1, 2, 3]` | 3 条放射治疗文献，DOI 均解析为 `10.1016/j.semradonc.2019.02.006` 等 |
| 2610.18926 | `[6]` | *VoxelMorph*，DOI `10.1109/tmi.2019.2897538` |
| Wikipedia | `[2]` | *Retrieval-Augmented Generation for AI-Generated Content: A Survey*，DOI `10.1007/s41019-025-00335-5` |

`mapped_ratio` 的分母只统计**正文中检测到的标记**（参考文献列表的编号不计入）；它不是“页面全部引用标注的召回率”。

## 3. 引用句 → 被引来源定位（≥5 条/页）

`claims_holdout.jsonl` 中两篇 arXiv 各取 6 条引用句（每条带 `source_title` / `source_doi`）；
Wikipedia 页没有现成标注，从正文中选“恰好一个标记 + 该标记指向有标题文献”的句子 5 条
（4 条唯一 DOI 文献用完后，第 5 条复用文献按标题匹配；这不是人工金标）。

| 页面 | 引用句 | 标记已映射 | 命中 gold（DOI 或标题） | 备注 |
| --- | ---: | ---: | ---: | --- |
| arXiv 2611.07772 | 6 | 6 | 6（全部标题） | 页面文献无 DOI，标题 token 覆盖 ≥0.8 |
| arXiv 2610.18926 | 6 | 6 | 6（全部 DOI） | 含多标记 `[1,2,3]`、`[6]…[11]`、`[12,13,14]` |
| Wikipedia RAG | 5 | 5 | 5（标题；1 条 DOI） | 页面文献缺 DOI 时按标题匹配 |
| **合计** | **17** | **17** | **17** | 100% |

## 4. 与现有 `check_claim` 对照（不判官）

对每条引用句调用 `check_claim(sentence, page_url, page_title, mode="fast", phase="retrieve")`，
只看返回的 5 条候选里是否有 gold DOI/标题：

| 页面 | 调用 | 命中 | 说明 |
| --- | ---: | ---: | --- |
| arXiv 2611.07772 | 6 | 6 | 命中 DOI（OpenAlex 候选补全了页面缺失的 DOI） |
| arXiv 2610.18926 | 6 | 6 | 命中 DOI |
| Wikipedia RAG | 5 | 1 | 现有 `live_check` **不给 Wikipedia 建页面映射**；1 条是标题碰巧重合，不作为能力证据 |
| **合计** | **17** | **13** | arXiv 12/12；Wikipedia 不适用 |

耗时（同一进程、已有页面/文献缓存）：首条 907 ms，其余 10–72 ms；另一轮冷启动单条实测 **9.77 s**（含页面抓取与外部检索，网络相关）。
所有调用 `errors=0`，未出现异常；`label` 均为 `no_evidence` 只是因为 `phase=retrieve` 不调用判官，不代表来源定位失败。

## 5. 失败页与结构兜底

在同样 5 个 arXiv HTML 上（同一 `readability-lxml 0.9`，缓存 HTML 复跑），summary 有两种失效：

| 页面 | summary 文本 | jsdom+Readability.js 文本 | summary 文献数 | 处理 |
| --- | ---: | ---: | ---: | --- |
| 2610.24037 | 32,006 | 66,583 | 0 | raw body 兜底 → 60 条文献、23 个标记、100% 映射 |
| 2610.32576 | 30,198 | 90,413 | 0 | raw body 兜底 → 63 条文献、96 个标记、100% 映射 |
| 2610.38049 | **1,512** | 84,590 | 0 | raw body 兜底 → 126 条文献、119 个标记、100% 映射 |

`live_page.build_page_model` 的兜底规则（已写进代码并测试）：summary 文本 <1500 字符，或 summary
文献数 < 原始文献数的 80%，即切到 raw body，并把 `extractor.mode` 标为 `body-fallback`
（不静默假装成功）。

注意：2610.24037 的 23 个标记明显少于 jsdom 统计的 136 个（jsdom 统计含参考文献列表标签与纯文本标记）。
当前实现**优先用锚点**（arXiv `a.ltx_ref`、Wikipedia `a[href^=#cite_note]`），只有整页一个锚点都没有时才扫描纯文本。
因此“映射率 100%”不等于“检出率 100%”——这是下一轮最该补的：锚点与纯文本标记合并去重，并用人工标注评估召回。

## 6. 目标判定与替代方案

- **≥80% 映射率：达到（100%，146/146）**，且 3/3 页面均成功。
- **不足与替代**：
  - 纯文本/无锚点页面：需要“文本扫描 + 锚点合并”，并抑制参考文献区、年份区间（如 `[2020]`）误报；当前 0/3 失败页在兜底后映射正常，但标记数偏低。
  - 出版商页面（Nature/Springer/MDPI）：服务端实测 Bot 墙/403，不能靠服务端抽取；应把抽取放到扩展侧（activeTab + Readability.js），本 spike 未覆盖。
  - 中文页面：本次未取得可复现样本（Wikipedia 中文返回 HTTP 429），全角括号只在单元测试中覆盖，真实中文页待补。
  - `check_claim` 目前只对 arXiv HTML 建页面映射；若要让 Wikipedia/出版商页也走 `[n]`，需要把 `live_page` 的页面模型接入 `live_check`（t25 边界：不改 `live_check`，仅纯函数调用）。

## 7. 交付物与边界

| 文件 | 作用 |
| --- | --- |
| `src/citeguard/live_page.py` | 纯函数：抓取/解析/文献列表/标记/映射；不接路由、不写数据库 |
| `scripts/spike_live_pages.py` | 3 页 spike 驱动，写 `data/experiments/live_spike.json` |
| `tests/test_live_page.py` | 追加 6 条映射测试（arXiv 样式、无文献、乱序编号、全角括号、缺失标记、DOI/标题匹配） |
| `data/experiments/live_spike.json` | 本次真实数字（可用上面的命令重新生成） |

边界：不改 `web/`、`extension/v2/`、`live_check.py`；不下载模型、不跑 GPU；spike 结果不作为产品能力宣称。
`check_claim` 的 Wikipedia 1/5 标题命中不计入“来源定位”能力；真实判官未运行。
