# CiteMap 人工核对（CSV）

CiteMap 的机器抽取结果已在 105 格上完成三人人工核对，结果见 `citemap_audit_result.md`。`verification=false` 和界面上的
“机器证据”标签都表示：证据来自摘要的机器抽取，尚未由人逐格确认。

这份文档说明如何用 CSV 完成 CiteMap 核对：**默认 60 格分层抽样**，冲国一建议直接做 **105 格全量**。
以及如何计算一致率、κ 和证据精确率。

## 1. 生成核对包

```bash
python scripts/build_citemap_audit_csv.py --out dist/citemap_audit
```

输出：

| 文件 | 给谁 | 内容 |
| --- | --- | --- |
| `reviewer_A.csv` / `B` / `C` | 核对人 | 同一批格子（60 格抽样或 105 格全量，由 `--grid` 决定），三种独立随机顺序；每行带论文摘要和机器证据句 |
| `full_grid_105_optional.csv` | 可选 | 两主题 × 15 篇 × 各主题断言数 = 105 格全量网格 |
| `_organizer_only_key.csv` | 组织者 | 机器证据、置信度、抽样标记；**不要发给核对人** |
| `adjudication_sheet.csv` | 组织者 | 两人不一致时的仲裁模板 |
| `README_核对说明.md` | 所有人 | 逐列填写说明 |

60 格是分层抽样（每主题 30 格），不是全量。抽样协议由
`scripts/build_citemap_verification.py` 固定 seed 生成。

## 2. 核对人怎么判

每人只打开自己那份 CSV，独立填写：

- `verify_verdict`：`正确` / `有问题` / `跳过`
- `issue_type`：仅“有问题”时填，取值见 README
- `verify_note`：有问题或跳过的原因
- `reviewer_confidence_1_5`（可选）

机器证据格必须满足：引用句在摘要中逐字可查、对得上断言、立场与
方法/样本无明显错误。无机器证据格要判断摘要里是否其实存在相关证据。

**建议 3 人独立核对全部格子**：可算 Fleiss κ、多数票，分歧再仲裁；最低是 2 人独立 + 第 3 人仲裁；只有 1 人时只能写“单人核对”，不能宣称一致性。

## 3. 回收后评分

```bash
python scripts/score_citemap_csv.py \
  --key dist/citemap_audit/_organizer_only_key.csv \
  --reviewer dist/citemap_audit/reviewer_A.csv \
  --reviewer dist/citemap_audit/reviewer_B.csv \
  --out dist/citemap_audit/_results
```

输出：

- `agreement.json`：一致率、Cohen's κ（两人）/ Fleiss κ（三人）、多数票准确率、
  机器证据精确率、无证据误报率、Wilson 95% CI、仲裁数；
- `merged.csv`：逐格多数票；
- `adjudication.csv`：仅两人判断不一致的格，供仲裁后回填。

## 4. 边界

- 60 格是抽样，不能写成“30 篇论文全部已验证”。
- 机器抽取只读摘要，不读全文/结果页；人工判“正确”也只证明摘要级抽取正确。
- 未完成核对前，`data/evidence_map/verification_state.json` 的 `checked` 必须为 0。
- CSV 里不包含人工答案；评分脚本也不会把机器标签当人工标签。
