"""Build the fuller demo video: speed up the long compare wait, add narration/subs/cards."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path("D:/ai+ky/citeguard")
OUT = ROOT / "out/video"
RAW = OUT / "raw3"
SPEED = 3.0
PAD = 6.0

FONT = "C:/Windows/Fonts/msyhbd.ttc"
FONT_R = "C:/Windows/Fonts/msyh.ttc"


def load_marks() -> dict:
    marks = json.loads((OUT / "timeline3.json").read_text(encoding="utf-8"))
    return {m["name"]: m["t"] for m in marks}


def remap(t: float, m: dict) -> float:
    t1, t2 = m["compare_start"], m["compare_done"]
    if t <= t1:
        return t
    if t <= t2:
        return t1 + (t - t1) / SPEED
    return t1 + (t2 - t1) / SPEED + (t - t2)


# anchor, offset (raw seconds relative to anchor), text
SEGMENTS = [
    ("start", 0.4, "引证卫士，一个中文引文核验工作台。查存在、查支持、查格式。"),
    ("home", 0.6, "所有核验，都在本地流水线里跑。"),
    ("submitted", 1.2, "先上传一篇真实论文，打开支持度判定和正文图表抽检。解析、切分、比对、判定，每一步都在页面上。"),
    ("report_ready", 1.0, "十五条引用，零条严重不符。格式均分、正文一致率、支持度分布，都在总览里。"),
    ("report_ready", 11.0, "每条引用都有三层证据：题录、来源、国标。点开就能看。"),
    ("report_done", -10.0, "报告能导出成 HTML、Markdown、CSV、RIS、EndNote、BibTeX、CSL，直接进文献管理工具。"),
    ("figure_single", -9.0, "图表也能核验：先问 2025 年最高，它说支持；换成 2023 年，立刻改判不支持。"),
    ("figure_pdf", -9.0, "上传整篇 PDF，它自动找到对应页和图，不用手动截图。"),
    ("library", 0.4, "题录库已收 22 篇真实论文、412 条题录；RIS、EndNote、BibTeX、CSL 都能导入。"),
    ("discover", 0.4, "找不到的文献，用开放学术图谱检索：中文主题自动扩展英文关键词，去重后按相关度排序。"),
    ("batch", 0.2, "三篇并发，批量汇总。"),
    ("compare_start", 2.5, "多篇论文对比：六个字段逐篇抽取，这里快进。"),
    ("compare_done", -5.0, "矩阵出来，谁做了什么、差在哪，直接对齐。"),
    ("history", 0.4, "历史任务可以重跑、断点续跑；选两份报告，还能对比差异。"),
    ("benchmark", 0.4, "评测是底账。"),
    ("benchmark", 3.5, "CiteBench-CN 零点九六八四，ClaimSupport-CN 零点九五九七，真实四百零九条引用零误判。"),
    ("about", 0.4, "自研的不是模型，是流水线、判定规则和工程接线；模型、数据、工具全部开源。"),
    ("theme", 0.4, "深色、浅色两套主题，现场投影也能看清。"),
    ("github", -7.0, "代码、评测集、文档都公开，附许可证和第三方清单。"),
    ("end", 0.0, "引证卫士，让每一条引用都经得起追问。"),
]


def plan() -> None:
    m = load_marks()
    total = remap(m["record_end"], m)
    items = []
    for i, (anchor, off, text) in enumerate(SEGMENTS):
        if anchor == "end":
            start = total + 0.6
        else:
            start = remap(m[anchor] + off, m)
        items.append({"i": i, "start": round(max(0.3, start), 2), "text": text})
    (OUT / "narration_plan3.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "meta3.json").write_text(json.dumps({"total": round(total, 2), "marks": m}, ensure_ascii=False), encoding="utf-8")
    print("plan", len(items), "final", round(total, 2))


def dur(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def make_cards() -> tuple[Path, Path]:
    def card(name: str, lines) -> Path:
        img = Image.new("RGB", (1920, 1080), "#050d18")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 1920, 10], fill="#7ff0cf")
        y = 300
        for text, size, color, fp in lines:
            f = ImageFont.truetype(fp, size)
            w = d.textlength(text, font=f)
            d.text(((1920 - w) / 2, y), text, font=f, fill=color)
            y += size + 30
        p = OUT / f"{name}.png"
        img.save(p)
        return p
    intro = card("card_intro3", [
        ("引证卫士", 160, "#f4fbf8", FONT),
        ("CiteGuard-CN · 中文引文核验工作台", 44, "#9fc9c0", FONT_R),
        ("存在性 · 引用支持度 · GB/T 7714-2025", 34, "#7ff0cf", FONT_R),
    ])
    end = card("card_end3", [
        ("0 / 409", 150, "#7ff0cf", FONT),
        ("真实论文引用，零条严重不符", 42, "#dfeee9", FONT_R),
        ("github.com/kkk431/citeguard-cn", 34, "#ffb43a", FONT_R),
        ("AIC-2026-67377639", 26, "#7d9a94", FONT_R),
    ])
    return intro, end


def ts(t: float) -> str:
    h = int(t // 3600)
    mi = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{mi:02d}:{s:05.2f}"


def build() -> None:
    m = load_marks()
    meta = json.loads((OUT / "meta3.json").read_text(encoding="utf-8"))
    total = meta["total"]
    items = json.loads((OUT / "narration_plan3.json").read_text(encoding="utf-8"))
    items.sort(key=lambda x: x["start"])
    audios = [OUT / "audio" / f"seg3_{it['i']:02d}.wav" for it in items]
    for p in audios:
        if not p.exists():
            raise SystemExit(f"missing {p}; run SAPI on narration_plan3.json")
    durations = [dur(p) for p in audios]

    rows = []
    for it, p, d in zip(items, audios, durations):
        nxt = None
        for jt in items[items.index(it) + 1:]:
            nxt = jt["start"]
            break
        gap = (nxt - it["start"]) if nxt else (total - it["start"] - 0.2)
        gap = max(0.8, gap)
        tempo = min(1.35, d / gap) if d > gap else 1.0
        rows.append({**it, "dur": round(d, 2), "gap": round(gap, 2), "tempo": round(tempo, 3)})

    inputs, filters = [], []
    for r in rows:
        inputs += ["-i", str(OUT / "audio" / f"seg3_{r['i']:02d}.wav")]
        delay = int(r["start"] * 1000)
        filters.append(f"[{r['i']}:a]atempo={r['tempo']},adelay={delay}|{delay}[a{r['i']}]")
    mix = "".join(f"[a{r['i']}]" for r in rows) + f"amix=inputs={len(rows)}:normalize=0,alimiter=limit=0.9[aout]"
    Path(OUT / "audio_filter3.txt").write_text(";".join(filters + [mix]), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex_script", str(OUT / "audio_filter3.txt"),
                    "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", str(OUT / "narration3.m4a")], check=True)
    print("audio", dur(OUT / "narration3.m4a"))

    lines = []
    for r in rows:
        text = r["text"]
        chunks = [text[i:i + 20] for i in range(0, len(text), 20)]
        end = r["start"] + min(r["dur"] / r["tempo"], r["gap"] - 0.25)
        step = (end - r["start"]) / max(1, len(chunks))
        for k, ch in enumerate(chunks):
            a = r["start"] + k * step
            lines.append(f"Dialogue: 0,{ts(a)},{ts(a + step)},Default,,0,0,0,,{ch}")
    ass = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,44,&H00FFFFFF,&H000000FF,&H00151010,&H80000000,-1,0,0,0,100,100,0,0,1,2.4,0.8,2,80,80,42,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(lines) + "\n"
    (OUT / "subs3.ass").write_text(ass, encoding="utf-8")
    print("subs", len(lines))

    intro, end = make_cards()
    t1, t2 = m["compare_start"], m["compare_done"]
    final_no_pad = t1 + (t2 - t1) / SPEED + (m["record_end"] - t2)
    end_start = final_no_pad - 1.0
    vf = (
        f"[0:v]fps=25,trim=start=0:end={t1},setpts=PTS-STARTPTS[v1];"
        f"[0:v]fps=25,trim=start={t1}:end={t2},setpts=(PTS-STARTPTS)/{SPEED}[v2];"
        f"[0:v]fps=25,trim=start={t2},setpts=PTS-STARTPTS[v3];"
        f"[v1][v2][v3]concat=n=3:v=1:a=0,format=yuv420p,tpad=stop_mode=clone:stop_duration={PAD},"
        f"subtitles=out/video/subs3.ass:fontsdir=C\\\\:/Windows/Fonts[v0];"
        f"[1:v]format=rgba,fade=t=in:st=0:d=0.6:alpha=1,fade=t=out:st=4.4:d=0.6:alpha=1[i];"
        f"[v0][i]overlay=0:0:enable='lt(t,5)'[v1o];"
        f"[2:v]format=rgba[e];"
        f"[v1o][e]overlay=0:0:enable='gte(t,{end_start:.2f})'[v2o];"
        f"[3:a]apad=pad_dur=8[aout]"
    )
    Path(OUT / "video_filter3.txt").write_text(vf, encoding="utf-8")
    raw = sorted(RAW.glob("*.webm"), key=lambda p: p.stat().st_mtime)[-1]
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error",
           "-i", str(raw), "-loop", "1", "-i", str(intro), "-loop", "1", "-i", str(end), "-i", str(OUT / "narration3.m4a"),
           "-filter_complex_script", str(OUT / "video_filter3.txt"),
           "-map", "[v2o]", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest",
           str(ROOT / "dist" / "citeguard-demo.mp4")]
    print("rendering", " ".join(cmd[:4]), "...")
    subprocess.run(cmd, check=True)
    print("done", dur(ROOT / "dist" / "citeguard-demo.mp4"))


if __name__ == "__main__":
    if "--build" in sys.argv:
        build()
    else:
        plan()
