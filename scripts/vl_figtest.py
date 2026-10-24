"""Run Qwen2.5-VL on a figure-claim set (executed on the GPU host).

Example:
  CUDA_VISIBLE_DEVICES=1 python scripts/vl_figtest.py \
      --model /data1/GYX/citeguard/models/Qwen2.5-VL-7B-Instruct \
      --set /data1/GYX/citeguard/figtest/figtest_synth.json \
      --out /data1/GYX/citeguard/figtest/vl_synth_results.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

PROMPT = (
    "你是论文图表核验助手。下面是一张图表和一句结论。"
    "请判断该结论是否被图表支持：完全支持输出 supported；与图表数据矛盾输出 contradicted；"
    "图表信息不足以下结论输出 insufficient。\n"
    "只输出一个 JSON 对象：{{\"verdict\":\"supported|contradicted|insufficient\",\"reason\":\"不超过30字\"}}\n"
    "结论：{claim}"
)


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"verdict": "parse_error", "reason": text[:80]}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"verdict": "parse_error", "reason": text[:80]}
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in {"supported", "contradicted", "insufficient"}:
        verdict = "parse_error"
    return {"verdict": verdict, "reason": str(data.get("reason", ""))[:80]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--set", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--image-dir", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-new-tokens", type=int, default=120)
    ap.add_argument("--max-pixels", type=int, default=1280 * 28 * 28)
    ap.add_argument("--prompt-file", default=None, help="optional prompt template with {claim}")
    args = ap.parse_args()

    prompt_template = PROMPT
    if args.prompt_file:
        prompt_template = Path(args.prompt_file).read_text(encoding="utf-8")
        if "{claim}" not in prompt_template:
            raise SystemExit("prompt file must contain {claim}")

    from qwen_vl_utils import process_vision_info

    data = json.loads(Path(args.set).read_text(encoding="utf-8"))
    base = Path(args.image_dir) if args.image_dir else Path(args.set).parent
    items = data["items"][: args.limit or None]

    t0 = time.time()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, device_map="cuda"
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(
        args.model, min_pixels=256 * 28 * 28, max_pixels=args.max_pixels
    )
    load_s = time.time() - t0
    print(f"model loaded in {load_s:.1f}s", flush=True)

    results = []
    latencies = []
    for i, item in enumerate(items, 1):
        img_path = base / item["image"]
        for label in ("supported", "contradicted"):
            claim = item[f"claim_{label}"]
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": str(img_path)},
                        {"type": "text", "text": prompt_template.format(claim=claim)},
                    ],
                }
            ]
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = processor(
                text=[text], images=image_inputs, videos=video_inputs, padding=True, return_tensors="pt"
            ).to(model.device)
            t1 = time.time()
            with torch.no_grad():
                generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            latency = time.time() - t1
            latencies.append(latency)
            trimmed = generated[:, inputs.input_ids.shape[1]:]
            answer = processor.batch_decode(
                trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]
            pred = parse_json(answer)
            results.append(
                {
                    "id": item["id"],
                    "label": label,
                    "claim": claim,
                    "pred": pred["verdict"],
                    "reason": pred["reason"],
                    "latency_s": round(latency, 2),
                    "raw": answer.strip()[:200],
                }
            )
            print(
                f"[{i}/{len(items)}] {item['id']} {label}: pred={pred['verdict']} "
                f"({latency:.2f}s)",
                flush=True,
            )

    tp = sum(1 for r in results if r["label"] == "contradicted" and r["pred"] == "contradicted")
    fn = sum(1 for r in results if r["label"] == "contradicted" and r["pred"] != "contradicted")
    fp = sum(1 for r in results if r["label"] == "supported" and r["pred"] == "contradicted")
    tn = sum(1 for r in results if r["label"] == "supported" and r["pred"] == "supported")
    n_pos = tp + fn
    n_neg = tn + fp
    summary = {
        "model": args.model,
        "n_items": len(items),
        "n_queries": len(results),
        "load_s": round(load_s, 1),
        "latency_mean_s": round(sum(latencies) / len(latencies), 2),
        "latency_p90_s": round(sorted(latencies)[int(len(latencies) * 0.9)], 2),
        "accuracy": round((tp + tn) / len(results), 4),
        "contradiction_recall": round(tp / n_pos, 4) if n_pos else None,
        "supported_recall": round(tn / n_neg, 4) if n_neg else None,
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "peak_gpu_mb": round(torch.cuda.max_memory_allocated() / 1024 / 1024, 0),
        "results": results,
    }
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
