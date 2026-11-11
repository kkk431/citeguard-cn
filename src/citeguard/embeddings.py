"""Optional embedding backend (BGE-M3 or any OpenAI-compatible endpoint).

CiteGuard never needs an embedding model to verify a reference. This layer exists
for two optional jobs: re-ranking Chinese title candidates and semantic library
search. It is deliberately **off by default**: with no endpoint configured,
callers get ``None`` / a clear ``EmbeddingError`` instead of a silent fallback.

Environment contract (same names as the OpenAI-compatible API):

``CITEGUARD_EMBED_ENDPOINT``   base URL, e.g. ``http://127.0.0.1:8080/v1``
``CITEGUARD_EMBED_MODEL``      default ``BAAI/bge-m3``
``CITEGUARD_EMBED_API_KEY``    optional bearer token
``CITEGUARD_EMBED_TIMEOUT``    seconds, default 30

The endpoint must implement ``POST {base}/embeddings`` and return::

    {"data": [{"embedding": [0.1, ...]}, ...]}

which is what vLLM, TEI's OpenAI shim and Xinference expose. We do not bundle
model weights and do not download anything at import time.
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


class EmbeddingError(RuntimeError):
    """Raised when an embedding call is configured but cannot be completed."""


@dataclass(frozen=True)
class EmbeddingConfig:
    endpoint: str
    model: str = "BAAI/bge-m3"
    api_key: str = ""
    timeout: float = 30.0

    def url(self) -> str:
        base = self.endpoint.rstrip("/")
        if base.endswith("/embeddings"):
            return base
        return base + "/embeddings"


def load_config(environ: dict | None = None) -> EmbeddingConfig | None:
    """Return a config when ``CITEGUARD_EMBED_ENDPOINT`` is set, else ``None``."""
    env = os.environ if environ is None else environ
    endpoint = (env.get("CITEGUARD_EMBED_ENDPOINT") or "").strip()
    if not endpoint:
        return None
    try:
        timeout = float(env.get("CITEGUARD_EMBED_TIMEOUT") or 30)
    except ValueError:
        timeout = 30.0
    return EmbeddingConfig(
        endpoint=endpoint,
        model=(env.get("CITEGUARD_EMBED_MODEL") or "BAAI/bge-m3").strip(),
        api_key=(env.get("CITEGUARD_EMBED_API_KEY") or "").strip(),
        timeout=max(1.0, timeout),
    )


def is_configured() -> bool:
    return load_config() is not None


def embed_texts(
    texts: list[str],
    config: EmbeddingConfig | None = None,
    opener=urllib.request.urlopen,
) -> list[list[float]]:
    """Embed ``texts``; raise ``EmbeddingError`` when unconfigured or broken."""
    if not texts:
        return []
    cfg = config or load_config()
    if cfg is None:
        raise EmbeddingError(
            "未配置向量服务：设置 CITEGUARD_EMBED_ENDPOINT（如 http://127.0.0.1:8080/v1）后重试；"
            "不启用也不影响核验。"
        )
    body = json.dumps({"model": cfg.model, "input": list(texts)}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    req = urllib.request.Request(cfg.url(), data=body, headers=headers, method="POST")
    try:
        with opener(req, timeout=cfg.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise EmbeddingError(f"向量服务返回 HTTP {exc.code}：{detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EmbeddingError(f"连不上向量服务 {cfg.url()}：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise EmbeddingError("向量服务返回的不是 JSON，请确认是 OpenAI 兼容的 /embeddings 接口。") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or len(data) != len(texts):
        raise EmbeddingError("向量服务返回条数与输入不一致。")
    vectors: list[list[float]] = []
    for item in data:
        vec = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(vec, list) or not vec:
            raise EmbeddingError("向量服务返回了空向量。")
        try:
            vectors.append([float(x) for x in vec])
        except (TypeError, ValueError) as exc:
            raise EmbeddingError("向量里含有非数字值。") from exc
    return vectors


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity; returns 0.0 for a zero vector or a length mismatch."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def rerank(query: str, candidates: list[str], config: EmbeddingConfig | None = None) -> list[tuple[int, float]]:
    """Return ``(index, cosine)`` sorted descending; used by optional callers."""
    if not candidates:
        return []
    vectors = embed_texts([query, *candidates], config=config)
    q = vectors[0]
    return sorted(
        ((i, cosine(q, vec)) for i, vec in enumerate(vectors[1:])),
        key=lambda pair: pair[1],
        reverse=True,
    )
