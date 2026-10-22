# CiteBench-CN 工作流规划与交付状态

> 本文只覆盖 **评测/基准（benchmark）工作包**，并汇总与其他工作包的接口缺口。团队总规划见 `D:\ai+ky\参赛包装方案_引证卫士.md`（评分表逐项证据、PPT/视频脚本、风险预案）；各调研线产物在 `D:\ai+ky\research\`。

## 1. 工作包定位

- 目标：为「引证卫士 CiteGuard-CN」提供**可复现的中文引文核验评测基准 + 评测脚本 + 对照基线**，支撑评分表「实现完成度与可验证效果 25」「开放成果与复用价值 15」。
- 范围：`scripts/`（构建/评测/基线/校验脚本）、`data/citebench_cn/`（数据集与结果）、`docs/`（数据卡/一页纸/本规划）。
- 不在范围：`src/citeguard/`（v1.1 核验器，由 Lead 维护）、`web/`、项目级材料与 PPT。

## 2. 交付状态（已验收）

| 交付物 | 状态 | 证据 |
|---|---|---|
| CiteBench-CN v3 数据集 | ✅ | `data/citebench_cn/citebench_cn.jsonl`，250 条=100/75/75，SHA-256 `1a8e466b…`（LF 统一换行），seed 20261022，本地/服务器重建字节一致 |
| 数据卡（口径/构造/许可/复现） | ✅ | `data/citebench_cn/README.md` |
| 评测脚本（macro-F1/accuracy/per-class/混淆/消融/CSV） | ✅ | `scripts/evaluate_citebench.py`，`results.json` |
| DeepSeek 公平基线（固定 prompt v3） | ✅ | `scripts/deepseek_baseline.py`，`deepseek_results.json`（`prompt_sha256=e2637ac0…`） |
| 一键复现（benchmark 段） | ✅ | `scripts/reproduce_citebench.sh` |
| 产物一致性校验 | ✅ | `scripts/verify_artifacts.py`（本地 + `/api/benchmark` 契约） |
| 服务器实跑与页面 | ✅ | `/api/benchmark` available:true、`/benchmark` 200、本地/服务器 md5 一致 |
| ClaimSupport-CN 支持度基准（100 条） | ✅ | `data/claimsupport_cn/`（40/25/15/20 构造标签，SHA `4820014a…`）+ `scripts/evaluate_support.py` + `docs/support_summary.md` |

**实测指标**：v1.1 macro-F1 **0.9684** / accuracy **0.968**；混淆矩阵 `[[100,0,0],[8,67,0],[0,0,75]]`；per-class Exact .926/1.000/.962、Minor 1.000/.893/.944、Major 1.000/1.000/1.000；消融 full 0.9684、-DOI anchor 0.8071（-0.1613）、-title search 0.7744（-0.1940）；DeepSeek zero-shot 0.5159/0.536。

## 3. 已自主完成的加固项

1. `scripts/verify_artifacts.py`：一条命令校验数据集 SHA、标签构成、results/per-class/混淆/消融自洽、DeepSeek 数据集一致性与 live `/api/benchmark` 契约；失败返回非 0，可直接进验收/CI。
2. `scripts/reproduce_citebench.sh`：build → evaluate → verify →（可选）DeepSeek，自动识别本地 `src/` 与服务器 `.pylibs/` 两种环境。
3. 数据卡与一页纸已按团队口径回填**真实测量值**（此前包装方案中的 `0.8x` 为占位）。
4. **跨环境复现修复**：发现 Windows 构建写 CRLF、Linux 写 LF 导致同 seed 的 JSONL 在不同机器 SHA 不同（且 build 曾依赖 rapidfuzz 版本）；已改为统一 LF + 纯 Python 相似度过滤，本地/服务器重建 SHA 一致，并在数据卡中记录。

## 4. 与团队总规划的接口缺口（需 Lead 拍板/其他线执行，不阻塞本工作包）

| # | 缺口 | 建议动作 | 责任 |
|---|---|---|---|
| 1 | 包装方案指标仍是占位：`0.8x`（第 51/214 行） | 回填 `macro-F1 0.9684 / accuracy 0.968`；支持度 F1 待 ClaimSupport-CN | Lead |
| 2 | **表述风险**：包装方案第 135 行写「双人标注 + κ」，与事实不符（本集标签由构造决定，无人工双标、无 κ） | 改为「程序化构造 + 回解析自检 0 失败；标签由构造决定」，避免答辩被追问无法举证 | Lead（高优先级） |
| 3 | 项目级 `reproduce.sh`、顶层 README / NOTICE / THIRD_PARTY_NOTICES / LICENSE | 开源成果 15 分需要；可用本工作包脚本作为 benchmark 段 | Lead + 全队 |
| 4 | ~~ClaimSupport-CN 100 条（支持度四分类）~~ **✅ 已交付** | 100 条（support 40 / partial 25 / contradict 15 / no_evidence 20），judge macro-F1 0.7951 / accuracy 0.810；数据卡明确「构造标签、无人工双标、无 κ」 | 已完成 |
| 5 | E3 英文方法验证、E4 格式合规、E5 检索、E7 用户实测 | 各自脚本/材料 | 其他线 |
| 6 | 上游 PR/Issue 证据 | 选 1 个 good-first-issue 实际提交 | Lead 指派 |

## 5. 验收命令（本工作包）

```bash
# 本地
PYTHONPATH=src python3 scripts/verify_artifacts.py
# 服务器（含 live API 契约）
cd /data/xyjiang/aic_mental/citeguard
PYTHONPATH=.pylibs:. python3 scripts/verify_artifacts.py --api-base http://127.0.0.1:8000
# 全链路复现（含可选 DeepSeek）
DEEPSEEK_API_KEY=... bash scripts/reproduce_citebench.sh
```

## 6. 风险

- OpenAlex 免费额度有限（约 1000 次/日/IP）；评测已用 `data/citebench_cn/cache/` 缓存，复跑基本不再发请求。
- 中文元数据存在作者中英双写/机构作者噪声，作者顺序扰动的可检出率有限（见数据卡「已知局限」）。
- 数据集为工程回归集（250 条），答辩中应表述为「可复现的工程基准」，不做学科结论性外推。
