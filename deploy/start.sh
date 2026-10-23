#!/usr/bin/env bash
# One-command start on the VM: installs deps, builds the UI, runs API + UI on one port.
# Usage: ./deploy/start.sh            (reads .env in the repo root)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
PORT="${PORT:-8000}"

PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt

if [ ! -d frontend/dist ] || [ "${REBUILD_UI:-0}" = "1" ]; then
  command -v npm >/dev/null || { echo "npm missing: build frontend elsewhere and copy frontend/dist"; exit 1; }
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
fi

cd backend
exec ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
