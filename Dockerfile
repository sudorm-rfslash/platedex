# syntax=docker/dockerfile:1.7
# Platedex: one image with the web app, the API, the plate-reading worker and Ollama (GPU).

# ---------- 1. Web app ----------
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. Ollama binary + CUDA runtime libraries ----------
FROM ollama/ollama:latest AS ollama

# ---------- 3. Runtime ----------
FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/app/home \
    DATA_DIR=/data \
    STATIC_DIR=/app/static \
    GEO_DIR=/app/geo \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl libglib2.0-0 libgomp1 unzip \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 1000 --create-home --home-dir /app/home --shell /usr/sbin/nologin platedex

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Python dependencies first (cached unless the lockfile changes)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev

# Plate detector + OCR models and offline place names, baked into the image
RUN platedex download-models \
 && curl -fsSL -o /tmp/cities.zip https://download.geonames.org/export/dump/cities5000.zip \
 && platedex prepare-geo /tmp/cities.zip --out /app/geo/cities.tsv.gz \
 && rm /tmp/cities.zip

COPY --from=ollama /usr/bin/ollama /usr/bin/ollama
COPY --from=ollama /usr/lib/ollama /usr/lib/ollama
COPY --from=web /web/build /app/static
COPY docker/entrypoint.sh /app/entrypoint.sh

RUN chown -R platedex:platedex /app/home && mkdir -p /data && chown platedex:platedex /data
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]
