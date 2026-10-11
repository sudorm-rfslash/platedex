#!/bin/sh
# Starts everything Platedex needs inside one container, supervised by supervisord:
#   api     FastAPI + the built web app on :8080
#   worker  plate reading (OCR on CPU, optional AI reader via an external Ollama at OLLAMA_URL)
set -e

mkdir -p "$DATA_DIR/photos"

if [ "${SECRET_KEY:-change-me}" = "change-me" ]; then
	echo "WARNING: SECRET_KEY is not set. Generate one with: openssl rand -hex 32" >&2
fi

platedex migrate

CONF=/tmp/supervisord.conf
cat > "$CONF" <<CONF
[supervisord]
nodaemon=true
user=root
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:api]
command=uvicorn platedex.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips=*
user=platedex
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true

[program:worker]
command=platedex worker
user=platedex
autorestart=true
startsecs=5
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
CONF

if [ -n "${OLLAMA_URL:-}" ]; then
	echo "AI reader: Ollama at $OLLAMA_URL (model: ${VLM_MODEL:-qwen3-vl:8b})"
else
	echo "AI reader off: OLLAMA_URL is not set. OCR runs alone."
fi

# Fix ownership only where needed (fast on big photo folders).
find "$DATA_DIR" ! -user platedex -exec chown platedex:platedex {} + 2>/dev/null || true
exec supervisord -c "$CONF"
