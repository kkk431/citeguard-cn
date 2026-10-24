"""Figure-claim verification through an OpenAI-compatible vision endpoint.

The product host (CPU) never loads a vision model itself: operators point
CITEGUARD_VL_ENDPOINT at a GPU service such as `scripts/local_vl_server.py`
(Qwen2.5-VL-7B-Instruct, Apache-2.0). Without that endpoint the feature is
hidden, and every call returns code="not_configured".
"""

from __future__ import annotations

import base64
import json
import re
import time

import requests

from . import config

PROMPT_VERSION = "1"
SUPPORTED_MIMES = {"image/png", "image/jpeg", "image/webp"}

PROMPT = (
    "你是论文图表核验助手。下面是一张图表和一句结论。"
    "请判断该结论是否被图表支持：完全支持输出 supported；与图表数据矛盾输出 contradicted；"
    "图表信息不足以下结论输出 insufficient。\n"
    "只输出一个 JSON 对象：{{\"verdict\":\"supported|contradicted|insufficient\",\"reason\":\"不超过30字\"}}\n"
    "结论：{claim}"
)


def available() -> bool:
    """Whether a vision endpoint is configured."""
    return bool(config.VL_ENDPOINT)


def _parse_verdict(text: str) -> dict:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        raise ValueError("模型返回中没有 JSON")
    data = json.loads(match.group(0))
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in {"supported", "contradicted", "insufficient"}:
        raise ValueError(f"未知判定：{verdict or '空'}")
    return {"verdict": verdict, "reason": str(data.get("reason", "")).strip()[:120]}


def check_figure(image_bytes: bytes, mime: str, claim: str) -> dict:
    """Return {ok, verdict, reason, model, latency_ms} or {ok: False, code, error}."""
    if not available():
        return {
            "ok": False,
            "code": "not_configured",
            "error": "未配置图表核验服务（设置 CITEGUARD_VL_ENDPOINT 指向视觉模型服务）",
        }
    mime = (mime or "").lower()
    if mime not in SUPPORTED_MIMES:
        return {"ok": False, "code": "bad_mime", "error": f"不支持的图片格式：{mime or '未知'}"}
    claim = (claim or "").strip()
    if not 5 <= len(claim) <= 500:
        return {"ok": False, "code": "bad_claim", "error": "结论需为 5–500 字"}
    if not image_bytes:
        return {"ok": False, "code": "empty_image", "error": "图片为空"}
    if len(image_bytes) > config.VL_MAX_FIGURE_MB * 1024 * 1024:
        return {"ok": False, "code": "too_large", "error": f"图片超过 {config.VL_MAX_FIGURE_MB} MB"}

    data_uri = f"data:{mime};base64," + base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": config.VL_MODEL,
        "max_tokens": 160,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": PROMPT.format(claim=claim)},
                ],
            }
        ],
    }
    headers = {"Content-Type": "application/json"}
    if config.VL_API_KEY:
        headers["Authorization"] = f"Bearer {config.VL_API_KEY}"

    started = time.perf_counter()
    try:
        resp = requests.post(
            config.VL_ENDPOINT + "/chat/completions",
            json=payload,
            headers=headers,
            timeout=config.VL_TIMEOUT,
        )
    except requests.RequestException as exc:  # noqa: BLE001
        return {"ok": False, "code": "unreachable", "error": f"核验服务不可用：{exc}"}
    latency_ms = int((time.perf_counter() - started) * 1000)
    if resp.status_code >= 400:
        return {
            "ok": False,
            "code": "http_error",
            "error": f"核验服务返回 HTTP {resp.status_code}",
        }
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = _parse_verdict(content)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return {"ok": False, "code": "bad_response", "error": f"无法解析核验结果：{exc}"}
    return {
        "ok": True,
        "verdict": parsed["verdict"],
        "reason": parsed["reason"],
        "model": config.VL_MODEL,
        "latency_ms": latency_ms,
        "prompt_version": PROMPT_VERSION,
    }
