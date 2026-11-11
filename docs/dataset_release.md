# ClaimSupport-CN-300 发布包

- 文件：`dist/CiteGuard-CN_ClaimSupport-CN-300_v1.0.zip`
- 大小：75,128 B
- 内容：300 条构造集（`claimsupport_cn_300.jsonl`）、统计、DATASET_CARD、README、MANIFEST（逐文件 sha256）
- 许可证：CC-BY-4.0；来源句子来自 OpenAlex 摘要（CC0），不重新分发全文

## 标签边界

标签由构造规则唯一决定（support / partial / contradict / no_evidence），
**不是人工语义标注**；`human_review_40.csv` 是空白模板，不能当人审证据。

## 上传步骤（待 token）

HuggingFace：
```bash
huggingface-cli login
huggingface-cli upload kkk431/claimsupport-cn-300 dist/CiteGuard-CN_ClaimSupport-CN-300_v1.0.zip --repo-type dataset
```

Zenodo（可选）：新建 deposition → 上传同一 zip → 填 DATASET_CARD 元数据 → DOI。
