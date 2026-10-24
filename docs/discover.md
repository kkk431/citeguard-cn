# 选题与文献发现（OpenAlex）

模块 E：给定一个中文研究主题，先把它扩展成中英双语检索词，再从 [OpenAlex](https://openalex.org/) 的开放作品索引检索候选文献，合并去重后按一套**写死、可解释**的规则重排，以卡片形式展示（摘要、被引、OA、命中理由），可筛选语言、切换排序、分页、勾选加入本地题录库，或导出 CSV。

它解决的是「从一个主题词开始找几篇能读的论文」这一步，不解决「这篇引文是不是真的」「这篇论文说了什么」——后者分别由引文真实性核验与多篇文献对比负责。

## 检索流程

```
中文主题
  → 查询扩展（可选，LLM）：英文检索式 ≤120 字符 + 3–6 个关键词
  → OpenAlex /works：原查询 + 英文检索式各取一页（每页固定 100 条，礼貌池）
  → 合并去重（DOI → 规范化题名；摘要取更长、被引取更大、OA 取并集）
  → 默认过滤撤稿记录
  → 透明规则重排
  → 分页切片（稳定：同一查询的各页使用同一固定候选池）
  → 卡片列表 / 排序 / 语言筛选 / 勾选入库 / CSV
```

- 查询扩展关闭或不可用时**只检索原查询**，页面会注明「未扩展」，不会假装做过双语检索。
- 中文主题能搜到中文文献，但召回率完全取决于 OpenAlex 的中文覆盖；搜不到不代表没有这篇论文。
- 只调用 `https://api.openalex.org/works`，带 `mailto` 的礼貌池请求；不抓取、不缓存、不转存全文，只存题录元数据（含 OpenAlex 摘要倒排索引重建的摘要，截断 240 字）。
- 网络结果缓存 **7 天**（`data/cache/discover/`），扩展结果按「模型 + 版本 + 查询」缓存（`data/cache/discover/expand/`）；网络失败时若有过期缓存则回退使用，否则报 `OpenAlex 请求失败`。

## 排序规则（不是学习排序）

```
match_score = 1.0 × 归一化相关度            # 原查询/扩展查询各自的上游 relevance，按本池最大值归一
            + 2.0 × 标题重合度              # 原查询与扩展查询取较大者
            + 0.9 × 关键词重合度
            + 0.35 × min(log10(1+被引), 3)
            + 新近度（近 3 年 0.3 / 近 8 年 0.15 / 更早 0）
            + 0.1 × 是否 OA
            − 1.0（若已撤稿，默认已被过滤）
```

- `match_score` 只用于同一次检索内部的相对排序，不是概率，也不代表论文质量。
- 每张卡片给出 `reason`：命中词来自标题或关键词；只命中英文扩展检索式时标注「英文扩展命中」。
- 排序可切换为「相关度 / 被引次数 / 最新年份」；语言筛选（全部 / 中文 / 英文）在前端完成，不重新请求。

## 分页与稳定排序

- 每页 10 / 20 / 30 / 50 条，最多 5 页；`page` 从 1 开始。
- 每次请求对每个查询固定取 100 条候选池，再对**同一池**重排、切片。这样第 2 页不会因为重新取数导致排序漂移、条目重复或漏条。
- `matched` 是 OpenAlex 对该查询的上游命中总数（含扩展检索时取并集口径），不是可翻页条数；`has_more` 只表示当前池里还有下一条可切。

## 使用方式

### Web

`/discover`：输入主题 → 选条数 / 起始年份 / 只看 OA / 是否查询扩展 / 是否显示撤稿 → 检索 → 卡片列表（可切换排序、筛选语言）→ 勾选 → 「加入题录库」或「导出 CSV」；支持「加载更多」与一键全选。

### HTTP API

```bash
# 检索（expand: auto | off；sort: relevance | citations | year）
curl -s -X POST http://127.0.0.1:8010/api/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"人工智能 教育","limit":20,"page":1,"sort":"relevance","expand":"auto","include_retracted":false}'

# 导出 CSV（UTF-8 BOM，Excel 可直接打开；参数与检索一致）
curl -s 'http://127.0.0.1:8010/api/discover/export?query=%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD%20%E6%95%99%E8%82%B2&limit=20&sort=citations' -o discovery.csv

# 勾选结果加入题录库（按规范化题名去重）
curl -s -X POST http://127.0.0.1:8010/api/discover/import \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"title":"...","authors":["..."],"year":2024,"venue":"...","doi":"10.xxxx/..."}]}'
```

**入库语义**：只写题录（题名/作者/年/刊/DOI/OA 链接/类型），`source` 标记为 `openalex-discover`；同一规范化题名已存在时跳过。入库**不会**自动核验该文献，也不会改变已有引文的核验结论；要核验仍走工作台。

## 实测（工程可用性，不是排序质量评测）

同一台机器，2026-10-24，查询 `人工智能 教育`：

| 条件 | 上游命中 | 耗时 | 观察 |
|---|---|---|---|
| `expand=auto`，第 1 页，冷启动（含扩展 + 两次上游请求） | **1,141,987** | 6.16 s | 20 条，中文 3 条，英文扩展式 `artificial intelligence AND education` |
| 相同查询，缓存命中 | 1,141,987 | **76 ms** | 结果一致 |
| 第 2 页（固定候选池） | 1,141,987 | 32–143 ms | 20 条，与第 1 页**零重叠** |
| `expand=off` | 112,724 | 17 ms（缓存） | 20 条，中文 8 条 |

扩展把上游命中从 11.2 万扩大到 114 万，代价是冷启动多一次 LLM 调用（约 4–5 秒）和更高的英文占比；这两种模式都保留，由用户显式选择。

以上只说明「能扩展、能查、能排、能展示、能入库」；**没有任何 relevance 标注集**，因此不报告 NDCG/Precision 之类的排序指标。中文结果占比是观察值，不代表排序质量。

## 代码与测试

- `src/citeguard/discover.py`：`expand_query()` / `search_papers()` / `rank()` / `_dedupe()` / `import_entries()` / `render_csv()`
- `web/app.py`：`/discover`、`POST /api/discover`、`GET /api/discover/export`、`POST /api/discover/import`
- 前端：`web/templates/discover.html`、`web/static/js/discover.js`（排序/语言筛选/分页/批量选择/入库）
- 测试：`tests/test_discover.py`（16 项，纯离线，monkeypatch 掉网络与扩展）、`tests/test_web.py`（页面/API/导入/导出）
- 复现：`python -m pytest tests/test_discover.py tests/test_web.py -q`
- 冒烟：

```python
from citeguard import discover
res = discover.search_papers("人工智能 教育", limit=20, page=1, sort="relevance")
print(res["matched"], len(res["results"]), res["results"][0]["reason"])
```

## 局限

- 排序是启发式，不是训练出来的推荐模型，也没有做个性化、引用网络分析或语义向量召回。
- 查询扩展依赖已配置的判定模型；不可用时退化为原查询，召回会明显下降（中文主题尤其如此）。
- 中文召回受 OpenAlex 覆盖限制；拿不到全文，也不判断论文质量。
- 最多 5 页 / 50 条；`matched` 是上游计数，翻到底不代表「看完所有相关文献」。
- 入库只写题录，不是「已核验」；带 DOI 的条目仍需在工作台或题录库里核验。
