#!/usr/bin/env bash
# Start the app on http://127.0.0.1:8000 (API + UI), fully offline.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
PORT="${PORT:-8000}"
URL="http://127.0.0.1:${PORT}"
if [ "${NO_BROWSER:-0}" != "1" ]; then
  ( for _ in $(seq 1 90); do
      if curl -fs "$URL/api/health" | grep -q '"ready":true'; then open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true; break; fi
      sleep 1
    done ) &
fi
exec uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
