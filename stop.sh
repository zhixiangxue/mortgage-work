#!/usr/bin/env bash
# Stop leftover Mortgage Work processes: the app itself plus the viewer
# servers it spawns. Ports are read from config.py (same .env the app uses),
# so this never drifts from what actually got started.
set -euo pipefail
cd "$(dirname "$0")"

# Ask the single source of truth which ports the viewers listen on
PORTS=$(uv run python -c "
from config import SERVICES as s
print(s.falkordb_viewer_port, s.rqlite_viewer_port, s.qdrant_viewer_port, s.redis_viewer_port)
")

# Orphaned app instances first — killing the parent also reaps live children
APP_PIDS=$(pgrep -f "python.*mortgage-work/app.py" || true)
if [ -n "$APP_PIDS" ]; then
  echo "killing app.py: $APP_PIDS"
  kill $APP_PIDS 2>/dev/null || true
fi

# Then anything still holding a viewer port (children whose parent died)
for port in $PORTS; do
  PIDS=$(lsof -ti tcp:"$port" || true)
  if [ -n "$PIDS" ]; then
    echo "killing port $port: $PIDS"
    kill $PIDS 2>/dev/null || true
  else
    echo "port $port: free"
  fi
done

# Grace period, then force anything that ignored SIGTERM
sleep 1
for port in $PORTS; do
  PIDS=$(lsof -ti tcp:"$port" || true)
  [ -n "$PIDS" ] && { echo "force-killing port $port: $PIDS"; kill -9 $PIDS 2>/dev/null || true; }
done

echo "done."
