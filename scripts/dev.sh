#!/usr/bin/env bash
# Development: FastAPI on :8000 and Vite on :5173 (proxies /api to :8000).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT
(cd frontend && npm run dev)
