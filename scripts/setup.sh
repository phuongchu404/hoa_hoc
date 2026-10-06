#!/usr/bin/env bash
# One-time setup: Python env, models, frontend build. Needs internet once.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

MOLSCRIBE_REF=7296a30413eb55436702011efdff78131f66d162
RXNSCRIBE_REF=ad6b1c75d40e563e68deca0491918885948d69c7

if ! command -v uv >/dev/null 2>&1; then
  echo "→ Cài uv (trình quản lý Python)…"
  if command -v brew >/dev/null 2>&1; then brew install uv; else curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; fi
fi

echo "→ Tạo môi trường Python 3.11…"
[ -d .venv ] || uv venv --python 3.11 .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ Cài thư viện…"
uv pip install -r requirements-dev.txt
uv pip install --no-deps \
  "molscribe @ git+https://github.com/thomas0809/MolScribe.git@${MOLSCRIBE_REF}" \
  "rxnscribe @ git+https://github.com/thomas0809/RxnScribe.git@${RXNSCRIBE_REF}"

echo "→ Tải model (≈1.6 GB, chỉ lần đầu)…"
python scripts/download_models.py

echo "→ Build giao diện…"
cd "$ROOT/frontend"
if ! command -v npm >/dev/null 2>&1; then
  echo "Cần Node.js ≥ 20 (https://nodejs.org hoặc: brew install node)"; exit 1
fi
npm ci || npm install
npm run build

echo
echo "✓ Xong. Chạy ứng dụng bằng: ./scripts/start.sh"
