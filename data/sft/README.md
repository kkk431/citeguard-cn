# ClaimSupport-CN SFT 数据（A3 扩样版）

供 Qwen3 系列 LoRA 四分类（`support` / `partial` / `contradict` / `no_evidence`）微调使用。
本文件由 `scripts/build_support_sft.py` 在生成数据时按实测数字渲染，不存在占位值。

## 1. 概览

| split | 条数 | support | partial | contradict | no_evidence |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 600 | 238 | 165 | 88 | 109 |
| dev | 20 | 8 | 5 | 4 | 3 |
| test | 60 | 24 | 15 | 9 | 12 |
| **合计** | **680** | **270** | **185** | **101** | **124** |

- 训练样本 **600** 条（验收线 ≥500），三份合计 **680** 条；
- 标签为**规则构造**标签，不是人工标注；没有二次标注 / 一致性系数（kappa）声明；
- dev / test 与历史 80/20/60 版本**字节级一致**（同 id、同内容、同顺序；已对 git
  `HEAD:data/sft/support_dev.jsonl` / `support_test.jsonl` 逐字节比对通过），
  因此之前的 1.7B / 8B / 14B 结果仍可直接与本版 4B 结果对比；
- 本版只扩 train：`train = 20 条借用的官方 dev + ext 60 + v2 140 + a3 380`。

## 2. 标签口径（构造规则继承 `scripts/build_claimsupport.py`，未改动）

| 标签 | 构造规则（一句话） |
| --- | --- |
| `support` | claim 取来源论文摘要首个合格句，evidence 为该句（+第二句上下文），即 claim ⊆ evidence |
| `partial` | claim 为原句，evidence 只保留该句中一个断言从句（`partial_clause`），信息不足以判支持 |
| `contradict` | claim 把 evidence 句中首个反义短语替换（如 显著提高→显著降低，共 29 组），evidence 保留原句 |
| `no_evidence` | claim 来自论文 B、evidence 来自论文 A；两篇标题/句子字符相似度 <0.22 且 bigram Jaccard <0.06，主题不相关 |

每条 a3 数据都由 `build_claimsupport.check_item()` 逐条复算规则自检通过（380/380 条自检通过、0 条失败）；
base / ext / v2 的 300 条沿用原数据卡的自检结论。

## 3. 来源与去重

| 来源数据集 | 条数 | 唯一来源 work 数 | 路径 |
| --- | ---: | ---: | --- |
| base | 100 | 120 | `data/claimsupport_cn/claimsupport_cn.jsonl` |
| ext | 60 | 69 | `data/claimsupport_cn/claimsupport_cn_ext.jsonl` |
| v2 | 140 | 160 | `data/claimsupport_cn/claimsupport_cn_v2.jsonl` |
| a3 | 380 | 455 | `data/sft/claimsupport_a3.jsonl` |

- 每个 item 在 raw jsonl 里带 `claim_source` / `evidence_source`（`openalex_id`、`title`、`doi`、`year`）；
  SFT 三份 jsonl 是训练用瘦身版，只保留 `id/claim/evidence/label/split`；
- 三份 split 的来源 work 交集：train∩dev = 0，
  train∩test = 0，dev∩test = 0；
- id 交集：train∩dev = 0，
  train∩test = 0，dev∩test = 0；
- 全量唯一来源 work：804 篇，被多个 item 复用的 work：0 篇；
- 生成时断言 + `scripts/verify_sft_splits.py` 独立复算（只读三份 jsonl 与 raw 数据集），
  审计结果落盘 `data/experiments/sft_split_audit.json`；抽查样本 `data/experiments/sft_spotcheck.json`。

<!-- audit:start -->
- 在线复核样本 **20** 条：a3 新来源与 base / ext / v2 旧来源交替抽取，四标签轮转；
- **逐字一致 17/20**：同 id、同标题、同年份、同 DOI，且引用片段仍出现在该篇中文摘要中；
- **被 OpenAlex 上游合并 3/20**：标题与年份一致，DOI 为上游新补，抓取时的中文摘要属自动翻译记录（例：`a3-0067` W3152146516 → W2114894403；`a3-0345` W1582756069 → W3146088224；`c2-0015` W3146610601 → W1989039845）；
- 未解释的内容不一致 0 条；明细见 `data/experiments/sft_split_audit.json` 的 `live_sources`。
<!-- audit:end -->

### a3 新增来源（380 条）

- 只读复用 `data/claimsupport_cn/claimsupport_cn.sources.json`（2026-10-28，pages 1..4）中
  **未被前 300 条使用**的 186 篇 work；
- 另从 OpenAlex 新抓取 pages 5..21（filter `language:zh,has_abstract:true,type:article`），
  新增 549 篇 work（每页新增量见下方实测日志）；
- 新来源片段缓存：`data/sft/openalex_sources_a3.json`，sha256 `3dc44ee27b1ef6d7740346541714a6d723298eae8d3ca75f94a9b1115db24770`，
  每篇最多 2 句摘要片段，不存全文；上游元数据许可 CC0 1.0；
- 与现有 300 条（base + ext + v2，349 篇来源）的来源 work 重叠：**0**。

实测抓取日志（`data/sft/claimsupport_a3.meta.json` 的 `fetch_log`）：

```text
[sources] cached unused pool: {'works': 186, 'partial_capable': 63, 'contradict_capable': 0}
[sources] page 5: +4 works, unused pool {'works': 190, 'partial_capable': 66, 'contradict_capable': 1}
[sources] page 6: +4 works, unused pool {'works': 194, 'partial_capable': 68, 'contradict_capable': 2}
[sources] page 7: +21 works, unused pool {'works': 215, 'partial_capable': 79, 'contradict_capable': 12}
[sources] page 8: +48 works, unused pool {'works': 261, 'partial_capable': 107, 'contradict_capable': 20}
[sources] page 9: +83 works, unused pool {'works': 340, 'partial_capable': 153, 'contradict_capable': 26}
[sources] page 10: +94 works, unused pool {'works': 423, 'partial_capable': 203, 'contradict_capable': 40}
[sources] page 11: +119 works, unused pool {'works': 536, 'partial_capable': 266, 'contradict_capable': 59}
[sources] page 12: +45 works, unused pool {'works': 579, 'partial_capable': 296, 'contradict_capable': 68}
[sources] page 13: +4 works, unused pool {'works': 583, 'partial_capable': 298, 'contradict_capable': 68}
[sources] page 14: +4 works, unused pool {'works': 587, 'partial_capable': 299, 'contradict_capable': 69}
[sources] page 15: +7 works, unused pool {'works': 593, 'partial_capable': 303, 'contradict_capable': 70}
[sources] page 16: +10 works, unused pool {'works': 603, 'partial_capable': 307, 'contradict_capable': 72}
[sources] page 17: +23 works, unused pool {'works': 623, 'partial_capable': 319, 'contradict_capable': 77}
[sources] page 18: +31 works, unused pool {'works': 650, 'partial_capable': 332, 'contradict_capable': 83}
[sources] page 19: +36 works, unused pool {'works': 677, 'partial_capable': 342, 'contradict_capable': 91}
[sources] page 20: +25 works, unused pool {'works': 701, 'partial_capable': 355, 'contradict_capable': 95}
[sources] page 21: +36 works, unused pool {'works': 735, 'partial_capable': 376, 'contradict_capable': 100}
[build] unused pool=735 (prior cache=186, new pages=549)
```

## 4. JSONL 字段

每行一个 JSON 对象，键固定 5 个（与旧版 `build_support_sft.py` 完全一致）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | str | 全局唯一，前缀区分批次：`cs-`（base 100）、`cx-`（ext）、`c2-`（v2）、`a3-`（A3） |
| `claim` | str | 引用句 |
| `evidence` | str | 证据片段（截断到 1800 字符） |
| `label` | str | `support` / `partial` / `contradict` / `no_evidence` |
| `split` | str | `train` / `dev` / `test` |

示例（train 第一条，实测）：

```json
{"id": "cs-0002", "claim": "热成像技术具有广泛的应用领域，随着红外焦平面探测器及数字图像处理技术的发展，新型热成像模式及其图像处理技术成为国内外发展的重要方向。", "evidence": "吸附技术能潜在地代替溶剂抽取过程，特别地为有从大常规水库通常是比那低的生产率的新兴的页岩气体井，如果优异吸附物(吸着剂) 被开发。在这评论，我们在吸着剂的三种类型上集中我们的讨论：金属氧化物基于吸着剂, Cu/Ag-based 和另外的广告吸着剂，和胺接枝硅石。", "label": "no_evidence", "split": "train"}
```

微调时由 tokenizer 的 chat template 渲染成对话格式：system = 学术引文核验员四分类指令，
user = `【引用句】…\n【证据片段】…`，assistant = `{"label": "<label>"}`；
见 `scripts/train_support_lora.py` 的 `build_prompt` / `encode`。

## 5. 复现命令

```bash
# 1) 构造 a3 扩样池（首次需要网络；缓存已随仓库提交，可 --offline 纯离线复现）
PYTHONPATH=src python scripts/build_sft_expand.py            # 首次
PYTHONPATH=src python scripts/build_sft_expand.py --offline  # 缓存复现

# 2) 组装三份 SFT jsonl + 本 README（断言 id/来源不重叠）
python scripts/build_support_sft.py --out data/sft

# 3) 独立审计（含 5 条来源的 OpenAlex 在线核验，加 --no-network 可跳过）
python scripts/verify_sft_splits.py --verify-openalex 5
```

## 6. 训练 / 评测入口

```bash
# 训练（--model-size 支持 1.7b / 4b / 8b / 14b，A3 目标是 4b）
python scripts/train_support_lora.py --model-size 4b --data data/sft --out out/support_lora_qwen3_4b

# 无 GPU 先验证数据与模型解析（不 import torch）
python scripts/train_support_lora.py --model-size 4b --dry-run

# 同口径评测（产品同款 prompt，经 OpenAI 兼容端点；--split 可选 test/dev）
python scripts/eval_support_adapter.py --model-size 4b --data data/sft --split test \
    --out out/support_adapter_eval_4b.json
```

两个脚本都把 `model_size` 写进 `run_meta.json` / 结果 JSON；本地权重放在
`models/Qwen3-4B` 时训练脚本自动优先用它，否则回退到 `Qwen/Qwen3-4B`。

实际指标记录在 `data/experiments/`，本数据卡不预填任何结果。

## 7. 文件清单

| 文件 | 大小 | sha256 |
| --- | ---: | --- |
| `support_train.jsonl` | 284,236 B | `19f4eaae682a61a6d203b812fd54e0f652bdbc252521830f6055f877dfae47e7` |
| `support_dev.jsonl` | 8,499 B | `a3ea2edb72fd98b8aea0b477c5131de9186b5a1c10823cbd76c8a61857a16bbb` |
| `support_test.jsonl` | 28,826 B | `9f474199142fd4595b21f2b3176dc05d464a171522623b5904d1d6074ed2564e` |

## 8. 已知限制

- 构造标签只保证"规则一致"，不保证与人类判断一致；`partial` 与 `no_evidence` 的边界尤其依赖构造启发式；
- OpenAlex 中文摘要中相当一部分是机器翻译，句式可能不自然（构造时已按 CJK 比例 / 句长过滤）；
- a3 与 base 的论文来源不同，但学科分布由 OpenAlex 默认相关性排序决定，未做人工分层；
- dev 仅 20 条（沿用历史口径），只用于训练期监控；对外报数请以 test 60 条为准。

## 9. 许可

- 本数据卡与 SFT jsonl：CC-BY-4.0；
- 上游 OpenAlex 元数据：CC0 1.0；片段缓存每篇最多 2 句，不重新分发摘要全文。
