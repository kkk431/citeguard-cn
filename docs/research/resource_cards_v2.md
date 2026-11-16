# 资源卡 v2：能落到 CiteGuard 的可测提升候选（第一轮短名单）

> 本轮只交 6 条短名单 + 3 个 smoke 设计/结果，每条 ≤8 行；六项门槛的完整卡等队长验收后再补。所有状态按实际：跑通写数字，没跑通写阻断原因。

## 0. 短名单（6 条）

### C1 MiniCheck（句对事实核验）
- 论文/项目：arXiv:2404.10774（EMNLP 2024）https://arxiv.org/abs/2404.10774 ；官方 repo https://github.com/Liyan06/MiniCheck （main，2026-11-16 拉取 zip 1,566,723 B）
- 许可/官方实现：代码 Apache-2.0（GitHub API）；权重卡 MIT（https://hf-mirror.com/lytang/MiniCheck-DeBERTa-v3-Large ）；代码与权重均公开
- 接入点：`src/citeguard/support.py` 的 `judge_support` 之前，先做本地句对核验/预筛，减少 API 调用
- 预期增益：ClaimSupport-CN 100 条 macro-F1 基线 0.9597（v10 judge）→ 目标 ≥0.90 且单对 <1 s（CPU）；<0.85 或 >2 s/对即 kill
- 验证：`data/claimsupport_cn/v1_100.jsonl` 取 test60 + partial 40，跑 pred/prob 与 macro-F1；命令与脚本随完整卡提交
- 状态：**blocked（未产出 pred/prob）**——权重 pytorch_model.bin 1,740,386,738 B 已缓存，但 hf-mirror 大文件约 1 MB/s，本地加载两次均 >10 min 未完成；未得到分数

### C2 AlignScore（句对对齐/NLI 打分）
- 论文/项目：arXiv:2305.16739（ACL 2023）https://arxiv.org/abs/2305.16739 ；官方 repo https://github.com/yuh-zha/AlignScore （main）；checkpoint AlignScore-base.ckpt 1,966,965,771 B
- 许可/官方实现：MIT（仓库 LICENSE + 权重卡）；代码、权重公开
- 接入点：`src/citeguard/support.py` 给 judge 结果加可校准的对齐分，复核 partial/support
- 预期增益：把 judge 判 partial 的“弱证据”与“无证据”分开；目标 partial→no_evidence 误判 −2 pt（基线见 judge on/off：no_evidence 25→12）
- 验证：ClaimSupport-CN 100 条（judge 关闭，用规则+AlignScore 复判）；命令 `python -c "from alignscore import AlignScore ..."`，CPU 每对约 0.5 s
- 状态：**smoke 通过**——加载 7.2 s，0.49 s/对；en 支持 0.9983 / en 矛盾 0.0004 / zh 支持 0.743（中文为跨语言代理，不作正式结论）

### C3 multilingual-e5-small（多语检索 embedding）
- 论文/项目：arXiv:2212.03533（E5）https://arxiv.org/abs/2212.03533 ；模型 https://hf-mirror.com/intfloat/multilingual-e5-small （118M）
- 许可/官方实现：MIT（HF 模型卡）；权重公开；无官方 repo（模型卡即入口）
- 接入点：`src/citeguard/embeddings.py` + `scripts/eval_replacement.py`，替换/补充 BGE-M3 的候选召回
- 预期增益：replacement 438 查询/477 候选，R@3 0.3219（BGE-M3）→ 目标 ≥0.34；低于 0.32 即 kill
- 验证：`data/experiments/replacement_eval_dataset.json` 全量，R@1/R@3/R@5/MRR，编码 4.8 s
- 状态：**smoke 触发 kill**——带 query:/passage: 前缀 R@1 0.1438 / R@3 0.2009 / R@5 0.2694 / MRR 0.2019；低于 BM25 0.2580，不作为候选

### C4 Docling（PDF 版式/参考文献解析）
- 论文/项目：arXiv:2408.09869 https://arxiv.org/abs/2408.09869 ；官方 repo https://github.com/docling-project/docling （PyPI 2.150.1，模型 docling-layout-heron 171,658,996 B）
- 许可/官方实现：MIT（GitHub API）；代码、模型公开
- 接入点：`src/citeguard/pdf_extract.py` 的正文/参考文献块解析（离线批处理，不进交互路径）
- 预期增益：22 篇 real_corpus 当前 543 条引用、键自洽 89.5% → 目标引用条数不减、自洽率 ≥90%、中文不乱码；耗时 >300 s/篇即降为离线选项
- 验证：`data/real_corpus/hanspub_152574.pdf` 等 3 篇，比较“参考文献”块与 [n] 条目数；命令 `DocumentConverter().convert(path)` 
- 状态：**smoke 通过**——552,528 B PDF 转换 107.5 s，输出 10,317 字符 markdown，中文标题/正文正确；远慢于现有 pypdf（<1 s），只能离线用

### C5 MinerU（中文版面/公式/表格解析）
- 论文/项目：arXiv:2409.18839 https://arxiv.org/abs/2409.18839 ；官方 repo https://github.com/opendatalab/MinerU （PyPI mineru 4.2.2，requires_python <3.15,>=3.11）
- 许可/官方实现：Apache-2.0 + 附加条款（LICENSE：MAU 1 亿/月营收 2,000 万美元为商用阈值）；代码公开，模型需另下
- 接入点：`src/citeguard/pdf_extract.py` 的中文备选解析器（与 Docling 二选一）
- 预期增益：3 篇中文 PDF 的参考文献块完整性 ≥ 当前管线；低于当前即 kill
- 验证：同 C4 的 3 篇 PDF，比对 [n] 条目与正文段落完整性；安装与模型下载预计 20–40 min
- 状态：**blocked（未试装）**——Docker daemon 未运行（npipe dockerDesktopLinuxEngine 不存在）、模型体积大、本机无 GPU；未伪造结果

### C6 ContextCite（上下文归因/span 定位）
- 论文/项目：arXiv:2409.00729（NeurIPS 2024）https://arxiv.org/abs/2409.00729 ；官方 repo https://github.com/MadryLab/context-cite （PyPI context-cite 0.0.4）
- 许可/官方实现：MIT（GitHub API）；代码公开；需自备底座 LLM
- 接入点：`src/citeguard/evidence_map.py` / `live_check.py`，把 claim 支持定位到候选摘要的具体 span
- 预期增益：Live held-out 30 句 evidence_available 11/30 → 目标 ≥18/30，且证据可逐字回查
- 验证：`data/live_eval/claims_holdout.jsonl` 抽 10 句，绑定同一底座模型跑 num_ablations=64，统计 span 命中与耗时
- 状态：**blocked（未产出 span）**——包可导入，但初始化触发 nltk punkt_tab 下载失败（WinError 10060），且需 HF 底座 LLM（本机无 GPU、大模型下载慢）

## 1. 三个 smoke 设计（命令 / 数据 / 判据 / 结果）

### S1 AlignScore NLI smoke（已执行，PASS）
- 命令：加载 `D:/Temp/citeguard_e3/AlignScore-base.ckpt`，`BERTAlignModel.load_state_dict` + `Inferencer.inference(['premise'],['hypo'])`，取 tri 头第 0 列
- 数据：3 对锚点（Eiffel 支持、Eiffel 矛盾、中文支持）
- 判据：en 支持 ≥0.90、en 矛盾 ≤0.10、中文 ≥0.50、≤1 s/对；任一不满足记失败
- 结果：0.9983 / 0.0004 / 0.743，0.49 s/对；加载 7.2 s —— PASS
- 备注：transformers 4.57 已移除 `AdamW`（需 patch），PL 2.6 不允许实例调用 `load_from_checkpoint`（改为手动 state_dict）；`en_core_web_sm` 未装，走 nli 头绕开 spacy

### S2 Docling 中文 PDF smoke（已执行，PASS）
- 命令：`python -c "from docling.document_converter import DocumentConverter; d=DocumentConverter().convert('data/real_corpus/hanspub_152574.pdf'); open('out.md','w',encoding='utf-8').write(d.document.export_to_markdown())"`
- 数据：`data/real_corpus/hanspub_152574.pdf`（552,528 B）
- 判据：输出含中文标题/摘要、含“参考文献”块、无乱码、<300 s/篇
- 结果：107.5 s，10,317 字符，中文正确，参考文献块存在 —— PASS（但延迟只适合离线）

### S3 multilingual-e5-small 重排 smoke（已执行，KILL）
- 命令：`python scripts/eval_replacement.py --methods e5`（临时实现读 `data/experiments/replacement_eval_dataset.json`，query:/passage: 前缀，仅 title 作文档，与 bge 口径一致）
- 数据：438 查询 / 477 候选
- 判据：R@3 ≥0.3219（BGE-M3 基线）才保留；低于 0.32 即 kill
- 结果：R@3 0.2009（R@1 0.1438 / R@5 0.2694 / MRR 0.2019）—— KILL，已从短名单移除

## 2. 三张完整卡

### C2 AlignScore（smoke 通过；中文 100 条评测 KILL）
- **论文/项目**：AlignScore: Evaluating Factual Consistency with a Unified Alignment Function，arXiv:2305.16739（ACL 2023），https://arxiv.org/abs/2305.16739 ；repo https://github.com/yuh-zha/AlignScore （main，2026-11-16；无 PyPI 包）；权重 AlignScore-base.ckpt 1,966,965,771 B。
- **官方实现/许可证**：代码与权重均公开；MIT（repo LICENSE + HF 权重卡 https://hf-mirror.com/yzha/AlignScore ）。
- **接入点**：`src/citeguard/support.py`——在 judge 判 partial/support 时增加 AlignScore 对齐分（NLI 头），用于复核“弱证据/无证据”边界；judge 不可用时作为本地降级分。
- **基线→目标**：ClaimSupport-CN 100 条（support 40 / partial 25 / contradict 15 / no_evidence 20）当前 v10 judge macro-F1 0.9597；judge 关闭时 no_evidence 25 条（t20 M04）。目标：partial→no_evidence 误判 −2 pt，且 judge 关闭时 macro-F1 ≥0.85；单对 >1 s 或中文分离度 <0.5 即 kill。
- **验证方案**：取 100 条逐对跑（claim, 最佳证据），比对 judge 标签；命令见 §1 S1（手动 `state_dict` 加载，绕 PL 2.6 实例调用限制）；30 对先跑约 15 s + 加载 7 s，100 条约 50 s。
- **风险/kill**：transformers 4.57 已移除 `AdamW`（需 `transformers.AdamW=torch.optim.AdamW`）；PL 2.6 不允许 `BERTAlignModel(...).load_from_checkpoint`，需手动加载；默认模式要 `en_core_web_sm`（本机未装，走 nli 头）；英文训练，中文仅跨语言代理（0.743/对），中文结论只作参考。
- **中文 100 条人工多数票评测（KILL）**：n=100（support 41 / partial 26 / contradict 17 / no_evidence 16）。平均 entailment 分：support **0.8110**、partial **0.9710**、contradict **0.9650**、no_evidence **0.6040**。contradict 与 partial 同级且高于 support，中文矛盾被当成支持 → 不能用于中文复核/降级；没有接入产品。
  - 证据：`data/experiments/alignscore_cn100.json`；复现：`python scripts/eval_alignscore_cn100.py --ckpt D:/Temp/citeguard_e3/AlignScore-base.ckpt`。
  - 结论：英文 smoke 的 0.9983/0.0004 是英文能力，不迁移中文；AlignScore 只保留为英文对照，不进中文产品。

### C1 MiniCheck（加载受阻；按阻断记录，不重试）
- **论文/项目**：MiniCheck: Efficient Fact-Checking of LLMs on Grounding Documents，arXiv:2404.10774（EMNLP 2024），https://arxiv.org/abs/2404.10774 ；repo https://github.com/Liyan06/MiniCheck （main，zip 1,566,723 B）；权重 https://hf-mirror.com/lytang/MiniCheck-DeBERTa-v3-Large 。
- **官方实现/许可证**：代码 Apache-2.0（GitHub API）；权重卡 MIT；代码、权重公开。注意 PyPI `minicheck` 是同名无关包（形式化验证），必须从 repo 装。
- **接入点**：`src/citeguard/support.py` 的 `judge_support` 前置本地句对核验/预筛，减少 API 调用。
- **基线→目标**：ClaimSupport-CN 100 条 macro-F1 0.9597（v10 judge）；目标 ≥0.90 且单对 <1 s（CPU）；<0.85 或 >2 s/对即 kill。
- **验证方案**：`data/claimsupport_cn/v1_100.jsonl` 的 test60 + partial 40，`MiniCheck(model_name='deberta-v3-large', cache_dir=...)` 输出 pred/prob 后算 macro-F1；预计加载 20–60 s、100 对 <2 min（若可加载）。
- **阻断记录（不是结果）**：权重 `pytorch_model.bin` 1,740,386,738 B 已缓存，但两次本地加载均 >10 min 未完成（hf-mirror 大文件约 1 MB/s）；未产出 pred/prob，不写分数。风险：DeBERTa-large 1.7 GB、纯英文训练、本机无 GPU。

### C4 Docling（smoke 通过；只离线、不进产品）
- **论文/项目**：Docling Technical Report，arXiv:2408.09869，https://arxiv.org/abs/2408.09869 ；repo https://github.com/docling-project/docling （PyPI 2.150.1）；布局模型 docling-layout-heron 171,658,996 B。
- **官方实现/许可证**：代码与模型公开；MIT（GitHub API）。
- **接入点**：`src/citeguard/pdf_extract.py` 的离线批处理分支（仅用于 real_corpus/批量入库），不进入 Live/请求内解析路径。
- **基线→目标**：22 篇 real_corpus 当前 543 条引用、键自洽 89.5%；目标引用条数 ≥543、自洽率 ≥90%、中文无乱码；单篇 >300 s 或引用条数下降即 kill。
- **验证方案**：3 篇中文 PDF（含 `data/real_corpus/hanspub_152574.pdf`，552,528 B），比较 Docling markdown 与 pypdf 文本的“参考文献”块与 `[n]` 条目数；命令 `DocumentConverter().convert(path).document.export_to_markdown()`；实测 107.5 s/篇、10,317 字符。
- **风险/kill**：107.5 s/篇（pypdf <1 s），只适合离线；模型 172 MB 需预下；OCR 语种未验证；不进产品交互路径（队长已确认）。

## 3. 拒绝卡与参考列表

### 3.1 拒绝卡（不采用）
- **C3 multilingual-e5-small（拒绝）**：MIT、118M、权重公开；smoke 在 replacement 438 查询/477 候选（title-only，与 bge 口径一致）R@3 0.2009，低于 BM25 0.2580 与 BGE-M3 0.3219，触发 kill；非许可证问题，是检索质量不匹配。
- **C5 MinerU（受阻/不选）**：PyPI 4.2.2，Apache-2.0 + 附加条款（MAU 1 亿/月营收 2,000 万美元商用阈值）；本机 Docker daemon 未运行、模型体积大、无 GPU，未试装即停；不占完整卡。
- **C6 ContextCite（受阻/不选）**：MIT、PyPI 0.0.4；安装/导入成功，但初始化触发 nltk punkt_tab 下载失败（WinError 10060），且需自备底座 LLM（本机无 GPU、大模型下载慢）；未产出 span，不占完整卡。

### 3.2 参考列表（逐条一句话）
- **SummaC**：Apache-2.0、英文 NLI 聚合指标；依赖 `huggingface-hub<=0.17.0` 与当前 transformers 4.57.6 冲突，装不上，只作指标参考。
- **TRUE**：NAACL 2022 事实一致性基准，许可证未验证、英文，只作评测参考。
- **RAGTruth**：MIT，约 18,000 条词级幻觉标注、英文，可做英文幻觉评测参考，不接中文产品。
- **ALCE**：MIT，英文带引用生成评测（ASQA/QAMPARI/ELI5），可借鉴 citation precision/recall 口径，不直接用数据。
- **AttributionBench**：GitHub license=None（许可不明），拒绝使用。
- **GROBID**：Apache-2.0，PDF 引文解析成熟，但模型以英文/欧语为主、无中文模型，中文场景仅参考。
- **CERMINE**：仓库 Cermine/CERMINE 返回 404、许可未验证，不纳入。

## 4. 文件与复现

- 本文件：`docs/research/resource_cards_v2.md`；结构化数据：`data/experiments/resource_cards_v2.json`。
- 环境：Python 3.13.14，CPU AMD Ryzen 7 8845H 8C/16T，RAM 27.8 GiB，无 GPU；transformers 4.57.6、huggingface-hub 0.36.2、datasets 3.6.0、sentence-transformers 3.4.1、docling 2.150.1、context-cite 0.0.4。
- 模型缓存：AlignScore ckpt `D:\Temp\citeguard_e3\AlignScore-base.ckpt`；Docling 模型在 `C:\Users\hejiaxuan\.cache\huggingface\hub\models--docling-project--docling-layout-heron`；MiniCheck 缓存在 `D:\Temp\citeguard_e3\ckpts`（权重已下、加载未完成）。
- 复现：S1/S2/S3 的命令与判据见 §1；本轮未改产品代码。
