#!/usr/bin/env bash
# Development: backend with auto-reload on :8000 + Vite dev server on :5173.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
( cd "$ROOT/backend" && source .venv/bin/activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 ) &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd "$ROOT/frontend" && npm run dev
