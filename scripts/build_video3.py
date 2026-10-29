"""Build take 3: one global speed for exact picture / voice / subtitle sync.

raw webm -> setpts / SPEED; every narration cue is anchored at mark / SPEED and
the ASS subtitles are generated from the same cue list. Voice: Windows SAPI
(male, offline) because edge-tts currently returns 403.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path("D:/ai+ky/citeguard")
OUT = ROOT / "out/video"
DIST = ROOT / "dist"
AUD = OUT / "audio3"
AUD.mkdir(parents=True, exist_ok=True)
TARGET = 292.0
TRAIL = 5.0

marks = {m["name"]: m["t"] for m in json.loads((OUT / "timeline4.json").read_text(encoding="utf-8"))}
RAW_DUR = marks["record_end"]
SPEED = max(1.0, min(1.6, RAW_DUR / TARGET))
FINAL = RAW_DUR / SPEED
TOTAL = FINAL + TRAIL
F = {k: v / SPEED for k, v in marks.items()}
print(f"raw={RAW_DUR:.1f}s speed={SPEED:.3f} final={FINAL:.1f}s total={TOTAL:.1f}s")

SEGMENTS: list[tuple[str, float, str]] = [
    ("start", 0.4, "引证卫士，中文引文核验工作台。"),
    ("home", 0.3, "查存在、查支持、查格式，三个问题一次说清。"),
    ("submitted", 0.3, "上传 PDF；解析、比对、判支持度、查国标，每一步都看得见。"),
    ("report_ready", 0.5, "十五条引用，零条严重不符，格式均分八十七点七。"),
    ("report_ready", 7.0, "每条都有题录、来源、国标三层证据，点开能看原文和候选来源。"),
    ("report_ready", 13.0, "右侧抽屉列出原文、来源、规范条目，还能跳知网、万方人工复核。"),
    # marks are taken at the END of each recording segment, so a segment's
    # narration must anchor on the PREVIOUS mark (= when that page appeared).
    ("report_done", 0.4, "图表核验：两句话逐句对照真实图表。"),
    ("figure_single", 2.5, "多张图一次提交，各自判断，互不干扰。"),
    ("figure_multi", 2.5, "直接传 PDF，自动定位图表页再渲染。"),
    ("figure_pdf", 3.0, "题录库二十二篇、四百一十二条；支持 RIS 导入、批量补录、整表导出。"),
    ("library", 3.0, "没有就查开放学术图谱：中文主题扩展英文词，去重排序。"),
    ("discover", 2.5, "多篇论文一次拖进来，批量跑完，汇总状态和耗时。"),
    ("batch", 3.0, "多篇论文对比：六维字段、两篇论文，真实调用判官。"),
    ("batch", 12.0, "没有播放加速，进度条在走，等待就是真实推理时间。"),
    ("batch", 45.0, "对比只做结构化抽取，不给论文打分。"),
    ("compare_done", -3.5, "六维对比：问题、方法、数据、发现、局限、可复现性。"),
    ("compare_done", 2.5, "历史任务还能挑两份报告做差异对比。"),
    ("history", 2.5, "底账：引文验证 0.9684，支持度 0.9597，真实 409 条零误判。"),
    ("benchmark", 2.5, "自研的是流水线、规则和接线；模型与数据全部开源。"),
    ("about", 2.0, "深浅主题，现场投影也能看清。"),
    ("theme", 2.0, "扫描版 PDF 没有文字层，自动 OCR，照样能核。"),
    ("ocr", 2.5, "代码、评测集、文档已公开，许可证和清单齐全。"),
    ("github", 2.5, "Apache 2.0，可审计、可复现。"),
]
CLOSING = ("让每一条引用，都经得起追问。", 292.3)
SEGMENTS.append(("__close__", 0.0, CLOSING[0]))
F["__close__"] = CLOSING[1]


def synth(i: int, text: str) -> Path:
    path = AUD / f"seg{i:02d}.wav"
    if path.exists() and path.stat().st_size > 2000:
        return path
    tf = AUD / f"seg{i:02d}.txt"
    tf.write_text(text, encoding="utf-8")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice('Microsoft Huihui Desktop'); $s.Rate=2; "
        f"$s.SetOutputToWaveFile('{path}'); "
        f"$s.Speak((Get-Content -Raw -Encoding UTF8 '{tf}')); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return path


def dur(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def ts(t: float) -> str:
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def srt_ts(t: float) -> str:
    h = int(t // 3600); m = int(t % 3600 // 60); s = int(t % 60); ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def card(name: str, lines: list[tuple[str, int, str, str]], accent: str) -> Path:
    img = Image.new("RGB", (1920, 1080), "#050d18")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1920, 10], fill=accent)
    d.rectangle([0, 1070, 1920, 1080], fill=accent)
    y = 300
    for text, size, color, font_path in lines:
        f = ImageFont.truetype(font_path, size)
        w = d.textlength(text, font=f)
        d.text(((1920 - w) / 2, y), text, font=f, fill=color)
        y += size + 30
    path = OUT / f"{name}.png"
    img.save(path)
    return path


def intro_card() -> Path:
    return card("t3_intro", [
        ("引证卫士", 160, "#f4fbf8", "C:/Windows/Fonts/msyhbd.ttc"),
        ("CiteGuard-CN · 中文引文核验工作台", 44, "#9fc9c0", "C:/Windows/Fonts/msyh.ttc"),
        ("存在性 · 引用支持度 · GB/T 7714-2025", 34, "#7ff0cf", "C:/Windows/Fonts/msyh.ttc"),
    ], "#7ff0cf")


def main() -> None:
    metas = []
    ordered = sorted(enumerate(SEGMENTS), key=lambda x: F[x[1][0]] + x[1][1])
    for i, (anchor, off, text) in ordered:
        p = synth(i, text)
        d = dur(p)
        start = F[anchor] + off
        nxt_anchor, nxt_off = ordered[ordered.index((i, (anchor, off, text))) + 1][1][0:2] if False else ("", 0)
        metas.append({"i": i, "start": round(start, 2), "dur": round(d, 2), "text": text, "anchor": anchor})
    # gap to next cue in time order
    for k, m in enumerate(metas):
        nxt = metas[k + 1]["start"] if k + 1 < len(metas) else TOTAL
        gap = max(1.0, nxt - m["start"] - 0.2)
        m["gap"] = round(gap, 2)
        m["tempo"] = round(min(1.45, m["dur"] / gap) if m["dur"] > gap else 1.0, 3)
        if m["anchor"] == "compare_start" and m["dur"] / gap > 1.45:
            print("WARN tight cue", m["text"])
    # sync audit: every cue must start inside the scene it describes, i.e. no
    # later than the next mark after its anchor.
    names = [n for n in marks if n not in ("record_end",)]
    for m in metas:
        anchor = m["anchor"]
        if anchor not in F:
            continue
        later = [F[n] for n in names if F[n] > F[anchor] + 0.01]
        scene_end = min(later) if later else TOTAL
        if m["start"] > scene_end + 0.01:
            print(f"WARN cue after scene: {m['start']:.1f} > {scene_end:.1f} {m['text'][:20]}")
        if m["i"] == 0:
            pass
    for m in metas:
        print(f"cue {m['start']:7.2f} scene<={min([F[n] for n in names if F[n] > F[m['anchor']] + 0.01] or [TOTAL]):7.2f}  {m['text'][:30]}")
    (OUT / "narration3.json").write_text(json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8")

    inputs, filters = [], []
    for m in metas:
        inputs += ["-i", str(AUD / f"seg{m['i']:02d}.wav")]
        delay = int(m["start"] * 1000)
        filters.append(f"[{m['i']}:a]atempo={m['tempo']},adelay={delay}|{delay}[a{m['i']}]")
    mix = "".join(f"[a{m['i']}]" for m in metas) + f"amix=inputs={len(metas)}:normalize=0,alimiter=limit=0.9[aout]"
    (OUT / "audio3_filter.txt").write_text(";".join(filters + [mix]), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex_script", "audio3_filter.txt",
                    "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", str(OUT / "narration3.m4a")], check=True, cwd=str(OUT))
    print("audio", dur(OUT / "narration3.m4a"))

    ass_lines, srt_lines = [], []
    for m in metas:
        text = m["text"]
        chunks = [text[i:i + 19] for i in range(0, len(text), 19)]
        end = min(m["start"] + m["dur"] / m["tempo"], m["start"] + m["gap"])
        step = (end - m["start"]) / max(1, len(chunks))
        for k, ch in enumerate(chunks):
            a = m["start"] + k * step
            b = a + step
            ass_lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Default,,0,0,0,,{ch}")
            srt_lines.append(f"{len(srt_lines)+1}\n{srt_ts(a)} --> {srt_ts(b)}\n{ch}\n")
    ass = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,46,&H00FFFFFF,&H000000FF,&H00151010,&H80000000,-1,0,0,0,100,100,0,0,1,2.6,0.8,2,90,90,54,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ass_lines) + "\n"
    (OUT / "subs3.ass").write_text(ass, encoding="utf-8")
    (DIST / "citeguard-demo.srt").write_text("\n".join(srt_lines), encoding="utf-8")

    intro = intro_card()
    raw = sorted((OUT / "raw4").glob("*.webm"), key=lambda p: p.stat().st_mtime)[-1]
    fc = (
        f"[0:v]setpts=PTS/{SPEED},tpad=stop_mode=clone:stop_duration={TRAIL},fps=25,scale=1920:1080,format=yuv420p[base];"
        f"[1:v]format=rgba,fade=t=in:st=0:d=0.45:alpha=1,fade=t=out:st=4.0:d=0.5:alpha=1[c1];"
        f"[base][c1]overlay=0:0:enable='between(t,0,4.45)'[v1];"
        f"[v1]subtitles=subs3.ass:fontsdir='C\\:/Windows/Fonts'[v2];"
        f"[v2]fade=t=out:st={TOTAL-1.2:.2f}:d=1.2[vout]"
    )
    (OUT / "video3_filter.txt").write_text(fc, encoding="utf-8")
    out = DIST / "citeguard-demo.mp4"
    cmd = ["ffmpeg", "-y", "-i", str(raw), "-i", str(intro),
           "-i", str(OUT / "narration3.m4a"), "-filter_complex_script", "video3_filter.txt",
           "-map", "[vout]", "-map", "2:a", "-t", f"{TOTAL:.2f}", "-r", "25",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True, cwd=str(OUT))
    print("out", out, out.stat().st_size, dur(out))


if __name__ == "__main__":
    main()
