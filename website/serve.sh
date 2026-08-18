#!/usr/bin/env bash
#
# Build-then-serve wrapper for the static website, used by supervisor
# (see mortgage-work.supervisor.conf at the repo root).
#
# Rebuilds dist/ only when needed:
#   - dist/index.html is missing, or
#   - the git HEAD changed since the last build (i.e. after `git pull`).
# Then exec's `vite preview` so supervisor manages the real server process.
#
# Redeploy flow on the server is just:
#   git pull
#   sudo supervisorctl restart mortgage-website
#
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HEAD="$(git rev-parse HEAD 2>/dev/null || echo no-git)"
STAMP="dist/.build-head"

if [ ! -f dist/index.html ] || [ ! -f "$STAMP" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$HEAD" ]; then
  echo "▶ building website (HEAD=$HEAD)…"
  if [ ! -d node_modules ]; then
    npm ci
  fi
  npm run build
  echo "$HEAD" > "$STAMP"
else
  echo "▶ dist/ is up to date (HEAD=$HEAD), skipping build."
fi

exec ./node_modules/.bin/vite preview --host 0.0.0.0 --port 5280 --strictPort
