# Accessibility and theme contrast

Method: WCAG 2.1 relative-luminance formula (`src/citeguard/contrast.py`), tokens read
directly from `web/static/css/refresh.css`. Normal text needs 4.5:1, large text/UI 3.0:1.

Run:

```bash
PYTHONPATH=src python scripts/check_contrast.py
```

Output is also written to `data/experiments/contrast_report.json`.

## Light theme (after 1.0.1)

| pair | ratio | need | result |
|---|---|---|---|
| ink / paper | 15.45 | 4.5 | pass |
| ink-2 / paper | 6.74 | 4.5 | pass |
| muted / paper | 4.63 | 4.5 | pass |
| accent / paper | 4.94 | 3.0 | pass |
| white / accent | 5.44 | 4.5 | pass |
| bad / paper | 5.75 | 3.0 | pass |

Dark theme passed unchanged; see the JSON for all 20 pairs.

## Other accessibility work
- Focus rings on links/buttons/inputs; `aria-live` regions for job progress and copy feedback.
- Charts have a table view (`build_charts` + report template), so information is not colour-only.
- Keyboard: `/` focus search, `j`/`k` row navigation, Enter open, Esc close drawer, Ctrl/Cmd+K palette.
- Reduced-motion media query disables reveal animations.

## Keyboard audit (1.0.2)

`data/experiments/frontend_audit.json` records 8 Playwright checks at 1280x800:

| check | result |
|---|---|
| home has no horizontal overflow | pass |
| home has an aria-live region | pass |
| all home buttons/links have names | pass (0 unnamed) |
| Ctrl+K opens the command palette | pass |
| j focuses the first reference row | pass |
| Enter opens the evidence drawer | pass |
| Esc closes the drawer | pass |
| / focuses report search | pass |

The audit also caught two real bugs fixed in 1.0.2: rail links were unnamed when
collapsed, and j/k/`/` targeted the hidden list when the overview tab was active.


## 1.0.12 全站巡检（50/50）

`scripts/audit_frontend.py [base]` 覆盖 11 个页面（首页/支持度/题录库/发现/对比/图表/批量/评测/历史/模型设置/关于）与报告页键盘流，逐页检查：

1. 1280 宽无横向溢出；
2. 存在 `h1`；
3. 所有 `button` / `a[href]` 有可访问名；
4. 控制台无错误；
5. 报告页 j/Enter/Esc/`/` 与全局 Ctrl+K。

结果：**50/50 通过**；唯一失败项是首页 favicon 404，已用 SVG icon + `/favicon.ico` 路由修复。证据 `data/experiments/frontend_audit.json`，截图 `docs/evidence/shots/phase-38-a11y-pages-1.0.12.png`（E48）。

## 1.7.4 全站巡检（54/54）

`scripts/audit_frontend.py` 扩到 12 个页面（新增 CiteMap）与报告页键盘流；同时修正检查脚本的一个真实误判：可访问名按 `aria-label > title > innerText` 取值，不能因为按钮只有空白文本就判为无名。

结果：**54/54 通过**（含首页、CiteMap、报告 j/Enter/Esc/`/` 与 Ctrl+K）；产物 `data/experiments/frontend_audit.json`。

