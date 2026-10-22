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
# Parallel metadata lookups; keep modest to respect OpenAlex/Crossref politeness.
VERIFY_WORKERS = int(os.environ.get("CITEGUARD_VERIFY_WORKERS", "4"))

# Claim-support judge (optional; DeepSeek API is used only as a judge).
# Per-job override is available through the web form / CLI flag; this is the
# default cap on how many references get an LLM support verdict.
SUPPORT_MAX_REFS = int(os.environ.get("CITEGUARD_SUPPORT_MAX_REFS", "30"))
SUPPORT_MAX_REFS_LIMIT = 200

# Upload guard for the web app.
MAX_UPLOAD_MB = int(os.environ.get("CITEGUARD_MAX_UPLOAD_MB", "30"))

# User-supplied reference library (RIS / EndNote / BibTeX / CSL-JSON / plain list).
LIBRARY_DIR = DATA_DIR / "library"
LIBRARY_FILE = LIBRARY_DIR / "library.json"

# Optional OCR fallback for scanned PDFs (needs rapidocr-onnxruntime + pypdfium2).
OCR_MAX_PAGES = int(os.environ.get("CITEGUARD_OCR_MAX_PAGES", "30"))
