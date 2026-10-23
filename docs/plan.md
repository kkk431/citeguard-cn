# 路线与状态（产品视角）

> 本文件只记录**产品与工程质量**的现状、已知边界和下一步；不涉及任何比赛/材料工作。
> 评测数字的出处：`docs/real_data_eval.md`（真实论文语料）、`docs/support_summary.md`（支持度）、
> `docs/experiments.md`（E4/E5/E7 补充实验）、`data/citebench_cn/README.md`（真实性基准数据卡）。

## 1. 现在能做什么（已上线，均有测试/实测）

| 能力 | 状态 | 证据 |
|---|---|---|
| 输入解析：PDF（文字层）、Word .docx（含表格参考文献）、TXT/MD、GBK 文本 | ✅ | 真实语料解析干净率 99.6%/99.2%（`scripts/eval_parse_real.py`） |
| 扫描件 PDF 自动 OCR（可选依赖 rapidocr） | ✅ 可选 | `src/citeguard/ocr.py`，`tests/test_ocr.py` |
| 中文引文解析（GB/T 编号制 + APA 作者-年份） | ✅ | `tests/test_parser_styles.py`、`tests/test_docx_input.py` |
| 引文真实性核验：OpenAlex/Crossref/arXiv + DOI 全系统校验 | ✅ | 真实已发表文献误判「虚构」0/224；中国 DOI 落地页可补非 Crossref 注册 DOI |
| 本地题录库（RIS/EndNote/BibTeX/CSL-JSON/纯文本）优先核验 | ✅ | 中文文献确定结论率 55% → 100%（库内命中，`scripts/eval_library_real.py`） |
| GB/T 7714-2025 字段检查（必填/建议字段、类型码、作者数、DOI 格式、年份/页码、文档级序号与连接号一致性） | ✅ | E4：类型码 100%、必填字段 98.4%、构造漂移严格检出 **29/30（96.7%）** |
| 引用支持度判定（LLM judge，可插拔、可选，两段式覆盖审计） | ✅ 可选 | ClaimSupport-CN macro-F1 **0.9328** / acc 0.930（单段 v3 为 0.9005） |
| 报告与导出（HTML/MD/JSON/CSV，一键生成规范条目、复制建议、打印） | ✅ | `tests/test_web.py`、`tests/test_hardening.py` |
| 批量：网页多文件上传（含汇总面板/汇总 CSV）、CLI 目录批处理 | ✅ | `web/static/js/index.js`、`tests/test_cli.py` |
| 工程：Docker、CI、部署文档、247 个离线测试 | ✅ | `docker/`、`.github/workflows/ci.yml`、`docs/deployment.md` |

## 2. 已知边界（不要对外说成"能"）

1. **中文文献的在线覆盖率**：无本地库时约 45% 的中文参考文献只能给「未找到匹配」（不是造假）。这是国际开放元数据对中文期刊覆盖不足，不是匹配算法问题（检索召回实测 92%）。解决路径：导入本地题录库（已实现），或获得中文数据源授权（未做）。
2. **支持度判定依赖外部 LLM API**：无 key 时全部「未检测」；只判有摘要的条目（默认前 30 条，可调）；两段式审计后 partial↔support 仍有 4 条混淆。
3. **格式规则边界**：页码 ASCII 连字符只给 info 提示（标准原文的一字线规定请以官方为准）、卷/期为小数字时无法判断互换；扫描件 OCR 可能丢类型码（已做「类型码丢失」标记，不臆造）。
4. **无真实用户测试**：目前只有内部可用性自测（E7），没有外部受试者、没有 SUS；测试包见 `docs/user_test_kit.md`。

## 3. 下一步（按优先级）

1. **题录库体验**（P0）：支持知网/NoteExpress 更多导出变体；题库导出为 BibTeX；批量导入文件夹；摘要补全（`scripts/enrich_library_abstracts.py` 已实现）。
2. **格式规则扩展**（P1）：页码连接号/卷期一致性规则已加（info 提示 / 启发式 warning），仍需核实标准原文并给规则依据打标；把「规则依据/是否已核原文」写进每条 issue，避免过度断言。
3. **OCR 质量**（P1）：类型码与标点的 OCR 后处理（`[J]`→`[]` 修复候选）、按页限流与进度提示。
4. **核验准确率**（P2）：作者中英文混写归一化、机构作者过滤；本地库比对的题名相似度阈值调参（当前 0.90/0.78）。
5. **性能**（P2）：同一文献去重后再查询、请求合并；大 PDF 分页进度。
6. **真实用户测试**（P3，需要人）：`docs/user_test_kit.md` 已备好任务脚本、指标、SUS 问卷与结果模板，招募 3–5 名真实用户即可产出可用性报告。

## 4. 复现/自检命令

```bash
pip install -r requirements.lock.txt
PYTHONPATH=src python -m pytest tests -q                 # 247 项离线测试
PYTHONPATH=src python scripts/verify_artifacts.py        # 数据集/结果一致性（32 项）
PYTHONPATH=src python scripts/eval_parse_real.py         # 真实论文解析实测（需先抓语料）
PYTHONPATH=src python scripts/eval_verify_real.py        # 真实文献核验误报实测
PYTHONPATH=src python scripts/eval_library_real.py       # 本地题录库覆盖率实测
PYTHONPATH=src python scripts/e4_format_check.py         # 格式规则回归（E4）
PYTHONPATH=src python scripts/evaluate_support.py        # 支持度评测（两段式）
```
