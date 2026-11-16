# 引用链风险：一层间接撤稿检查

报告页的「引用链风险」不是撤稿提醒的重复，而是再往前问一步：

> 这篇被引论文自己，有没有引用一篇已经撤稿的论文？

它只做**一层**（被引论文 → 它的参考文献），不做传递闭包，也不声称“整条引用链干净”。

## 怎么触发

- 只选**已匹配且带 DOI** 的条目（`verify.status` 为 `Exact` / `Minor`）。
- 每次最多 8 条被引论文；每条被引论文最多抽样 12 篇参考文献。
- 在报告页点「检查引用链」，或调用接口；结果缓存在任务目录的 `report.chain.json`。
- 不做自动分析，避免每次体检都多付 2–10 秒网络时间；用户需要时再点。

```
GET  /api/report/{job_id}/citation-chain   # 读缓存
POST /api/report/{job_id}/citation-chain   # 重新检查（4 路并发）
```

返回：

```json
{
  "available": true,
  "summary": {
    "checked": 8,
    "references_sampled": 96,
    "references_checked": 96,
    "retracted_found": 1,
    "indirect": 1,
    "clean": 7,
    "no_references": 0,
    "error": 0,
    "average_coverage": 1.0
  },
  "items": [
    {
      "index": 2,
      "doi": "10.1080/14653240600855905",
      "title": "Minimal criteria for defining multipotent mesenchymal stromal cells",
      "status": "indirect",
      "sampled": 8,
      "checked": 8,
      "coverage": 1.0,
      "retracted": [
        {
          "id": "W2158048826",
          "doi": "https://doi.org/10.1038/nature00870",
          "title": "RETRACTED ARTICLE: Pluripotency of mesenchymal stem cells derived from adult marrow"
        }
      ],
      "detail": "抽样的 8 条引用文献中，1 条被撤稿"
    }
  ]
}
```

## 状态怎么读

| 状态 | 含义 | 不能说什么 |
| --- | --- | --- |
| `indirect` | 抽样的参考文献里找到了 OpenAlex 标记为撤稿的文献 | 不能说“这篇论文整体不可信” |
| `clean` | 抽样范围内未发现撤稿 | 不能说“整条引用链干净” |
| `no_references` | OpenAlex 没有收录这篇文献的参考文献表 | 不能当成“没有撤稿引用” |
| `error` | 源不可用/超时/DOI 非法 | 不能当成 clean |

`平均抽样覆盖` = 返回的参考文献条数 / 抽样的参考文献条数。它只描述**抽样内的完整度**，不是全量覆盖率；论文参考文献表很长时，12 条只是抽样。

## 真实冒烟

- `10.1038/nature14539`（Deep learning）：抽样 5 条，5/5 返回，`clean`。
- `10.1080/14653240600855905`（间充质干细胞最小标准）：抽样 8 条，8/8 返回，`indirect`；命中 `10.1038/nature00870`（被撤稿的间充质干细胞论文）。
- 面板实测（真实报告 `96511af51c97`，15 条引用）：8 条被引论文、抽样 96 条、间接撤稿 0、平均抽样覆盖 100%。
- 截图：`docs/evidence/shots/phase-68-citation-chain-1.7.34.png`。

## 边界

- 依赖 OpenAlex `referenced_works` 与 `is_retracted`；中文文献和部分出版商记录覆盖不足。
- 只查一层，不做 2 跳；不做“撤稿结论是否被实际采用”的语义判断。
- 不返回参考文献全文，不把撤稿旗标当成论文质量结论。
- 这是工程级风险提示，不是研究级引用链分析。
