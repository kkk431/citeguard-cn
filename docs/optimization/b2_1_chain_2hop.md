# B2.1 引用链 2 跳（实现与真实阻塞）

## 实现

`src/citeguard/retraction.py::check_chain(..., max_hops=1, hop2_limit=3)`

- 默认仍是 1 跳，产品现有行为不变。
- `max_hops=2` 时，在直接引用里取最多 `hop2_limit` 条“未撤稿且有参考文献表”的中继文献，
  合并其 `referenced_works`（最多 20 个）批量查 `is_retracted`。
- 返回新增：`second_degree`（2 跳撤稿记录）、`second_sampled`、`max_hops`。
- 状态：只要直接或 2 跳发现撤稿，`status=indirect`；detail 区分“直接”与“2 跳抽样”。
- 覆盖仍是**抽样覆盖**，不是全链闭合；中继数量/每条 ref 数都有上限。

## 单元测试

`tests/test_retraction.py::test_chain_two_hop_finds_retraction_one_layer_down`

- 直接引用 W1/W2 未撤稿；
- W1→W9、W2→W10；W9 撤稿；
- 结果 `indirect`、`retracted=[]`、`second_sampled=2`、`second_degree=[W9]`。
- 全套 retraction 测试 **11 passed**。

## 真实阻塞

对 `10.1080/14653240600855905`、`10.1038/nature14539` 跑 2 跳时，OpenAlex 引用列表批次返回失败：

```text
status=error checked=0 detail=引用列表查询失败
```

因此**没有真实 2 跳数字**。这是外部源/限流问题，不是“2 跳有效”的证据；不写覆盖率、不写召回。

## 边界

- 2 跳只覆盖 OpenAlex 有 `referenced_works` 的中继；中文文献/出版商页面大量缺失。
- 不是完整传递闭包；不能承诺“整条引用链干净”。
- 产品默认仍 1 跳；2 跳目前只供评测/未来开关。
- 不把 unit test 的合成中继当成真实世界覆盖率。
