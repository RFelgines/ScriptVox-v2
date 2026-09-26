#!/usr/bin/env bash
# Launch the 3 ScriptVox processes (API, Huey worker, frontend) in parallel
# and stop all of them together on Ctrl-C.
#
# Usage:  ./start.sh          production frontend (fast; rebuilt automatically when the sources changed)
#         ./start.sh --dev    Next.js dev server (hot reload; slower, compiles each page on first visit)
set -uo pipefail
DEV=0
if [ "${1:-}" = "--dev" ]; then DEV=1; fi
# Each `&` job becomes its own process group leader, so cleanup() can kill the
# whole subtree (npm run dev -> next dev is a grandchild, plain `kill $pid`
# leaves it orphaned) via `kill -TERM -$pid`.
set -m
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -x ".venv/bin/uvicorn" ]; then
    echo "No .venv found — run ./setup.sh first." >&2
    exit 1
fi
if [ ! -d "frontend/node_modules" ]; then
    echo "frontend/node_modules missing — run ./setup.sh first." >&2
    exit 1
fi
if [ ! -f ".env" ]; then
    echo "No .env found — run ./setup.sh first (or copy .env.example yourself)." >&2
    exit 1
fi

pids=()
cleanup() {
    echo
    echo "Stopping..."
    for pid in "${pids[@]}"; do
        kill -TERM "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    exit 0
}
trap cleanup INT TERM

echo "==> Starting API (uvicorn) on 127.0.0.1:8000"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
pids+=("$!")

echo "==> Starting Huey worker"
.venv/bin/python -m huey.bin.huey_consumer app.workers.tasks.huey -k thread -w 1 &
pids+=("$!")

if [ "$DEV" = "1" ]; then
    echo "==> Starting frontend (Next.js, dev mode) on :3000"
    ( cd frontend && npm run dev ) &
else
    # Production build (audit 2026-09-25, UX-10): the dev server compiles every page on first
    # visit, the main cause of the "slow app" feeling. Rebuild only when sources are newer.
    if [ ! -f "frontend/.next/BUILD_ID" ] || \
       [ -n "$(find frontend/src frontend/package.json frontend/next.config.ts \
                -newer frontend/.next/BUILD_ID -print -quit 2>/dev/null)" ]; then
        echo "==> Building frontend (first run or sources changed)"
        ( cd frontend && npm run build ) || { echo "Frontend build failed." >&2; exit 1; }
    fi
    echo "==> Starting frontend (Next.js, production) on 127.0.0.1:3000"
    ( cd frontend && npm run start -- -H 127.0.0.1 ) &
fi
pids+=("$!")

echo
echo "API:      http://localhost:8000  (docs at /docs)"
echo "Frontend: http://localhost:3000"
echo "Press Ctrl-C to stop all three."

wait
