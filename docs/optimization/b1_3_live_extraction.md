# B1.3 Live 页面抽取前移

## 结论

Live 页面引用预检已经在产品里做“抽取前移”：先取页面参考文献与正文 `[n]` 标记，再交给后续单句核验；不再等用户手工贴文献列表。

现有真实夹具（6 页，arXiv/PMC/Wikipedia）结果：

- 文献 252 条；正文标记 451 个；映射 **451/451（100%）**；含引用标记句子 317；mapped sources 246。
- 30/30 引用句能定位到页面来源；6/6 页成功。
- 产品入口：`POST /api/live/page`，返回文献数、标记数、映射数、引用句数与前 8 条样例，不返回正文。

## 边界

- 出版商页面（Nature/Springer/MDPI）是 Bot 墙，服务端抓不到；当前只支持 arXiv/PMC/Wikipedia。
- Wikipedia 有限支持（模板/参考文献结构不稳定）；中文真页未做真实页面验证。
- 100% 只代表这 6 个夹具，不代表任意页面。
- 只做定位，不判断支持/矛盾；判定仍由 `/api/live/check` 完成。

## 复现

```bash
PYTHONPATH=src python scripts/spike_live_pages.py --timeout 20
```

结果：`data/experiments/live_spike.json`；产品记录：`data/experiments/opt_b1_3_live_extraction_2026-11-27.json`。
