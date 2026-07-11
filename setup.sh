#!/usr/bin/env bash
# One-time (and safe-to-rerun) setup: Python venv + backend deps + frontend deps
# + scaffold the two .env files from their templates (never overwritten if present).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "==> Backend: Python virtual environment"
if [ ! -d ".venv" ]; then
    "$PYTHON_BIN" -m venv .venv
    echo "    created .venv"
else
    echo "    .venv already exists, reusing it"
fi

echo "==> Backend: installing dependencies (requirements.txt)"
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q
echo "    done (requirements-qwen.txt is NOT installed — GPU-only, opt-in, see README)"

echo "==> Backend: environment file"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "    created .env from .env.example — edit it to choose your LLM provider"
else
    echo "    .env already exists, left untouched"
fi

echo "==> Frontend: npm dependencies"
( cd frontend && npm install --no-fund --no-audit )

echo "==> Frontend: environment file"
if [ ! -f "frontend/.env.local" ]; then
    cp frontend/.env.example frontend/.env.local
    echo "    created frontend/.env.local from frontend/.env.example"
else
    echo "    frontend/.env.local already exists, left untouched"
fi

if [ -f "scripts/doctor.py" ]; then
    echo
    # doctor.py exits 1 when it has something to flag (e.g. LLM provider not
    # reachable yet) — that's informational, not a setup failure, so it must
    # not trip `set -e` and abort before the "Setup complete" message below.
    .venv/bin/python scripts/doctor.py || true
fi

echo
echo "Setup complete. Next: ./start.sh"
