# CiteGuard-CN runtime image.
#
# Build (context MUST be the citeguard/ directory, not docker/):
#   docker build -f docker/Dockerfile -t citeguard-cn:0.2.0 .
#   docker run --rm -p 8000:8000 -e DEEPSEEK_API_KEY=sk-... citeguard-cn:0.2.0
#
# Secrets are NEVER baked into the image: DEEPSEEK_API_KEY is read from the
# environment at run time (see docker-compose.yml). .env, data/jobs, data/cache
# and .pylibs are excluded via ../.dockerignore.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Runtime dependencies only (no pytest / httpx needed in production).
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

# Application code and the read-only benchmark results used by /benchmark.
COPY src ./src
COPY web ./web
COPY scripts ./scripts
COPY docs ./docs
COPY data/citebench_cn/results.json ./data/citebench_cn/results.json
COPY README.md NOTICE THIRD_PARTY_NOTICES.md LICENSE ./

# Writable runtime directories, owned by the unprivileged user.
RUN mkdir -p data/jobs data/cache data/uploads out \
    && useradd --create-home --uid 10001 citeguard \
    && chown -R citeguard:citeguard /app

USER citeguard

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
