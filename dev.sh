#!/usr/bin/env bash
#
# One command to run the whole dev stack: the Vite dev server (frontend) plus
# the pywebview app (app.py --dev, which also spins up the data-browser viewers).
#
# It starts Vite in the background, waits until it's actually serving, then runs
# the app in the foreground. Closing the app window or hitting Ctrl+C tears the
# Vite server down too — no more orphaned dev servers or juggling two terminals.
#
# Usage:  ./dev.sh
set -euo pipefail

# Always operate from the project root, regardless of where the script is called.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VITE_PORT=5273
VITE_PID=""

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
