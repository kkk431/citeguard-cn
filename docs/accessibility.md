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
