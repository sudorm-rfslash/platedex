#!/bin/sh
# Starts everything Platedex needs inside one container, supervised by supervisord:
#   api     FastAPI + the built web app on :8080
#   worker  plate reading (OCR on CPU, AI reader via Ollama)
#   ollama  the AI reader on the GPU (skipped when OLLAMA_URL points elsewhere or VLM_MODE / VLM_MODE_DEFAULT is off)
set -e

mkdir -p "$DATA_DIR/photos" "$DATA_DIR/ollama"

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

INTERNAL_OLLAMA=no
case "${OLLAMA_URL:-}" in
	""|"http://127.0.0.1:11434"|"http://localhost:11434") INTERNAL_OLLAMA=yes ;;
esac
VLM_START_MODE="${VLM_MODE:-${VLM_MODE_DEFAULT:-auto}}"
if [ "$VLM_START_MODE" = "off" ] && [ "${START_OLLAMA:-}" != "yes" ]; then
	INTERNAL_OLLAMA=no
fi

if [ "$INTERNAL_OLLAMA" = "yes" ]; then
	cat >> "$CONF" <<CONF

[program:ollama]
command=/usr/bin/ollama serve
user=platedex
environment=OLLAMA_HOST="127.0.0.1:11434",OLLAMA_MODELS="$DATA_DIR/ollama",HOME="/app/home"
autorestart=true
priority=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
redirect_stderr=true
CONF
	echo "Starting with the built-in Ollama (model: ${VLM_MODEL:-qwen3-vl:8b})"
else
	echo "Built-in Ollama is off (OLLAMA_URL=${OLLAMA_URL:-unset}, AI reader mode=$VLM_START_MODE)"
fi

# Fix ownership only where needed (fast on big photo folders).
find "$DATA_DIR" ! -user platedex -exec chown platedex:platedex {} + 2>/dev/null || true
exec supervisord -c "$CONF"
