from citeguard.contrast import contrast_ratio, luminance


def test_black_on_white_is_max_contrast():
    assert contrast_ratio("#000000", "#ffffff") > 20.9


def test_mid_gray_is_below_aa():
    assert contrast_ratio("#777777", "#ffffff") < 4.5


def test_luminance_bounds():
    assert luminance("#ffffff") == 1.0
    assert luminance("#000000") == 0.0


def test_light_theme_tokens_meet_aa():
    import re
    from pathlib import Path
    text = Path("web/static/css/refresh.css").read_text(encoding="utf-8")
    body = re.search(r"(?s)body\.theme-light\s*\{(.*?)\}", text).group(1)
    rows = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", body))
    rows = {k.lstrip("-"): v for k, v in rows.items()}
    assert contrast_ratio(rows["ink"], rows["paper"]) >= 4.5
    assert contrast_ratio(rows["ink-2"], rows["paper"]) >= 4.5
    assert contrast_ratio(rows["muted"], rows["paper"]) >= 4.5
    assert contrast_ratio(rows["accent-ink"], rows["accent"]) >= 4.5
