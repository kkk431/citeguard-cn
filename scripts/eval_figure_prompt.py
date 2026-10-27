"""Evaluate figure-claim prompts (v1 vs v2, with/without paper context).

Runs against a local OpenAI-compatible vision endpoint (Qwen2.5-VL-7B).
Outputs data/experiments/figure_prompt_eval.json.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SYNTH_JSON = Path(os.environ.get("FIGTEST_SYNTH_JSON", ROOT / "out/figtest_synth/figtest_synth.json"))
SYNTH = json.loads(Path(SYNTH_JSON).read_text(encoding="utf-8"))
SYNTH_FOLDER = os.environ.get("FIGTEST_SYNTH_FOLDER", "figtest_synth/images")
REAL_JSON = Path(os.environ.get("FIGTEST_REAL_JSON", ROOT / "out/figtest_real/figtest_real.json"))
REAL = json.loads(Path(REAL_JSON).read_text(encoding="utf-8"))
REAL_FOLDER = os.environ.get("FIGTEST_REAL_FOLDER", "figtest_real/images")
ENDPOINT = os.environ.get("CITEGUARD_VL_ENDPOINT", "http://127.0.0.1:8099/v1")
MODEL = os.environ.get("CITEGUARD_VL_MODEL", "qwen2.5-vl-7b")

V1 = (
    "你是论文图表核验助手。下面是一张图表和一句结论。\n"
    "请判断该结论是否被图表支持：完全支持输出 supported；与图表数据矛盾输出 contradicted；\n"
    "图表信息不足以判断输出 insufficient。\n"
    "只输出一个 JSON 对象：{{\"verdict\":\"supported|contradicted|insufficient\",\"reason\":\"不超过 40 字\"}}\n"
    "结论：{claim}"
)
V2 = (
    "你是论文图表核验助手。下面是一张图表、一句结论，以及可选的论文正文/图注摘录。\n"
    "第一步：判断结论是否被图表支持——图表数据与结论一致输出 supported；与图表数据矛盾输出 contradicted；\n"
    "图表信息不足以判断输出 insufficient。\n"
    "第二步：如果提供了正文/图注摘录，再判断它是否支持该结论。正文与图表冲突时以「矛盾」为准；\n"
    "正文没有提到该结论时仍以图表为准，并在 reason 里注明「正文未覆盖」。\n"
    "只输出一个 JSON 对象：{{\"verdict\":\"supported|contradicted|insufficient\",\"reason\":\"不超过 40 字\"}}\n"
    "{context_block}结论：{claim}"
)

V3 = (
    "你是论文图表核验助手。下面是一张图表、一句结论，以及可选的论文正文/图注摘录。\n"
    "第一步：判断结论是否被图表支持——图表数据与结论一致输出 supported；与图表数据矛盾输出 contradicted；\n"
    "图表信息不足以判断输出 insufficient。\n"
    "注意：如果结论把某个子图/对象的数值或属性归到了错误的子图/对象上（例如图中是 Cluster 2 的纵轴范围，结论写成 Cluster 3），"
    "只要图中能看出该对象明显不符，就判 contradicted，不要判 insufficient；只有确实无法从图中读出任何相关信息时才判 insufficient。\n"

    "第二步：如果提供了正文/图注摘录，再判断它是否支持该结论。正文与图表冲突时以「矛盾」为准；\n"
    "正文没有提到该结论时仍以图表为准，并在 reason 里注明「正文未覆盖」。\n"
    "只输出一个 JSON 对象：{{\"verdict\":\"supported|contradicted|insufficient\",\"reason\":\"不超过 40 字\"}}\n"
    "{context_block}结论：{claim}"
)


V4 = (
    "你是论文图表核验助手。按三步工作，最后只输出一个 JSON。\n"
    "第一步 读图：描述图表类型、标题、坐标轴/类别、图例，以及 1–2 个关键数据点（引用图中数字或标签）。\n"
    "第二步 比对：复述结论的核心断言，与第一步的读图结果逐项比较；如提供了正文/图注摘录，也用它核对。\n"
    "第三步 判定：图表明确蕴含结论输出 supported；图表数据与结论冲突（包括对象/子图/数值归属错误）输出 contradicted；\n"
    "确实无法从图中读出相关信息输出 insufficient（正文未覆盖时以图表为准，reason 里注明「正文未覆盖」）。\n"
    "只输出一个 JSON 对象：{{\"observation\":\"第一步，不超过60字\",\"verdict\":\"supported|contradicted|insufficient\",\"reason\":\"第二步+第三步，不超过40字\"}}\n"
    "{context_block}结论：{claim}"
)


def _page_text(pdf_name: str, page_no: int) -> str:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return ""
    path = ROOT / "data/real_corpus" / pdf_name
    if not path.exists():
        return ""
    doc = pdfium.PdfDocument(str(path))
    try:
        page = doc[page_no - 1]
        text = page.get_textpage().get_text_range() or ""
    finally:
        doc.close()
    return re.sub(r"\s+", " ", text).strip()[:4000]


def _context(item: dict, family: str) -> str:
    if family == "synth":
        return item.get("title", "")
    image = item["image"]  # hanspub_152575_p3_1.png
    match = re.search(r"(hanspub_\d+)_p(\d+)_", image)
    if not match:
        return item.get("title", "")
    text = _page_text(match.group(1) + ".pdf", int(match.group(2)))
    return text or item.get("title", "")


def _ask(image: str, prompt: str, folder: str) -> dict:
    data = ROOT / "out" / folder / image
    uri = "data:image/png;base64," + base64.b64encode(data.read_bytes()).decode("ascii")
    payload = {
        "model": MODEL,
        "max_tokens": 160,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": uri}},
            {"type": "text", "text": prompt},
        ]}],
    }
    started = time.perf_counter()
    resp = requests.post(ENDPOINT + "/chat/completions", json=payload, timeout=120)
    latency = int((time.perf_counter() - started) * 1000)
    content = resp.json()["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {"verdict": "unparsed", "latency_ms": latency}
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return {"verdict": "unparsed", "latency_ms": latency}
    return {"verdict": str(parsed.get("verdict", "")).lower(), "reason": parsed.get("reason", ""), "latency_ms": latency}


def _allowed(verdict: str) -> str:
    if verdict == "support":
        return "supported"
    if verdict == "contradict":
        return "contradicted"
    return "insufficient"


def run(out_path: Path, variants: list[str]) -> dict:
    rows = []
    families = [f for f in os.environ.get("FIGTEST_FAMILIES", "synth,real").split(",") if f]
    for family, data in (("synth", SYNTH["items"]), ("real", REAL["items"])):
        if family not in families:
            continue
        for item in data:
            for label_key, gold in (("claim_supported", "supported"), ("claim_contradicted", "contradicted")):
                claim = item[label_key]
                context = _context(item, family) if family == "real" else item.get("title", "")
                for variant, prompt_tpl, ctx in (
                    ("v1", V1, ""),
                    ("v2", V2, ""),
                    ("v2_context", V2, context),
                    ("v3_context", V3, context),
                    ("v3", V3, ""),
                    ("v4", V4, ""),
                    ("v4_context", V4, context),
                ):
                    if variant not in variants:
                        continue
                    prompt = prompt_tpl.format(
                        claim=claim,
                        context_block=("正文/图注摘录（可能不完整）：\n" + context + "\n") if ctx else "",
                    )
                    result = _ask(item["image"], prompt, SYNTH_FOLDER if family == "synth" else REAL_FOLDER)
                    rows.append({
                        "family": family,
                        "id": item["id"],
                        "gold": gold,
                        "variant": variant,
                        "verdict": result["verdict"],
                        "correct": result["verdict"] == gold,
                        "latency_ms": result.get("latency_ms"),
                        "reason": result.get("reason", ""),
                    })

    summary = {}
    for variant in variants:
        subset = [r for r in rows if r["variant"] == variant]
        total = len(subset)
        correct = sum(r["correct"] for r in subset)
        supported = [r for r in subset if r["gold"] == "supported"]
        contradicted = [r for r in subset if r["gold"] == "contradicted"]
        summary[variant] = {
            "n": total,
            "accuracy": round(correct / total, 4) if total else 0,
            "supported_recall": round(sum(r["correct"] for r in supported) / len(supported), 4) if supported else 0,
            "contradiction_recall": round(sum(r["correct"] for r in contradicted) / len(contradicted), 4) if contradicted else 0,
            "mean_latency_ms": round(sum(r["latency_ms"] or 0 for r in subset) / total, 1) if total else 0,
        }
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": MODEL,
        "endpoint": ENDPOINT,
        "variants": variants,
        "summary": summary,
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/experiments/figure_prompt_eval.json")
    parser.add_argument("--variants", default="v1,v2,v2_context")
    args = parser.parse_args()
    selected = [v.strip() for v in args.variants.split(",") if v.strip()]
    run(ROOT / args.out, selected)
