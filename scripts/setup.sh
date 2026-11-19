#!/usr/bin/env bash
# One-shot local setup. No credit card, no external credentials.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
bash scripts/fix-opencv.sh

if command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install --no-audit --no-fund && npm run build)
else
  echo "npm not found: frontend build skipped (backend API still works)."
fi

if [ ! -f .env ]; then cp .env.example .env; fi
echo "Setup complete. Start with: bash scripts/start.sh"
