# G1 入口与任务路径

## 目标
用户从首页进入工作台后：三种任务模式可见、最近报告可见、有运行中任务时在主入口直接提示、刷新不丢粘贴内容与选项。

## 行为
- `/workspace` 顶部保留三个任务模式：论文体检 / 快速判定 / 批量判定（各自独立页面，可直接收藏/分享）。
- 最近报告仍在工作台右栏；有 `queued/running` 任务时，主入口显示「有任务正在运行 · 刷新/离开页面不会中断」并提供 `/history` 链接。
- 粘贴文本、支持度档位、图表抽检勾选写入 `localStorage`（`citeguard.workspace.draft.v1`），刷新后恢复；提交成功后清空。
- 任务提交后仍进入 `/report/<id>`，可直接深链接到报告/history。

## 验证
- 真实运行任务 `d73ae2dcd2e9` 时工作台显示运行中提示。
- Playwright 刷新后：`#paste-text` 内容、`#support-max`=80、`#figure-check`=true 均恢复。
- 截图：`docs/evidence/shots/opt-G1-workspace-active-1.7.41-1440.png`、`opt-G1-draft-restored-1.7.41-1440.png`。
- 数据：`data/experiments/opt_g1_entry_state_2026-11-26.json`。
- 测试：`test_workspace_shows_active_job_banner`；全套 1063 passed。

## 边界
- 草稿只保存在本机浏览器；文件本身不持久化（隐私与体积），刷新后需重新选文件。
- 不把“离开页面”说成“关掉浏览器任务继续”：任务在服务端继续，但浏览器关闭后需从 `/history` 找回。
