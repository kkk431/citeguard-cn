"""Global configuration for CiteGuard-CN.

All secrets are read from environment variables; never hard-code API keys.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OUT_DIR = PROJECT_ROOT / "out"
for _d in (DATA_DIR, CACHE_DIR, OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Polite-pool contact for OpenAlex / Crossref. Set CITEGUARD_MAILTO to your email.
MAILTO = os.environ.get("CITEGUARD_MAILTO", "")
OPENALEX_MAILTO = MAILTO or "citeguard@example.org"
USER_AGENT = os.environ.get(
    "CITEGUARD_USER_AGENT",
    "CiteGuard-CN/0.1 (research prototype; citation verification; open-source)",
)

# DeepSeek API is used ONLY for baselines / distillation / pre-labelling.
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

HTTP_TIMEOUT = float(os.environ.get("CITEGUARD_HTTP_TIMEOUT", "20"))
API_SLEEP = float(os.environ.get("CITEGUARD_API_SLEEP", "0.12"))
# Optional access token for a public demo deployment. Empty means "open".
# Accepted as X-Access-Token header, Authorization: Bearer <token>, or ?token=.
ACCESS_TOKEN = os.environ.get("CITEGUARD_ACCESS_TOKEN", "").strip()
# Per-IP sliding-window limit for API routes (0 disables). Default is generous
# enough for a human demo but stops a loop from burning API credits/uploads.
try:
    RATE_LIMIT_PER_MIN = max(0, int(os.environ.get("CITEGUARD_RATE_LIMIT_PER_MIN", "120")))
except ValueError:
    RATE_LIMIT_PER_MIN = 120
# Parallel metadata lookups; keep modest to respect OpenAlex/Crossref politeness.
VERIFY_WORKERS = int(os.environ.get("CITEGUARD_VERIFY_WORKERS", "4"))

# Claim-support judge (optional; DeepSeek API is used only as a judge).
# Per-job override is available through the web form / CLI flag; this is the
# default cap on how many references get an LLM support verdict.
SUPPORT_MAX_REFS = int(os.environ.get("CITEGUARD_SUPPORT_MAX_REFS", "30"))
SUPPORT_MAX_REFS_LIMIT = 200
# Concurrent judge calls (the judge is I/O bound). Kept small so a hosted API
# or a single local model server is not overwhelmed; clamped to 1..8.
try:
    SUPPORT_WORKERS = max(1, min(8, int(os.environ.get("CITEGUARD_SUPPORT_WORKERS", "4"))))
except ValueError:
    SUPPORT_WORKERS = 4
# Two-stage judge: a coverage audit re-checks every "support" verdict and
# downgrades it to "partial" when the evidence misses part of the claim.
# Measured on ClaimSupport-CN: macro-F1 0.9005 -> 0.9328 (product path;
# 0.9439 in the standalone experiment harness). Costs one extra LLM call for
# the ~40% of items classified as support.
SUPPORT_AUDIT = os.environ.get("CITEGUARD_SUPPORT_AUDIT", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# Which audit prompt to use for stage 2 ("v1" strict empirical checklist,
# "v2" general-purpose, "v3" element checklist with examples). The best style
# depends on the judge model: hosted DeepSeek is strongest with v1, small local
# models (Qwen3-8B) need v2/v3. Measured on ClaimSupport-CN; see
# docs/support_summary.md. Invalid values fall back to v1.
SUPPORT_AUDIT_STYLE = os.environ.get("CITEGUARD_SUPPORT_AUDIT_STYLE", "auto").strip().lower()

# The support judge needs the abstract of the *cited* paper. When verification
# only found a weak title match (e.g. a random Crossref record at similarity
# 0.4), that abstract belongs to a different paper and any verdict is noise.
# Only judge when the match is trustworthy: Exact/Minor, or title similarity
# above this threshold.
SUPPORT_MIN_TITLE_SIM = float(os.environ.get("CITEGUARD_SUPPORT_MIN_TITLE_SIM", "0.90"))

# Optional custom system prompt for the support judge. Small local models follow
# the shorter scripts/support_prompt_simple.txt better than the built-in long
# prompt; custom prompts get a separate cache namespace automatically.
SUPPORT_PROMPT_FILE = os.environ.get("CITEGUARD_SUPPORT_PROMPT_FILE", "").strip()

# Upload guard for the web app.
MAX_UPLOAD_MB = int(os.environ.get("CITEGUARD_MAX_UPLOAD_MB", "30"))

# User-supplied reference library (RIS / EndNote / BibTeX / CSL-JSON / plain list).
LIBRARY_DIR = DATA_DIR / "library"
LIBRARY_FILE = LIBRARY_DIR / "library.json"

# Optional OCR fallback for scanned PDFs (needs rapidocr-onnxruntime + pypdfium2).
OCR_MAX_PAGES = int(os.environ.get("CITEGUARD_OCR_MAX_PAGES", "30"))

# Web-citation link check: reachability of `[EB/OL]` URLs (SSRF-guarded, cached).
# Disable with CITEGUARD_URL_CHECK=0 when running fully offline.
URL_CHECK_ENABLED = os.environ.get("CITEGUARD_URL_CHECK", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
URL_CHECK_TIMEOUT = float(os.environ.get("CITEGUARD_URL_CHECK_TIMEOUT", "8"))


# Optional figure-claim verification (chart/claim consistency) through an
# OpenAI-compatible vision endpoint (e.g. scripts/local_vl_server.py with
# Qwen2.5-VL on a GPU host). The feature is hidden when VL_ENDPOINT is empty.
VL_ENDPOINT = os.environ.get("CITEGUARD_VL_ENDPOINT", "").strip().rstrip("/")
VL_MODEL = os.environ.get("CITEGUARD_VL_MODEL", "qwen2.5-vl-7b").strip()
VL_API_KEY = os.environ.get("CITEGUARD_VL_API_KEY", "").strip()
VL_TIMEOUT = float(os.environ.get("CITEGUARD_VL_TIMEOUT", "60"))
VL_MAX_FIGURE_MB = int(os.environ.get("CITEGUARD_VL_MAX_FIGURE_MB", "8"))
FIGURE_PROMPT_STYLE = os.environ.get("CITEGUARD_FIGURE_PROMPT", "2").strip().lower()

# 万方开放平台（可选）。申请到「万方文献检索」订阅后，把 App Key 放进环境变量即可。
# 文档：https://ai.wfdata.com/api-detail?id=17 ；鉴权头 X-App-Key，必须 HTTPS。
WANFANG_BASE = os.environ.get("WANFANG_BASE", "https://api.wfdata.com").rstrip("/")
WANFANG_APP_KEY = os.environ.get("WANFANG_APP_KEY", "").strip()
