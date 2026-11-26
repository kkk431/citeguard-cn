# G4 微交互：页面过渡 / 骨架 / 抽屉 / toast / 命令面板

## 目标

把此前散落在各页的交互反馈收成一套可复用层：页面进入有轻过渡，异步区域有骨架屏，抽屉和弹层有统一的开合节奏，toast 有明确的语义和关闭入口，命令面板可分组、可键盘操作。所有动画尊重系统的「减少动效」，且不改变任何业务逻辑、不引入 CDN 或新依赖。

## 实现

改动只在 `web/templates/base.html`、`web/static/js/app.js`、`web/static/css/refresh.css`，页面模板与业务脚本未改。

### 1. 页面过渡

- `body.cg-ready main` 与 `.shell-top` 在首屏进入时做 320ms/220ms 的位移淡入；只在 `prefers-reduced-motion: no-preference` 下可见。
- 点击同源普通链接（非 `#`、非 `target=_blank`、无修饰键）时，顶部显示 2px 进度条 `#cg-nav-progress`；`pageshow` 时收起。不延迟、不拦截真实导航。
- 命令面板选中条目时也调用同一个 `startPageTransition()`，避免“点了没反应”的空档。

### 2. 骨架屏

- 公共 API：`CiteGuard.skeleton(target, rows)`、`CiteGuard.skeletonHTML(rows)`、`CiteGuard.clearSkeleton(target)`；`rows` 限制 1–8 行。
- 声明式：任意空容器加 `data-skeleton="3"` 即自动渲染；有内容时不会覆盖。
- 抽屉内自动兜底：`#ref-drawer`、`#evidence-drawer` 打开且正文仍为空时注入 4 行骨架（`aria-busy="true"`），业务脚本写入内容后自动移除标记，不伪造数据。
- 骨架条使用低对比渐变，减少动效下退化为静态色块。

### 3. 抽屉与弹层

- 统一识别 `#palette`、`#ref-drawer.open`、`#evidence-drawer`、`#checks-drawer`、`#repair-modal`、`#fix-modal`、`#page-viewer`、`.lib-modal` 这些遮罩层。
- 任一遮罩打开时给 `body` 加 `.cg-overlay-open`：锁定背景滚动，并用 `--cg-scrollbar` 补偿滚动条宽度，避免布局横跳；关闭后恢复。
- 统一时长令牌 `--cg-motion-fast/base/slow`；`@starting-style` 给右滑抽屉补起始位移，`.drawer-panel`、`.checks-panel`、`.lib-modal-card`、`.repair-panel` 复用同一套缓动。开合逻辑仍由 `report.js`/`library.js` 控制，未改写。

### 4. toast

- 保留旧签名 `toast(message, ms)` 与 `window.showToast`（`figure.js` 在用），新增 `toast(message, {type, ms})`。
- 结构：图标 + 文本 + 关闭按钮；`success`/`error`/`info` 三种语义色；容器 `aria-live="polite"`，错误消息设为 `role="alert"`。
- 同一时刻只展示一条，最多排队 3 条；关闭按钮、超时、下一条自动衔接；错误提示可停留更久。

### 5. 命令面板

- 入口：`Ctrl/Cmd+K`、顶栏按钮、`#palette` 直达；分组为「最近 / 页面 / 动作 / 链接」，原有 16 个入口全部保留（含 `/workspace#upload-card`、`/workspace?sample=1`、GitHub 链接）。
- 键盘：↑↓、Home/End、PageUp/PageDown、Enter、Esc；Tab 在输入框与关闭按钮间循环，不会把焦点放出对话框。
- 可访问性：输入框 `role="combobox"`、`aria-controls`、`aria-expanded`、`aria-activedescendant`；列表 `role="listbox"`、每项 `role="option"` + `aria-selected`；打开时记忆焦点，关闭后还原。
- 「最近」只写在浏览器 `localStorage`（`citeguard.palette.recent.v1`），最多 3 条，不进入后端、不随报告保存。
- 实时显示命中数 `#palette-count`，空结果给出「没有匹配的页面或动作」。

### 6. 减少动效

- 启动时用 `matchMedia('(prefers-reduced-motion: reduce)')` 设置 `html[data-motion="reduced"]`，系统偏好变化时实时更新。
- CSS 同时响应 `data-motion` 与 `prefers-reduced-motion`：动画/过渡归零、骨架静止、导航进度条隐藏。
- JS 侧在减少动效下跳过进度条与排队等待，命令面板、toast 直接呈现。

### 7. 键盘焦点

- 统一 `:focus-visible` 外环；按钮/输入/链接使用 `--accent` 描边。
- 对话框内 Tab 闭环；关闭后焦点回到触发元素。

## 验证

真实 Chromium（Edge 158 headless）在 1440×900 与 1280×800 两个视口跑 `/workspace` 与 `/library`，检查控制台、失败请求、横向溢出、面板键盘操作、toast、骨架 API 和减少动效；9 项检查全部通过：

| 检查 | 1440 | 1280 |
| --- | --- | --- |
| 横向溢出（workspace / library） | 0 / 0 px | 0 / 0 px |
| 控制台错误 / 失败请求 | 0 / 0 | 0 / 0 |
| 命令面板打开、分组、滚动锁定 | 通过（16 个入口） | 通过（16 个入口） |
| 输入过滤、方向键、Esc 关闭并还原焦点 | 通过 | 通过 |
| toast 语义、文本、关闭 | 通过（role=status） | 通过（role=status） |
| 骨架渲染 4 行并清空 | 通过 | 通过 |
| 减少动效：main / palette / skeleton 动画 | 全部 `none` | 全部 `none` |

截图（`docs/evidence/shots/`）：

- `opt-G4-workspace-palette-1.7.47-1440.png`、`opt-G4-workspace-palette-1.7.47-1280.png`
- `opt-G4-workspace-toast-1.7.47-1440.png`、`opt-G4-workspace-toast-1.7.47-1280.png`
- `opt-G4-reduced-motion-1.7.47-1440.png`、`opt-G4-reduced-motion-1.7.47-1280.png`

数据：`data/experiments/opt_g4_micro_interactions_2026-11-26.json`（含每个视口的 DOM 状态、控制台错误、失败请求、截图清单与逐项布尔检查）。

测试：

```powershell
python -m pytest tests/test_web.py -q
python -m pytest tests -q
```

`tests/test_web.py` 新增 5 条 G4 契约测试：base 钩子、app.js 交互契约、refresh.css 动效令牌、命令面板原有入口未丢、无远程依赖。全量测试保持全绿（见任务报告中的最终计数）。

复现页面检查：

```powershell
python -m uvicorn web.app:app --host 127.0.0.1 --port 8017
# 浏览器打开 http://127.0.0.1:8017/workspace，Ctrl+K；再执行：
# window.CiteGuard.toast('已复制候选证据 · 2 条', {type:'success'})
```

## 边界

- 不是 SPA 路由：过渡只做视觉层，导航仍是整页跳转；进度条不改变服务端行为。
- 骨架只在容器为空时出现，不预填、不伪造条目数量；业务数据仍由原接口返回。
- toast 队列上限 3 条，超出丢弃最早一条；不做持久化通知中心。
- 命令面板「最近」仅本机 localStorage，换浏览器/清缓存即丢失。
- 减少动效由浏览器 `matchMedia` 与 `html[data-motion]` 双保险；不支持 `matchMedia` 的旧环境默认完整动效。
- 截图只覆盖 Chromium 1440/1280 的 `/workspace`、`/library`；未在 Firefox/Safari、移动端或真实第三方页面做视觉验收，不宣称跨浏览器像素级一致。
- 不修改 `report.js`、`citemap.js`、`web/app.py`；抽屉开合、命令面板导航目标均沿用原业务脚本。
