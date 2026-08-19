#!/usr/bin/env bash
#
# Start the standalone data viewers (falkordb / rqlite / qdrant / redis)
# plus the portal entry page on :19786 (lists every viewer with live status).
#
#   ./serve.sh          sync deps if needed, then start portal + configured viewers
#
# The portal always starts; a viewer starts only when its data store is
# present in browser/.env — an unconfigured one is skipped with a note,
# never with an error. Ctrl+C (or a terminal close) reaps everything this
# script started.
#
# Syncs the venv only when needed:
#   - browser/.venv is missing, or
#   - the git HEAD changed since the last sync (i.e. after `git pull`).
#
# The viewers are an independent unit (own pyproject.toml / .env), like
# server/ — nothing here reads the desktop app's root .env.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # browser/ — its own uv project

HEAD="$(git rev-parse HEAD 2>/dev/null || echo no-git)"
STAMP=".venv/.sync-head"

if [ ! -d .venv ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$HEAD" ]; then
  echo "▶ syncing viewer dependencies (HEAD=$HEAD)…"
  uv sync
  echo "$HEAD" > "$STAMP"
else
  echo "▶ venv is up to date (HEAD=$HEAD), skipping sync."
fi

# Ask this unit's own config which viewers have a data store to browse.
CONFIGURED="$(uv run python -c "
from config import SERVICES
for name, script in (('falkordb', 'falkordb_viewer.py'),
                     ('rqlite', 'rqlite_viewer.py'),
                     ('qdrant', 'qdrant_viewer.py'),
                     ('redis', 'redis_viewer.py')):
    if SERVICES.configured(name):
        print(name, script)
")"

if [ -z "$CONFIGURED" ]; then
  echo "⚠ no data store configured in browser/.env — starting the portal only." >&2
  echo "  Copy browser/.env.example to browser/.env and fill in the stores." >&2
fi

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "▶ starting portal (.venv/bin/python portal.py)"
.venv/bin/python portal.py &
PIDS+=("$!")

while read -r name script; do
  [ -z "$name" ] && continue
  echo "▶ starting $name viewer (.venv/bin/python $script)"
  .venv/bin/python "$script" &
  PIDS+=("$!")
done <<< "$CONFIGURED"

PORTAL_URL="$(uv run python -c "
from config import SERVICES, VIEWER_HOST
print(f'http://{VIEWER_HOST}:{SERVICES.portal_port}')
")"
echo "✓ portal at $PORTAL_URL — Ctrl+C stops everything."
wait
