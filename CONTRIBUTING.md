# 参与 CiteGuard-CN

CiteGuard-CN 是 Apache-2.0 的中文引文核验工作台。欢迎提交可复现的 bug、评测数据修正、中文规则补全与文档改进。

## 本地开发

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests -q
python scripts/verify_artifacts.py
python -m uvicorn web.app:app --port 8013
```

需要联网核验时设置 `DEEPSEEK_API_KEY`（支持度判定）或本地 OpenAI 兼容服务；完全离线可设 `CITEGUARD_OFFLINE=1`。

## 提交前

- 新增/修改功能必须带测试；`pytest tests -q` 全绿。
- 修改数字/结论时，同步更新对应 `data/experiments/*.json`、`docs/evidence_index.md` 与 `docs/evidence_matrix.md`；没有 JSON 或命令支撑的数字不要写。
- 不要提交 `.env*`、API Key、运行时 `data/history.db`、`data/judge_models.json`、个人题录库。
- 不要伪造真人标注、用户反馈或截图；AI 辅助的核对必须标为 AI，不能写成人工核对。
- 中文文档统一 UTF-8；图片放 `docs/evidence/shots/` 并在证据索引登记。
- 提交信息用英文一句话说明改动，例如 `Fix live prewarm cache key`。

## 代码边界

- 核心 `src/citeguard/` 不引入 AGPL 依赖；PyMuPDF 仅作为可选布局依赖，见 `docs/licenses.md`。
- 产品页面用原生 JS/HTML，不引入需要 CDN 的前端框架；新增前端依赖需内置到 `web/static/vendor/` 并更新 `THIRD_PARTY_NOTICES.md`。
- 外部模型只通过 OpenAI 兼容接口接入，不把权重提交进仓库。

## 报告问题

请附：输入文件（可脱敏）、命令/页面、期望结果、实际结果、版本号（`/api/health`）与是否离线。安全问题请勿公开贴 Key。
