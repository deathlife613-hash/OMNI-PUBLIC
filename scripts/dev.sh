#!/usr/bin/env bash
# Run from the repo root on Linux/macOS: ./scripts/dev.sh
# Frontend in a second terminal: cd frontend && npm install && npm run dev
set -euo pipefail
cd "$(dirname "$0")/../backend"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
[ -f ../.env ] || { cp ../.env.example ../.env; echo "Created .env from template."; }
exec .venv/bin/python -m uvicorn app.main:app --reload --port 8000
