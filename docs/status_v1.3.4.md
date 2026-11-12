# v1.3.4 状态总表

一页看清：现在有什么、数字是多少、哪些还没做。所有数字来自仓库内 JSON/脚本，均可复跑；
构造集与人工标注严格区分，未做的项直接写「未做」。

## 1. 旗舰能力（第二轮计划）

| 能力 | 状态 | 入口 | 已验证的数字 / 证据 |
| --- | --- | --- | --- |
| F1 引用健康画像 | ✅ | 报告页「总览」 | 21 篇真实论文平均 **76.1**；单篇 95.9 A；脚本 `scripts/eval_health_real.py`，`data/experiments/health_real.json` |
| F2 修复与替换 | ✅ | 导出菜单「预览可修复条目」；抽屉「找替代文献」 | 真实报告 15/15 条可重排；替换检索 438 条查询 R@3 **0.3219**（BGE-M3），`data/experiments/replacement_eval.json` |
| F3 撤稿 / 勘误 | ✅ | 报告页红色横幅、条目卡徽章 | OpenAlex 撤稿 100/100、对照 0 误报；DOI 互换 99 条 0 Exact；`docs/retraction.md` |
| F4 CiteBench-CN v2 | ✅ | 文档站「公开榜单」 | 500 条（10 类）；精确率 **1.0000**、召回 **0.6487**（核验完成后 0.8707）、F1 **0.7869**；`docs/citebench_v2.md` |
| F5 批量健康聚合 | ✅ | 历史页「聚合健康画像」 | 21 篇 509 条、平均 **76.1**、CSV 导出；`docs/aggregate.md` |

## 2. 支撑能力（第二轮）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| S1 页内证据 | ✅ | 引注「第 N 页」→ 原页图 + 高亮原句；真实 10 页论文 17/18 定位 |
| S2 问题分诊 | ✅ | 待修 / 已修 / 忽略；复检 diff 自动关闭已解决项 |
| S3 版面选路 | ✅ | 版面 vs 文本按条数与题名健康度择优；Phi-3 71→72 条 |
| S4 题录库 SQLite sidecar | ✅ | JSON 为主、SQLite 为镜像；删除 JSON 可回退；迁移/回滚脚本 |
| S5 离线 E2E 进 CI | ✅ | GitHub Actions `smoke` job：离线起服务 + 13 项 E2E |
| S6 人审评分脚本 | ✅ | `scripts/score_audit_sheet.py`：准确率 / macro-F1 / κ / 覆盖率；空表拒绝 |
| S7 收尾对齐 | ✅ | OpenAPI 契约测试 + 本文件 + Docker 1.3.4 镜像健康检查（493 MB，离线 health 1.3.4） |
| S8 截图自动化 | ✅ | `scripts/capture_evidence.py`：11 页 + 报告页，控制台报错即失败 |

## 3. 核心指标（对外口径）

| 指标 | 数字 | 样本 | 口径 / 边界 |
| --- | --- | --- | --- |
| 真实论文核验 | 409 条：125 精确 / 87 小偏差 / 197 未核实 / **0 严重不符** | 20 篇真实 PDF | 未核实 ≠ 抄错；接本地库后 405/4/0/0 |
| CiteBench-CN v2 | 精确率 1.0000；召回 0.6487；F1 0.7869 | 500 条构造 | Unknown 19.87% 计漏报；撤稿 17/17 |
| 支持度（主口径） | macro-F1 **0.9597**、准确率 0.96 | 100 条构造 | 单段基线 0.9005；标签由构造规则决定 |
| 支持度（扩展集） | macro-F1 **0.9841**、准确率 0.9833 | 300 条构造 | 与 100 条同分布，不可当人审 |
| 开源小模型 | LoRA Qwen3-1.7B **0.9721 / 0.9667** | test 60 | 基座零样本 0.4935；产品路径复测一致 |
| 真实图表 | 8B 0.96；ChartCheck 400 零样本 F1 0.7628 | 10 条真实 / 400 条外部 | 第一道筛查，不替代人读图 |
| 引用抽取 | 21/22 篇有引注、543 处；被引 60.1% | 22 篇真实 | 自动指标，非人工准确率 |
| 性能 | 54 条 8.01 s；1000 条解析 0.118 s；文本缓存 0.014 s | 本机 | 缓存热、不含 LLM 判定 |

## 4. 还没做 / 外部阻塞

| 项 | 状态 | 需要什么 |
| --- | --- | --- |
| Word 任务窗格真机 | 预览版，未在真实 Word 里点通 | 用户在 Word「插入 → 我的加载项」手动加载 |
| 50 条人工抽检 | 评分脚本与空白表已就绪 | 3 位评审独立盲标（`data/audit/audit_sheet.csv`） |
| Zenodo DOI | 未上传 | 可选；需要用户 token |
| Docker 镜像发布到 registry | 未推送 | 可选；需要 registry 账号 |
| 移动端 | 不做（用户决定） | — |
| 演示视频/PPT/报告同步 | 材料阶段再做（用户后置） | — |

## 5. 运行与复现

```bash
# 本地
PYTHONPATH=src python -m uvicorn web.app:app --port 8013
# 全量测试
PYTHONPATH=src python -m pytest tests -q        # 661 passed
python scripts/verify_artifacts.py               # 137/137
python -m mkdocs build --strict                  # 文档站
# Docker（1.3.4）
docker build -f docker/Dockerfile -t citeguard-cn:1.3.4 .
docker run -d --rm -p 18082:8000 -e CITEGUARD_OFFLINE=1 citeguard-cn:1.3.4
```

离线演示：`CITEGUARD_OFFLINE=1` + `samples/offline_demo/`（10 条真实题录 + 1 条虚构）。
Docker 健康输出存档：`docs/evidence/logs/docker-1.3.4-health.txt`（`{"version":"1.3.4","offline":true}`）。
所有证据索引见 `docs/evidence_index.md`；截图在 `docs/evidence/shots/`。
