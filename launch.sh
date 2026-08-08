#!/usr/bin/env bash
#
# One command to launch the whole local stack: the Vite dev server (frontend)
# plus the pywebview app (app.py --dev, which also spins up the data-browser
# viewers).
#
#   ./launch.sh          stop leftovers, then launch the full local stack
#   ./launch.sh stop     stop leftovers only (app.py, viewers, Vite)
#                        (also accepts -stop / --stop)
#
# Startup always sweeps first because the viewers and Vite bind fixed ports —
# a crashed session would otherwise block the next one with "port in use".
# Closing the app window or hitting Ctrl+C tears Vite down too — no orphaned
# dev servers, no juggling two terminals.
set -euo pipefail

# Always operate from the project root, regardless of where the script is called.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Normalize: `stop`, `-stop`, `--stop` all mean stop-only. Anything else is a
# mistake — bail out rather than guess (starting the stack is not a safe default).
STOP_ONLY=0
case "${1:-}" in
  "") ;;
  stop|-stop|--stop) STOP_ONLY=1 ;;
  *) echo "unknown argument(s): $* -- usage: ./launch.sh [stop]" >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
  echo "unknown argument(s): $* -- usage: ./launch.sh [stop]" >&2
  exit 2
fi

VITE_PORT=5273
VITE_PID=""

# Every port a dev session can hold: the Vite dev server plus the viewer and
# agent ports from config.py (same .env the app reads). Captured once here so
# the startup sweep and the exit cleanup share one source of truth and neither
# has to spawn `uv run` again on the way out.
if ! SWEEP_PORTS=$(uv run python -c "
from config import SERVICES as s
print(s.falkordb_viewer_port, s.rqlite_viewer_port, s.qdrant_viewer_port, s.redis_viewer_port, s.agent_port)
" 2>/dev/null); then
  echo "⚠ could not read viewer ports from config.py; sweeping defaults" >&2
  SWEEP_PORTS="8787 9090 8789 8790 8791"
fi
SWEEP_PORTS="$VITE_PORT $SWEEP_PORTS"

stop_stack() {
  # SWEEP_PORTS (built above) is the single source of truth for every port a
  # dev session can hold — see the comment where it is computed.
  local ports="$SWEEP_PORTS"

  # Orphaned app instances first — killing the parent also reaps live children.
  # `uv run` execs the venv python from the project root, so the command line is
  # "<repo>/.venv/bin/python app.py --dev": match the parts, not one fixed order.
  # On macOS app.py then re-execs itself through a ".venv/bin/Mortgage Work"
  # alias to fix the Dock label, which drops "python" from the command line —
  # so accept the alias name too or the running app survives the sweep.
  local app_pids
  app_pids=$(pgrep -fl "app\.py" 2>/dev/null \
    | awk '/mortgage-work/ && (/python/ || /Mortgage Work/) {print $1}' || true)
  if [ -n "$app_pids" ]; then
    echo "killing app.py: $app_pids"
    kill $app_pids 2>/dev/null || true
  fi

  # Then anything still holding a port (children whose parent died, old Vite).
  local port
  for port in $ports; do
    (
      pids=$(lsof -ti tcp:"$port" || true)
      if [ -n "$pids" ]; then
        echo "killing port $port: $pids"
        kill $pids 2>/dev/null || true
      else
        echo "port $port: free"
      fi
    ) &
  done
  wait

  # Grace period, then force anything that ignored SIGTERM.
  sleep 1
  for port in $ports; do
    (
      pids=$(lsof -ti tcp:"$port" || true)
      if [ -n "$pids" ]; then
        echo "force-killing port $port: $pids"
        kill -9 $pids 2>/dev/null || true
      fi
    ) &
  done
  wait

  # Explicit success: a trailing failed test would abort the script under `set -e`.
  return 0
}

stop_stack
if [ "$STOP_ONLY" = "1" ]; then
  echo "done."
  exit 0
fi

cleanup() {
  # No re-entry: INT fires this, then the shell exits and EXIT would fire it
  # again — the port sweep below sleeps, so running it twice just wastes time.
  trap - EXIT INT TERM

  # Kill the Vite server (and any esbuild/node children that outlive npm).
  if [ -n "$VITE_PID" ] && kill -0 "$VITE_PID" 2>/dev/null; then
    pkill -P "$VITE_PID" 2>/dev/null || true
    kill "$VITE_PID" 2>/dev/null || true
  fi

  # Reap the detached servers by port. app.py starts the viewers and the
  # chat agent service with start_new_session=True, so each leads its own
  # process group — a Ctrl+C to this foreground group never reaches them.
  # app.py's own stop_viewers() reaps them on a clean exit, but that path
  # depends on a Python SIGINT handler firing inside pywebview's native run
  # loop, which on macOS can stay pending; if it never fires, agent_service
  # is orphaned and the clerk task inside it keeps ticking into the TTY.
  # Port-killing is process-group-agnostic: it reaches agent_service (and
  # clerk with it) on every exit path, however app.py happened to die.
  local port
  for port in $SWEEP_PORTS; do
    (
      pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
      [ -n "$pids" ] && kill $pids 2>/dev/null || true
    ) &
  done
  wait
  sleep 1
  for port in $SWEEP_PORTS; do
    (
      pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
      [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
    ) &
  done
  wait
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
VITE_READY=0
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:${VITE_PORT}" >/dev/null 2>&1; then
    VITE_READY=1
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
if [ "$VITE_READY" != "1" ]; then
  echo
  echo "✗ Vite did not become ready within 30s." >&2
  exit 1
fi

echo "▶ launching app (uv run python app.py --dev)…"
# Foreground: when the window closes, we fall through to cleanup via the trap.
# `uv run` syncs the project venv from the lockfile automatically, so this always
# uses the right interpreter (no stray VIRTUAL_ENV surprises).
# Tee stderr+stdout to runtime.log so the in-app Console panel can tail it.
uv run python app.py --dev 2>&1 | tee runtime.log
