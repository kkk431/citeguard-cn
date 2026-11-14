"""Capture the final, 1920x1080 product screenshots used as review evidence.

The shots are real pages of the running app, with real data.  This script never
fabricates a state: pages that need a job use ``--job``; pages that need a
search run the search against the live instance; the Live shot runs the actual
claim through the configured judge.

    python scripts/capture_final_shots.py --job 96511af51c97

Outputs ``docs/evidence/shots/final/product/*.png`` and ``manifest.json``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "evidence" / "shots" / "final" / "product"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8013")
    ap.add_argument("--job", required=True, help="report job id used for the report shots")
    ap.add_argument("--only", nargs="*", help="optional subset of scene names")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    base = args.base.rstrip("/")
    manifest: list[dict] = []
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": args.width, "height": args.height}, device_scale_factor=1)
        context.add_init_script("localStorage.setItem('citeguard-theme','dark')")
        page = context.new_page()
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        def shot(name: str, title: str, selector: str, path: str, wait_ms: int = 800, action=None, scroll: str | None = None) -> None:
            if args.only and name not in args.only:
                return
            console_errors.clear()
            try:
                page.goto(base + path, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(500)
                if action:
                    action(page)
                page.wait_for_selector(selector, timeout=30000)
                if scroll:
                    page.locator(scroll).first.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
                page.wait_for_timeout(wait_ms)
                target = OUT / f"{name}.png"
                page.screenshot(path=str(target), full_page=False)
                status = "OK" if not console_errors else f"CONSOLE:{len(console_errors)}"
                print(f"{status:12} {name:28} {target.name}")
                manifest.append({"file": str(target.relative_to(ROOT)).replace("\\", "/"), "title": title, "path": path, "status": status})
                if console_errors:
                    failures.append(f"{name}: {console_errors[0][:160]}")
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL         {name:28} {exc}")
                failures.append(f"{name}: {exc}")

        shot("01-landing", "独立首页：价值主张与真实报告预览", "h1", "/")
        shot("02-workspace", "工作台：上传、最近报告与本次会检查", "#upload-form", "/workspace")
        shot("03-support", "单句判定：四档含义与证据输入", "#sp-claim", "/support", action=lambda pg: pg.fill("#sp-claim", "The STIC model achieved an accuracy of 72.6% on the test set, comparable with doctors' consensus.") if pg.query_selector("#sp-claim") else None)
        shot("04-library", "题录库：标签、分页与覆盖构成", "#library-body", "/library")
        shot("05-discover", "文献发现：真实 OpenAlex 检索结果", "#discover-list .paper-card", "/discover",
             wait_ms=1200,
             action=lambda pg: (pg.fill("#discover-query", "人工智能 教育"), pg.evaluate("document.getElementById('discover-form').requestSubmit()")),
             scroll="#discover-form")
        shot("06-citemap", "CiteMap：断言分组与人工/机器证据", "#ctm-detail-body", "/citemap?topic=ai_education", wait_ms=1200)
        shot("07-live", "Live 单句核验：判官给出支持与逐字证据", "#live-output:not([hidden])", "/live",
             wait_ms=1000,
             action=lambda pg: (pg.locator(".live-example").nth(1).click(), pg.click("#live-btn")))
        shot("08-report-overview", "报告总览：结论、健康画像与先修项", "#report-root[data-ready='1']", f"/report/{args.job}", wait_ms=1200)
        shot("09-report-refs", "逐条结果与条目详情", "#ref-drawer:not([hidden])", f"/report/{args.job}",
             action=lambda pg: (pg.click('[data-summary-tab="refs"]'), pg.wait_for_selector('.ref[data-pos="0"]', state="visible", timeout=10000), pg.click('.ref[data-pos="0"]'), pg.wait_for_selector("#ref-drawer:not([hidden])", timeout=10000)))
        shot("09b-report-evidence", "证据抽屉：字段、支持度与正文引用", "#evidence-drawer:not([hidden])", f"/report/{args.job}",
             action=lambda pg: (pg.click('[data-summary-tab="refs"]'), pg.wait_for_selector('.ref[data-pos="0"]', state="visible", timeout=10000), pg.click('.ref[data-pos="0"]'), pg.wait_for_selector("#ref-drawer:not([hidden])", timeout=10000), pg.click('[data-detail-evidence]'), pg.wait_for_selector("#evidence-drawer:not([hidden])", timeout=10000)))
        shot("10-report-checks", "检查明细抽屉：来源/图表/支持度/引注", "#checks-drawer:not([hidden])", f"/report/{args.job}",
             action=lambda pg: (pg.click("#open-checks"), pg.wait_for_selector("#checks-drawer:not([hidden])", timeout=10000), pg.click('[data-checks-tab="citation"]'), pg.wait_for_timeout(400)))
        shot("11-repair", "一键修复：逐条 before/after 与字段提示", "#repair-modal:not([hidden])", f"/report/{args.job}",
             action=lambda pg: (pg.click("#btn-repair-all"), pg.wait_for_selector("#repair-modal:not([hidden])", timeout=10000)))
        shot("12-history", "全部报告：按文件合并与分页", "#history-body", "/history")
        shot("13-benchmark", "评测：CiteBench-CN v2 与真实基线", "#cb2-detection", "/benchmark", wait_ms=1200)
        shot("14-models", "模型设置：云端与本地两套判官", "#judge-grid", "/settings/models")
        shot("15-about", "关于：能力边界与开源资产", "h1", "/about")
        shot("16-figure", "图表核验：上传截图或按引用句定位", "#figure-dropzone", "/figure")
        shot("17-compare", "多篇对比：六字段对照", "h1", "/compare")
        shot("18-batch", "批量判定：一次粘贴多条引用句", "#bt-claims", "/batch")

        browser.close()

    (OUT / "manifest.json").write_text(json.dumps({
        "generated_by": "scripts/capture_final_shots.py",
        "job": args.job,
        "base": base,
        "version": "1.7.13",
        "shots": manifest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(manifest)} shots -> {OUT}")
    if failures:
        print("failures:")
        for item in failures:
            print(" -", item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
