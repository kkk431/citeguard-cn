"""Record a fuller product walkthrough (take 2), with compare + RIS + theme scenes."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path("D:/ai+ky/citeguard")
OUT = ROOT / "out/video"
RAW = OUT / "raw3"
BASE = "http://127.0.0.1:8010"
PDF = str(ROOT / "data/real_corpus/hanspub_152575.pdf")
PDFS = [str(ROOT / f"data/real_corpus/hanspub_{n}.pdf") for n in (152575, 152594, 152680)]
CMP = [str(ROOT / f"data/real_corpus/hanspub_{n}.pdf") for n in (152594, 152680)]
IMG1 = str(ROOT / "out/figtest_real/images/hanspub_152575_p3_1.png")
RIS = str(ROOT / "samples/offline_demo/library.ris")

marks: list[dict] = []
t0 = 0.0


def mark(name: str) -> None:
    marks.append({"name": name, "t": round(time.perf_counter() - t0, 2)})
    print(f"[{time.perf_counter() - t0:7.2f}] {name}")


async def hold(page, sec: float) -> None:
    await page.wait_for_timeout(int(sec * 1000))


async def glide(page, x: float, y: float, steps: int = 18) -> None:
    await page.mouse.move(x, y, steps=steps)
    await page.wait_for_timeout(240)


async def to(page, selector: str) -> None:
    el = page.locator(selector).first
    try:
        await el.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    box = await el.bounding_box()
    if box:
        await glide(page, box["x"] + min(box["width"] / 2, 320), box["y"] + min(box["height"] / 2, 220))
    await hold(page, 0.7)


async def click(page, selector: str) -> None:
    await to(page, selector)
    await page.locator(selector).first.click()
    await hold(page, 0.8)


async def cursor(page) -> None:
    await page.add_style_tag(content="""
    #__cursor{position:fixed;left:-40px;top:-40px;width:26px;height:26px;border-radius:50%;
      border:2px solid #7ff0cf;background:rgba(127,240,207,.18);box-shadow:0 0 22px rgba(127,240,207,.55);
      z-index:2147483647;pointer-events:none;transition:transform .06s ease-out}
    #__cursor:after{content:"";position:absolute;left:11px;top:11px;width:4px;height:4px;border-radius:50%;background:#eafffa}
    """)
    await page.evaluate("""() => {
      const c = document.createElement('div'); c.id='__cursor'; document.body.appendChild(c);
      window.addEventListener('mousemove', (e) => { c.style.left = (e.clientX-13)+'px'; c.style.top = (e.clientY-13)+'px'; });
    }""")


async def main() -> None:
    global t0
    RAW.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-gpu", "--hide-scrollbars"])
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, device_scale_factor=1,
            record_video_dir=str(RAW), record_video_size={"width": 1920, "height": 1080},
        )
        page = await ctx.new_page()
        page.set_default_timeout(300_000)
        t0 = time.perf_counter()
        mark("start")

        await page.goto(BASE + "/", wait_until="networkidle")
        await cursor(page)
        await glide(page, 960, 520)
        await hold(page, 7)
        mark("home")

        await page.set_input_files("#file-input", [PDF])
        await page.select_option("#support-max", "10")
        await page.check("#figure-check")
        await glide(page, 700, 520)
        await hold(page, 4)
        await click(page, "#start-btn")
        mark("submitted")

        await page.wait_for_selector("#summary-tabs", timeout=300_000)
        await hold(page, 2)
        mark("report_ready")

        await hold(page, 10)
        await click(page, '[data-summary-tab="refs"]')
        await hold(page, 3)
        await page.wait_for_selector("#ref-list .ref", timeout=30_000)
        await to(page, "#ref-list .ref")
        await page.locator("#ref-list .ref").first.click()
        await page.wait_for_selector("#ref-drawer:not([hidden])", timeout=10_000)
        await hold(page, 8)
        close = page.locator("#ref-drawer-close")
        if await close.count():
            await close.click()
        await hold(page, 1)
        await page.click(".export-menu summary")
        await hold(page, 7)
        await page.click(".export-menu summary")
        mark("report_done")

        # 图表：单图
        await page.goto(BASE + "/figure", wait_until="networkidle")
        await page.set_input_files("#figure-file", [IMG1])
        await page.fill("#figure-claim", "图中 2025 年的发文量最高，为 195 篇。\n图中 2023 年的发文量最高，为 195 篇。")
        await hold(page, 4)
        await click(page, "#figure-check-btn")
        await page.wait_for_selector("#figure-result:not(.hidden)", timeout=180_000)
        await hold(page, 10)
        mark("figure_single")

        # 图表：PDF 自动定位
        await page.set_input_files("#figure-file", [])
        await page.set_input_files("#figure-paper", [PDF])
        await page.fill("#figure-claim", "图中 2025 年的发文量最高，为 195 篇。")
        await page.fill("#figure-page", "")
        await hold(page, 3)
        await click(page, "#figure-check-btn")
        await page.wait_for_selector("#figure-result:not(.hidden)", timeout=180_000)
        await hold(page, 9)
        mark("figure_pdf")

        # 题录库
        await page.goto(BASE + "/library", wait_until="networkidle")
        await click(page, "#library-demo-btn")
        await hold(page, 4)
        await page.set_input_files("#library-file", [RIS])
        await click(page, "#library-import-btn")
        await hold(page, 4)
        await page.fill("#library-search", "教育")
        await hold(page, 4)
        await page.fill("#library-search", "")
        await to(page, "#library-table")
        await hold(page, 4)
        mark("library")

        # 发现
        await page.goto(BASE + "/discover", wait_until="networkidle")
        await page.fill("#discover-query", "人工智能 教育")
        await click(page, "#discover-btn")
        await page.wait_for_selector("#discover-result-section:not(.hidden)", timeout=180_000)
        await hold(page, 9)
        mark("discover")

        # 批量
        await page.goto(BASE + "/", wait_until="networkidle")
        await page.set_input_files("#file-input", PDFS)
        await page.select_option("#support-max", "0")
        await page.uncheck("#figure-check")
        await hold(page, 3)
        await click(page, "#start-btn")
        await page.wait_for_selector("#batch-results:not(.hidden)", timeout=300_000)
        await hold(page, 9)
        mark("batch")

        # 多篇论文对比
        await page.goto(BASE + "/compare", wait_until="networkidle")
        await page.set_input_files("#compare-files", CMP)
        await hold(page, 3)
        mark("compare_start")
        await click(page, "#compare-btn")
        await page.wait_for_selector("#compare-result-section:not(.hidden)", timeout=300_000)
        await hold(page, 6)
        mark("compare_done")

        # 历史 + 双报告对比
        await page.goto(BASE + "/history", wait_until="networkidle")
        await page.wait_for_selector("input.cmp", timeout=30_000)
        boxes = page.locator("input.cmp")
        n = await boxes.count()
        for i in range(min(2, n)):
            await boxes.nth(i).check()
            await hold(page, 0.4)
        await click(page, "#compare-run")
        await page.wait_for_selector("#compare-panel:not([hidden])", timeout=120_000)
        await hold(page, 9)
        mark("history")

        # 评测
        await page.goto(BASE + "/benchmark", wait_until="networkidle")
        await hold(page, 8)
        await page.evaluate("window.scrollTo({top: 950, behavior:'smooth'})")
        await hold(page, 7)
        await page.evaluate("window.scrollTo({top: 2300, behavior:'smooth'})")
        await hold(page, 8)
        mark("benchmark")

        # 关于
        await page.goto(BASE + "/about", wait_until="networkidle")
        await hold(page, 6)
        await page.evaluate("window.scrollTo({top: 750, behavior:'smooth'})")
        await hold(page, 6)
        mark("about")

        # 主题切换
        await page.goto(BASE + "/", wait_until="networkidle")
        await click(page, "#theme-toggle")
        await hold(page, 5)
        await click(page, "#theme-toggle")
        await hold(page, 2)
        mark("theme")

        # GitHub
        await page.goto("https://github.com/kkk431/citeguard-cn", wait_until="networkidle")
        await hold(page, 8)
        mark("github")

        await page.wait_for_timeout(900)
        marks.append({"name": "record_end", "t": round(time.perf_counter() - t0, 2)})
        print("raw duration", marks[-1]["t"])
        (OUT / "timeline3.json").write_text(json.dumps(marks, ensure_ascii=False, indent=1), encoding="utf-8")
        await ctx.close()
        await browser.close()
        videos = sorted(RAW.glob("*.webm"), key=lambda p: p.stat().st_mtime)
        print("video", videos[-1] if videos else "none")


if __name__ == "__main__":
    asyncio.run(main())
