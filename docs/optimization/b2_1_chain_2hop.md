# B2.1 引用链 2 跳（实现、样例与阻塞）

## 实现

`src/citeguard/retraction.py::check_chain(..., max_hops=1, hop2_limit=3)`

- 默认仍是 1 跳，产品现有行为不变。
- `max_hops=2` 时，在直接引用里取最多 `hop2_limit` 条“未撤稿且有参考文献表”的中继文献，
  合并其 `referenced_works`（最多 20 个）批量查 `is_retracted`。
- 返回新增：`second_degree`、`second_sampled`、`max_hops`。
- 状态：只要直接或 2 跳发现撤稿，`status=indirect`；detail 区分直接与 2 跳。
- 覆盖仍是**抽样覆盖**，不是全链闭合；中继数量/每条 ref 数都有上限。

## 单元测试

`tests/test_retraction.py::test_chain_two_hop_finds_retraction_one_layer_down`

- 直接引用 W1/W2 未撤稿；W1→W9、W2→W10；W9 撤稿；
- 结果 `indirect`、`retracted=[]`、`second_sampled=2`、`second_degree=[W9]`。
- `tests/test_retraction.py` **11 passed**。

## 真实样例（固定 8 个 DOI）

脚本：`scripts/eval_b2_chain_2hop.py`
数据：`data/experiments/opt_b2_1_chain_2hop_real_2026-11-27.json`

| DOI | 结果 | 直接撤稿 | 2 跳抽样 | 2 跳撤稿 |
|---|---|---|---|---|
| 10.1038/nature14539 | clean | 0 | 5 | 0 |
| 10.1080/14653240600855905 | indirect | 1 | 20 | 0 |
| 10.48550/arXiv.1810.04805 | clean | 0 | 20 | 0 |
| 其余 5 个 | error | — | — | — |

5 个 `error` 的原因是运行中 OpenAlex 返回不可用/限流，不是“没撤稿”。即使 3 个成功样例里，
唯一命中的撤稿是**直接引用**，2 跳没有新增正例。

## 结论与边界

- 2 跳在真实样例里**没有展示出增量价值**；不把它设为产品默认，只保留可选参数与单测。
- 没有真实 2 跳覆盖率/召回数字；不能写“支持 2 跳发现”。
- OpenAlex 的引用表覆盖不全、中文文献弱、限流明显；完整传递闭包不在本轮范围。
- 不把 unit test 的合成中继当成真实世界覆盖率。
