"""Figure-claim verification through an OpenAI-compatible vision endpoint.

The product host (CPU) never loads a vision model itself: operators point
CITEGUARD_VL_ENDPOINT at a GPU service such as `scripts/local_vl_server.py`
(Qwen2.5-VL-7B-Instruct, Apache-2.0). Without that endpoint the feature is
hidden, and every call returns code="not_configured".

v3 adds an attribution rule (wrong subplot/object → contradicted); v2 adds an optional paper-text/context excerpt: the judge first checks the
figure, and when a context is supplied it also reports whether that context
supports or contradicts the same claim.
"""

from __future__ import annotations

import base64
import json
import re
import time

import requests

from . import config

PROMPT_VERSION = "3"
SUPPORTED_MIMES = {"image/png", "image/jpeg", "image/webp"}
MAX_CONTEXT_CHARS = 4000
MAX_CLAIMS = 5

PROMPT = (
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


PROMPT_V4 = (
    "你是论文图表核验助手。按三步工作，最后只输出一个 JSON。\n"
    "第一步 读图：描述图表类型、标题、坐标轴/类别、图例，以及 1–2 个关键数据点（引用图中数字或标签）。\n"
    "第二步 比对：复述结论的核心断言，与第一步的读图结果逐项比较；如提供了正文/图注摘录，也用它核对。\n"
    "第三步 判定：图表明确蕴含结论输出 supported；图表数据与结论冲突（包括对象/子图/数值归属错误）输出 contradicted；\n"
    "确实无法从图中读出相关信息输出 insufficient（正文未覆盖时以图表为准，reason 里注明「正文未覆盖」）。\n"
    "只输出一个 JSON 对象：{{\"observation\":\"第一步，不超过60字\",\"verdict\":\"supported|contradicted|insufficient\",\"reason\":\"第二步+第三步，不超过40字\"}}\n"
    "{context_block}结论：{claim}"
)

PROMPTS = {"2": PROMPT, "4": PROMPT_V4}


def prompt_style() -> str:
    style = (getattr(config, "FIGURE_PROMPT_STYLE", "2") or "2").strip().lower()
    return style if style in PROMPTS else "2"


def _prompt() -> tuple[str, str]:
    style = prompt_style()
    return style, PROMPTS[style]


def available() -> bool:
    """Whether a vision endpoint is configured."""
    return bool(config.VL_ENDPOINT)


def _context_block(context: str) -> str:
    text = (context or "").strip()
    if not text:
        return ""
    text = text[:MAX_CONTEXT_CHARS]
    return "正文/图注摘录（可能不完整）：\n" + text + "\n"


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


def check_figure(image_bytes: bytes, mime: str, claim: str, context: str = "") -> dict:
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
        "max_tokens": 300 if prompt_style() == "4" else 180,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": _prompt()[1].format(context_block=_context_block(context), claim=claim)},
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
        "prompt_version": _prompt()[0],
        "context_chars": min(len((context or "").strip()), MAX_CONTEXT_CHARS),
    }


def split_claims(text: str) -> list[str]:
    """One claim per line; ignore blanks and trim whitespace."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def check_claims(image_bytes: bytes, mime: str, claims: list[str], context: str = "") -> dict:
    """Judge up to ``MAX_CLAIMS`` claims against the same figure in one request batch.

    Each claim is a separate call so a single bad claim cannot poison the rest;
    the response keeps per-claim verdicts plus a summary top-level shape so the
    page can render either one card or a small table.
    """
    if not claims:
        return {"ok": False, "code": "no_claims", "error": "至少写一条结论"}
    if len(claims) > MAX_CLAIMS:
        return {"ok": False, "code": "too_many_claims", "error": f"一次最多核验 {MAX_CLAIMS} 条结论"}
    bad = [c for c in claims if not 5 <= len(c) <= 500]
    if bad:
        return {"ok": False, "code": "bad_claim", "error": f"每条结论需为 5–500 字：{bad[0][:40]}"}
    items = []
    for claim in claims:
        result = check_figure(image_bytes, mime, claim, context)
        item = {"claim": claim}
        for key in ("ok", "verdict", "reason", "code", "error", "latency_ms"):
            if key in result:
                item[key] = result[key]
        items.append(item)
    ok = any(item.get("ok") for item in items)
    return {
        "ok": ok,
        "items": items,
        "model": config.VL_MODEL,
        "prompt_version": _prompt()[0],
        "max_claims": MAX_CLAIMS,
        "context_chars": min(len((context or "").strip()), MAX_CONTEXT_CHARS),
    }
