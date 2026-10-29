"""Record the CiteGuard-CN demo in one continuous browser take.

Usage:
  python scripts/record_demo.py --dry          # validate the flow, no video
  python scripts/record_demo.py --video        # record webm into out/video/raw
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8010"
PDF = Path("data/real_corpus/hanspub_152575.pdf").resolve()
FIG = Path("out/figtest_real/images/hanspub_152575_p3_1.png").resolve()
OUT = Path("out/video")
RAW = OUT / "raw"

CURSOR_JS = """
(() => {
  const c = document.createElement('div');
  c.id = '__demo_cursor';
  Object.assign(c.style, {position:'fixed', left:'0', top:'0', width:'24px', height:'24px',
    border:'2px solid rgba(6,20,32,.75)', borderRadius:'50%', background:'rgba(255,255,255,.38)',
    boxShadow:'0 0 0 2px rgba(255,255,255,.85), 0 4px 12px rgba(0,0,0,.35)',
    pointerEvents:'none', zIndex:'2147483647', transform:'translate(-50%,-50%)',
    transition:'width .07s, height .07s, background .07s'});
  const mount = () => document.documentElement && document.documentElement.appendChild(c);
  if (document.documentElement) mount(); else addEventListener('DOMContentLoaded', mount, {once:true});
  addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { c.style.width='16px'; c.style.height='16px'; c.style.background='rgba(255,184,77,.7)'; }, true);
  addEventListener('mouseup', () => { c.style.width='24px'; c.style.height='24px'; c.style.background='rgba(255,255,255,.38)'; }, true);
})();
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--video", action="store_true")
    args = ap.parse_args()

    marks: list[dict] = []
    t0 = time.time()

    def mark(name: str) -> None:
        marks.append({"name": name, "t": round(time.time() - t0, 2)})
        print(f"[{marks[-1]['t']:7.2f}s] {name}")

    def beat(ms: int) -> None:
        time.sleep(ms / 1000)

    RAW.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--force-device-scale-factor=1"])
        ctx_kwargs = {"viewport": {"width": 1920, "height": 1080}, "device_scale_factor": 1}
        if args.video:
            ctx_kwargs["record_video_dir"] = str(RAW)
            ctx_kwargs["record_video_size"] = {"width": 1920, "height": 1080}
        ctx = browser.new_context(**ctx_kwargs)
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()
        page.set_default_timeout(30000)

        mark("start")
        page.goto(BASE, wait_until="networkidle")
        beat(1200)
        page.mouse.move(960, 420)
        beat(600)
        page.mouse.wheel(0, 620)
        beat(2200)
        page.mouse.wheel(0, 620)
        beat(1200)
        page.mouse.wheel(0, -1240)
        beat(800)
        mark("home")

        page.locator("#file-input").set_input_files(str(PDF))
        beat(1200)
        page.locator("#upload-card").scroll_into_view_if_needed()
        beat(800)
        page.locator("#figure-check").check()
        beat(500)
        page.locator("#start-btn").click()
        mark("submitted")
        page.wait_for_url("**/report/**", timeout=300000)
        mark("report_opened")
        page.wait_for_function(
            "() => { const v=document.getElementById('verdict'); return v && v.innerText.trim().length>0; }",
            timeout=300000,
        )
        page.wait_for_timeout(1500)
        mark("report_ready")
        
        beat(3000)
        page.mouse.move(240, 380)
        beat(2500)
        page.locator("#figure-checks").scroll_into_view_if_needed()
        beat(1000)
        page.mouse.move(900, 600)
        beat(4500)
        page.locator("#support-summary").scroll_into_view_if_needed()
        beat(1000)
        page.mouse.move(900, 600)
        beat(4000)
        page.locator("#verdict").scroll_into_view_if_needed()
        beat(1200)

        page.locator(".export-menu summary").click()
        beat(1000)
        page.mouse.move(700, 320)
        beat(2500)
        page.locator('.export-menu-body a[href*="format=ris"]').hover()
        beat(2000)
        page.locator(".export-menu summary").click()
        beat(800)

        page.locator('.tab[data-summary-tab="refs"]').click()
        beat(1500)
        chips = page.locator("#chips .chip")
        if chips.count():
            chips.first.click()
            beat(800)
        rows = page.locator(".ref")
        print("refs rows:", rows.count())
        rows.first.click()
        beat(1300)
        drawer = page.locator("#ref-drawer")
        print("drawer text:", drawer.inner_text()[:200].replace("\n", " | "))
        beat(1200)
        box = drawer.bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        beat(600)
        page.mouse.wheel(0, 700)
        beat(2500)
        body = page.locator("#ref-drawer-body")
        if body.count():
            bb = body.bounding_box()
            if bb:
                page.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 3)
        page.mouse.wheel(0, 650)
        beat(3600)
        page.mouse.wheel(0, 650)
        beat(3000)
        page.mouse.wheel(0, -1300)
        beat(1200)
        page.locator("#ref-drawer-close").click()
        beat(800)
        rows.nth(1).click()
        beat(2000)
        page.mouse.move(1500, 500)
        beat(3500)
        page.locator("#ref-drawer-close").click()
        beat(800)
        mark("report_detail")

        page.goto(BASE + "/figure", wait_until="networkidle")
        beat(1400)
        page.locator("#figure-file").set_input_files(str(FIG))
        beat(1000)
        page.locator("#figure-claim").fill("图中 2025 年的发文量最高，为 195 篇。")
        beat(700)
        page.locator("#figure-context").fill(
            "图 1 为 2016—2025 年该刊发文量统计；柱状图显示 2025 年发文量最高。"
        )
        beat(700)
        page.locator("#figure-check-btn").click()
        mark("figure_submitted")
        page.wait_for_selector("#figure-result:not(.hidden)", timeout=180000)
        mark("figure_ready")
        beat(4500)
        page.mouse.move(960, 700)
        beat(2000)
        page.locator("#figure-claim").fill("图中 2023 年的发文量最高，为 195 篇。")
        beat(1000)
        page.locator("#figure-check-btn").click()
        mark("figure2_submitted")
        beat(9000)
        page.mouse.move(960, 750)
        beat(2500)
        mark("figure")

        page.goto(BASE + "/library", wait_until="networkidle")
        beat(1500)
        page.locator("#library-demo-btn").click()
        beat(3000)
        page.locator("#library-bulk-text").fill(
            "[1] 张三, 李四. 中文引文核验方法研究[J]. 情报学报, 2024, 12(3): 10-20.\n"
            "[2] 王五. 学术不端检测技术综述[J]. 图书情报工作, 2023, 67(8): 45-52."
        )
        beat(800)
        page.locator("#library-bulk-btn").click()
        beat(2200)
        page.locator("#library-search").scroll_into_view_if_needed()
        beat(1200)
        page.locator('a[href="/api/library/export?format=ris"]').hover()
        beat(1800)
        page.locator("#library-search").fill("雾霾")
        beat(1800)
        page.locator("#library-search").fill("")
        beat(1200)
        mark("library")

        page.goto(BASE + "/discover", wait_until="networkidle")
        beat(1500)
        page.locator("#discover-query").fill("人工智能 教育")
        beat(800)
        page.locator("#discover-btn").click()
        mark("discover_submitted")
        page.wait_for_selector("#discover-result-section:not(.hidden)", timeout=120000)
        beat(2500)
        page.mouse.move(960, 700)
        beat(3500)
        page.mouse.wheel(0, 600)
        beat(3000)
        mark("discover")

        page.goto(BASE, wait_until="networkidle")
        beat(1500)
        page.locator("#file-input").set_input_files([
            str(Path("data/real_corpus/hanspub_152572.pdf").resolve()),
            str(Path("data/real_corpus/hanspub_152573.pdf").resolve()),
            str(Path("data/real_corpus/hanspub_152574.pdf").resolve()),
        ])
        beat(1500)
        page.locator("#support-max").select_option("0")
        beat(600)
        page.locator("#start-btn").click()
        mark("batch_submitted")
        page.wait_for_selector("#batch-results:not(.hidden)", timeout=300000)
        beat(2500)
        page.locator("#batch-results").scroll_into_view_if_needed()
        beat(4500)
        mark("batch")

        page.goto(BASE + "/benchmark", wait_until="networkidle")
        beat(2000)
        page.mouse.move(960, 500)
        beat(2500)
        page.mouse.wheel(0, 700)
        beat(4000)
        page.mouse.wheel(0, 700)
        beat(3500)
        mark("benchmark")

        page.goto(BASE + "/history", wait_until="networkidle")
        beat(2500)
        page.mouse.wheel(0, 500)
        beat(2500)
        mark("history")

        page.goto(BASE + "/about", wait_until="networkidle")
        beat(2200)
        page.mouse.wheel(0, 600)
        beat(4500)
        page.mouse.wheel(0, 600)
        beat(3800)
        mark("about")

        page.goto("https://github.com/kkk431/citeguard-cn", wait_until="domcontentloaded", timeout=60000)
        beat(2500)
        page.mouse.move(960, 500)
        beat(800)
        page.mouse.wheel(0, 700)
        beat(2500)
        page.mouse.wheel(0, 500)
        beat(1800)
        mark("github")

        video = page.video
        ctx.close()
        browser.close()
        if video:
            print("video:", video.path())

    (OUT / "timeline.json").write_text(json.dumps(marks, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()
