#!/usr/bin/env bash
#
# One command for the whole dev stack: the Vite dev server (frontend) plus the
# pywebview app (app.py --dev, which also spins up the data-browser viewers).
#
#   ./dev.sh          stop leftovers, then start the full dev stack
#   ./dev.sh stop     stop leftovers only (app.py, viewers, Vite)
#
# Startup always sweeps first because the viewers and Vite bind fixed ports —
# a crashed session would otherwise block the next one with "port in use".
# Closing the app window or hitting Ctrl+C tears Vite down too — no orphaned
# dev servers, no juggling two terminals.
set -euo pipefail

# Always operate from the project root, regardless of where the script is called.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VITE_PORT=5273
VITE_PID=""

stop_stack() {
  # Ask the single source of truth (config.py, same .env the app uses) which
  # ports the viewers listen on, so this never drifts from what got started.
  local ports
  if ! ports=$(uv run python -c "
from config import SERVICES as s
print(s.falkordb_viewer_port, s.rqlite_viewer_port, s.qdrant_viewer_port, s.redis_viewer_port, s.agent_port)
" 2>/dev/null); then
    echo "⚠ could not read viewer ports from config.py; sweeping defaults" >&2
    ports="8787 9090 8789 8790 8791"
  fi
  ports="$VITE_PORT $ports"

  # Orphaned app instances first — killing the parent also reaps live children.
  local app_pids
  app_pids=$(pgrep -f "python.*mortgage-work/app.py" || true)
  if [ -n "$app_pids" ]; then
    echo "killing app.py: $app_pids"
    kill $app_pids 2>/dev/null || true
  fi

  # Then anything still holding a port (children whose parent died, old Vite).
  local port pids
  for port in $ports; do
    pids=$(lsof -ti tcp:"$port" || true)
    if [ -n "$pids" ]; then
      echo "killing port $port: $pids"
      kill $pids 2>/dev/null || true
    else
      echo "port $port: free"
    fi
  done

  # Grace period, then force anything that ignored SIGTERM.
  sleep 1
  for port in $ports; do
    pids=$(lsof -ti tcp:"$port" || true)
    [ -n "$pids" ] && { echo "force-killing port $port: $pids"; kill -9 $pids 2>/dev/null || true; }
  done
}

stop_stack
if [ "${1:-}" = "stop" ]; then
  echo "done."
  exit 0
fi

cleanup() {
  # Kill the Vite server (and any esbuild/node children that outlive npm).
  if [ -n "$VITE_PID" ] && kill -0 "$VITE_PID" 2>/dev/null; then
    pkill -P "$VITE_PID" 2>/dev/null || true
    kill "$VITE_PID" 2>/dev/null || true
  fi
  # Fallback sweep: strictPort means :5273 is only ever our own dev server.
  lsof -ti "tcp:${VITE_PORT}" 2>/dev/null | xargs kill 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# First run: install frontend deps so `npm run dev` doesn't fail out of the box.
if [ ! -d frontend/node_modules ]; then
  echo "▶ installing frontend deps (first run)…"
  npm install --prefix frontend
fi

echo "▶ starting Vite dev server on :${VITE_PORT}…"
npm run dev --prefix frontend &
VITE_PID=$!

# Wait for Vite to actually accept connections before launching the window,
# otherwise the app loads a blank page during the dev-server cold start.
printf "▶ waiting for Vite"
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:${VITE_PORT}" >/dev/null 2>&1; then
    echo " — ready."
    break
  fi
  # Bail early with a clear message if Vite died (e.g. port taken, bad config).
  if ! kill -0 "$VITE_PID" 2>/dev/null; then
    echo
    echo "✗ Vite exited before it was ready. See the output above." >&2
    exit 1
  fi
  printf "."
  sleep 0.5
done

echo "▶ launching app (uv run python app.py --dev)…"
# Foreground: when the window closes, we fall through to cleanup via the trap.
# `uv run` syncs the project venv from the lockfile automatically, so this always
# uses the right interpreter (no stray VIRTUAL_ENV surprises).
uv run python app.py --dev
