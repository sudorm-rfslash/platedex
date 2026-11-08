#!/bin/sh
# Starts a throwaway Platedex for the end-to-end tests: fresh database, the built web app,
# the API and the real worker (CPU OCR, no AI reader). Playwright runs this (playwright.config.ts).
set -e
cd "$(dirname "$0")/.."
export DATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/platedex-e2e.XXXXXX")"
export STATIC_DIR="$PWD/build" SECRET_KEY=e2e-secret VLM_MODE_DEFAULT=off OLLAMA_URL=
PORT="${E2E_PORT:-4173}"
[ -f build/index.html ] || { echo "Build the web app first: npm run build" >&2; exit 1; }

cd ../backend
uv run --frozen platedex migrate
uv run --frozen platedex worker &
WORKER=$!
trap 'kill $WORKER 2>/dev/null; rm -rf "$DATA_DIR"' EXIT INT TERM
uv run --frozen uvicorn platedex.main:app --host 127.0.0.1 --port "$PORT"
