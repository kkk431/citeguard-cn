"""Build narration + subtitles + intro/outro cards for the demo video."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("out/video")
AUD = OUT / "audio"
AUD.mkdir(parents=True, exist_ok=True)
VOICE = "zh-CN-YunxiNeural"

SEGMENTS = [
    (0.5, "引证卫士，中文引文核验工作台。查存在、查支持、查格式，三个问题，一次说清。"),
    (8.5, "所有核验都在本地流水线里跑，模型只是其中一环。"),
    (12.0, "先看一条真实论文。上传 PDF，打开支持度判定和正文图表抽检。"),
    (19.5, "解析、切分参考文献、逐条比对题录、判定引用支持度、检查国标格式，每一步都在页面上。"),
    (33.5, "十几秒结果出来：十五条引用，零条严重不符，格式均分八十七点七，正文引注与参考文献表一致。"),
    (42.0, "报告不只给结论：每条引用都有题录、来源、国标三层证据，点开就能看。"),
    (50.0, "正文里的图表也会被抽检。图一自动定位到第三页，判断这条结论被图表支持。"),
    (58.0, "支持度只判有摘要的文献；缺摘要就如实写未检测，不硬猜。"),
    (66.0, "换一条元数据偏差的条目：年份、卷期、作者、DOI，哪一层不一致，直接指出来。"),
    (80.5, "图表核验可以独立使用。先问二零二五年发文量最高，它说支持。"),
    (88.0, "把年份改成二零二三年，它立刻改判不支持。敢说不对，才有价值。"),
    (96.0, "同一个开源视觉模型，两次判断，没有一句套话。"),
    (107.5, "中文文献最头疼的是库里没有。题录库已收二十二篇真实论文、四百一十二条题录。"),
    (113.0, "支持 RIS、EndNote、BibTeX、CSL 导入，也支持批量补录和整表导出。"),
    (122.5, "找不到的文献，用开放学术图谱检索：输入中文主题，自动扩展英文关键词，去重后按相关度排序。"),
    (134.0, "一次拖三篇，批量跑完，汇总表直接给每篇的状态和耗时。"),
    (145.5, "评测页是这套东西的底账：CiteBench-CN 零点九六八四，ClaimSupport-CN 零点九五九七，真实四百零九条引用零误判。"),
    (155.0, "这些能力都跑在开源模型和开放数据上：Qwen3 十四 B、八 B、四比特，以及 OpenAlex、Crossref、arXiv。"),
    (164.0, "历史任务、断点续跑、离线包、证据包，都是为了在现场也能跑。"),
    (175.0, "自研的不是模型，是流水线、判定规则和工程接线；代码、评测集、文档全部开放。"),
    (183.0, "仓库已公开，附许可证和第三方资源清单。"),
    (186.0, "引证卫士，让每一条引用，都经得起追问。"),
]

FONT = "C:/Windows/Fonts/msyhbd.ttc"
FONT_R = "C:/Windows/Fonts/msyh.ttc"


def dur(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def synth(i: int, text: str) -> Path:
    path = AUD / f"seg{i:02d}.wav"
    if path.exists():
        return path
    raise SystemExit(f"missing {path}; run scripts/tts_sapi.ps1 first")


def card(name: str, lines: list[tuple[str, int, str, str]], accent="#7ff0cf") -> Path:
    img = Image.new("RGB", (1920, 1080), "#050d18")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1920, 10], fill=accent)
    y = 300
    for text, size, color, font_path in lines:
        f = ImageFont.truetype(font_path, size)
        w = d.textlength(text, font=f)
        d.text(((1920 - w) / 2, y), text, font=f, fill=color)
        y += size + 30
    path = OUT / f"{name}.png"
    img.save(path)
    return path


def make_cards() -> tuple[Path, Path]:
    intro = card("card_intro", [
        ("引证卫士", 160, "#f4fbf8", FONT),
        ("CiteGuard-CN · 中文引文核验工作台", 44, "#9fc9c0", FONT_R),
        ("存在性 · 引用支持度 · GB/T 7714-2025", 34, "#7ff0cf", FONT_R),
    ])
    end = card("card_end", [
        ("0 / 409", 150, "#7ff0cf", FONT),
        ("真实论文引用，零条严重不符", 42, "#dfeee9", FONT_R),
        ("github.com/kkk431/citeguard-cn", 34, "#ffb43a", FONT_R),
        ("AIC-2026-67377639", 26, "#7d9a94", FONT_R),
    ])
    return intro, end


def write_plan() -> None:
    plan = [{"i": i, "start": st, "text": text} for i, (st, text) in enumerate(SEGMENTS)]
    (OUT / "narration_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT / "narration_plan.json")


def main() -> None:
    seg_dir = AUD
    audios = []
    for i, (start, text) in enumerate(SEGMENTS):
        audios.append(synth(i, text))
    durations = [dur(p) for p in audios]
    meta = []
    for i, ((start, text), d) in enumerate(zip(SEGMENTS, durations)):
        nxt = SEGMENTS[i + 1][0] if i + 1 < len(SEGMENTS) else 199.0
        gap = max(0.6, nxt - start)
        tempo = min(1.3, d / gap) if d > gap else 1.0
        meta.append({"i": i, "start": start, "dur": round(d, 2), "gap": round(gap, 2), "tempo": round(tempo, 3), "text": text})
    (OUT / "narration.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("segments", len(meta), "total speech", round(sum(durations), 1))

    inputs = []
    filters = []
    for m in meta:
        inputs += ["-i", str(AUD / f"seg{m['i']:02d}.wav")]
        delay = int(m["start"] * 1000)
        filters.append(f"[{m['i']}:a]atempo={m['tempo']},adelay={delay}|{delay}[a{m['i']}]")
    mix = "".join(f"[a{m['i']}]" for m in meta) + f"amix=inputs={len(meta)}:normalize=0,alimiter=limit=0.9[aout]"
    fc = ";".join(filters + [mix])
    (OUT / "audio_filter.txt").write_text(fc, encoding="utf-8")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex_script", str(OUT / "audio_filter.txt"),
           "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", str(OUT / "narration.m4a")]
    subprocess.run(cmd, check=True, capture_output=True)
    print("audio", dur(OUT / "narration.m4a"))

    make_cards()
    # subtitles
    lines = []
    def ts(t: float) -> str:
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    for m in meta:
        text = m["text"]
        chunks = [text[i:i + 18] for i in range(0, len(text), 18)]
        end = m["start"] + min(m["dur"] / m["tempo"], m["gap"] - 0.2)
        step = (end - m["start"]) / max(1, len(chunks))
        for k, ch in enumerate(chunks):
            a = m["start"] + k * step
            b = a + step
            lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Default,,0,0,0,,{ch}")
    ass = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,46,&H00FFFFFF,&H000000FF,&H00151010,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,0.8,2,90,90,46,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(lines) + "\n"
    (OUT / "subs.ass").write_text(ass, encoding="utf-8")
    print("subs", len(lines))


if __name__ == "__main__":
    import sys
    if "--plan" in sys.argv:
        write_plan()
    else:
        main()
