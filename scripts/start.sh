#!/usr/bin/env bash
# Single-process production-style start: FastAPI serves the built SPA + API.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
export PYTHONPATH=backend
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
