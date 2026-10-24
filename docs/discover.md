# 选题与文献发现（OpenAlex）

模块 E：给定一个研究主题，从 [OpenAlex](https://openalex.org/) 的开放作品索引检索候选文献，按一套**写死、可解释**的规则重排后展示，可勾选加入本地题录库，或导出 CSV 交给别的工具。

它解决的是「从一个主题词开始找几篇能读的论文」这一步，不解决「这篇引文是不是真的」「这篇论文说了什么」——后者分别由引文真实性核验与多篇文献对比负责。

## 数据来源与边界

- 只调用 `https://api.openalex.org/works`，带 `mailto` 的礼貌池请求；不抓取、缓存或转存任何全文，只存题录元数据。
- 读取字段：题名、作者、年份、来源刊/会议、DOI、OpenAlex ID、类型、语言、被引量、是否 OA、最佳 OA 链接。
- 结果在本地磁盘缓存 **7 天**（`data/cache/discover/`）；网络失败时若有过期缓存则回退使用，否则报 `OpenAlex 请求失败`。
- 中文主题能搜到中文文献，但召回率完全取决于 OpenAlex 的中文覆盖；搜不到不代表没有这篇论文。

## 排序规则（不是学习排序）

OpenAlex 已按 `relevance_score:desc` 返回，本模块在这个顺序上再加四项可解释信号：

```
match_score = 1/(1+OpenAlex序号)          # 保留上游相关度
            + 2.0 × 查询重合度             # 标题里命中查询词/汉字二元组的比例，0..1
            + 0.35 × min(log10(1+被引), 3) # 被引量，封顶
            + 新近度(近 3 年 0.3 / 近 8 年 0.15 / 更早 0)
            + 0.1 × 是否 OA
```

`match_score` 只用于同一次检索内部的相对排序，不是概率，也不代表论文质量。

## 使用方式

### Web

`/discover`：输入主题 → 选返回条数（10/20/30）/起始年份/只看 OA → 检索 → 勾选 → 「加入题录库」或「导出 CSV」。

### HTTP API

```bash
# 检索
curl -s -X POST http://127.0.0.1:8010/api/discover \
  -H 'Content-Type: application/json' \
  -d '{"query":"人工智能 教育","limit":10,"year_from":2018,"oa_only":false}'

# 导出 CSV（UTF-8 BOM，Excel 可直接打开）
curl -s 'http://127.0.0.1:8010/api/discover/export?query=retrieval%20augmented%20generation&limit=20&oa_only=true' -o discovery.csv

# 勾选结果加入题录库（去重按规范化题名）
curl -s -X POST http://127.0.0.1:8010/api/discover/import \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"title":"...","authors":["..."],"year":2024,"venue":"...","doi":"10.xxxx/..."}]}'
```

**入库语义**：只写题录（题名/作者/年/刊/DOI/OA 链接/类型），`source` 标记为 `openalex-discover`；同一规范化题名已存在时跳过。入库**不会**自动核验该文献，也不会改变已有引文的核验结论；要核验仍走工作台。

## 实测（工程可用性，不是排序质量评测）

同一台机器、2026-10：

| 查询 | 条件 | 上游命中 | 首次请求 | 结果观察 |
|---|---|---|---|---|
| `人工智能 教育` | 10 条 | 112,724 | 1.82 s | 前 10 条均为中文 AI 教育论文 |
| `retrieval augmented generation` | 2022 起 + 仅 OA，10 条 | 133,725 | 1.56 s | 前 10 条均为 RAG 主题论文，2023–2025 |
| 相同查询重复请求 | 命中缓存 | — | 0.02 s | 返回一致 |

以上只说明「能查、能排、能展示、能入库」；**没有任何 relevance 标注集**，因此不报告 NDCG/Precision 之类的排序指标。

## 代码与测试

- `src/citeguard/discover.py`：`search_papers()` / `rank()` / `import_entries()` / `render_csv()`
- `web/app.py`：`/discover`、`POST /api/discover`、`GET /api/discover/export`、`POST /api/discover/import`
- 前端：`web/templates/discover.html`、`web/static/js/discover.js`
- 测试：`tests/test_discover.py`（9 项，纯离线，monkeypatch 掉网络）、`tests/test_web.py`（页面/API/导入/导出）
- 复现：`python -m pytest tests/test_discover.py tests/test_web.py -q`
- 冒烟：

```python
from citeguard import discover
res = discover.search_papers("人工智能 教育", limit=10)
print(res["matched"], [i["title"][:40] for i in res["results"][:3]])
```

## 局限

- 排序是启发式，不是训练出来的推荐模型，也没有做个性化或引用网络分析。
- 中文召回受 OpenAlex 覆盖限制；拿不到全文，也不判断论文质量。
- 只返回 OpenAlex 当页结果（最多 30 条），没有分页/去重跨页合并。
- 入库只写题录，不是「已核验」；带 DOI 的条目仍需在工作台或题录库里核验。
