# ClaimSupport-CN 数据集卡（v2026-11-11）

## 一句话

**ClaimSupport-CN** 是 CiteGuard-CN 自建的中文引文支持度评测集：每条样本给出一句中文 claim 与一段被引论文摘要片段（evidence），要求判定 `support / partial / contradict / no_evidence` 四分类。

> 标签由**构造规则唯一决定**，不是人工标注，也没有双人标注或 κ。请把它当作“可复现的构造评测集”，不要当作人工金标。

## 规模与构成

| 批次 | 条数 | 说明 |
|---|---|---|
| v1 | 100 | 首发集（2026-10-22），40/25/15/20 |
| ext | 60 | 扩展集，24/15/12/9，来源 work 与 v1 不重叠 |
| v2 | 140 | 补足长尾，54/40/24/22，来源 work 与 v1/ext 不重叠 |
| **合计** | **300** | support 120 / partial 80 / contradict 51 / no_evidence 49 |

- JSONL：`claimsupport_cn_300.jsonl`（UTF-8，LF，每行一条）
- SHA-256：`a180261d21f63ec79c05d3996c8ec1653d57c1a33e6aad0f79f43edf7d2979ba`
- 统计：`claimsupport_cn_300.stats.json`
- 重建命令：`python scripts/export_dataset_release.py`

## 构造方法（标签怎么来的）

1. 从 OpenAlex 取 `language:zh, has_abstract:true, type:article` 的论文元数据与摘要（CC0 1.0），只保留 1–5 句的句子片段，不保存完整摘要。
2. 按规则构造：
   - `support`：claim 是摘要中的核心句，evidence 是包含该句的片段；
   - `partial`：claim 是完整句，evidence 只含主要论断的一个从句；
   - `contradict`：把原句中的一处论断换成反义词（提高↔降低、正相关↔负相关等），evidence 用原句；
   - `no_evidence`：claim 来自论文 B，evidence 来自主题无关的论文 A（标题与 CJK bigram 重叠都低于阈值）。
3. 每条重新执行规则自检；v1 另有 20 条（20%）的规则复核（`claimsupport_cn.spot_check.json`），仍是**单标注者规则复核**，不是人工语义标注。
4. 各批次来源 work 互不重叠（`export_dataset_release.py` 会硬校验，失败直接报错）。

## 已知局限

- 部分中文摘要来自 OpenAlex 的机器翻译文本，语言自然度不代表真实中文写作分布。
- 构造保证“逻辑关系”，但不保证自然引用场景的分布；真实论文里的引用支持度更难。
- **没有人工标注**；仓库里的 `human_review_40.csv` 是空白复核模板（`your_label` 未填），不能当人审结果。
- 标签不完全均衡（support 40%，no_evidence 16.3%）。
- 只覆盖中文题录；跨语言引用未覆盖。

## 评测口径（按批次分别报，不混成一个数）

用产品同款两段式 judge（Qwen/DeepSeek 均可，temperature 0，prompt v10 + 覆盖审计）在同一份 JSONL 上跑：

| 批次 | 条数 | macro-F1 | accuracy | 备注 |
|---|---|---|---|---|
| v1 | 100 | 0.9597 | 0.9500 | 主口径 |
| v2 | 140 | 0.977 | 0.979 | 构造集，难度不同于真实语料 |
| ext | 60 | 0.9866 | 0.9833 | 构造集，仅 1 条 support→partial |

这些数字只说明“在该构造集上的判定能力”，不能外推为真实用户场景的准确率。

## 许可与引用

- 数据集与标注：**CC BY 4.0**（引用时请注明 CiteGuard-CN / AIC-2026-67377639）。
- 上游元数据：OpenAlex，CC0 1.0；evidence 仅为句子片段，不 re-host 全文或完整摘要。
- 若使用请引用：`CiteGuard-CN ClaimSupport-CN v2026-11-11, https://github.com/kkk431/citeguard-cn`。
