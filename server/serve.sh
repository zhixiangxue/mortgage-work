#!/usr/bin/env bash
#
# Sync-then-serve wrapper for the auth service, used by supervisor
# (see mortgage-work.supervisor.conf at the repo root).
#
# Syncs the venv only when needed:
#   - .venv is missing, or
#   - the git HEAD changed since the last sync (i.e. after `git pull`).
# Then exec's the uvicorn app so supervisor manages the real process.
#
# Redeploy flow on the server is just:
#   git pull
#   sudo supervisorctl restart mortgage-auth
#
# Requires uv on the box:
#   curl -LsSf https://astral.sh/uv/install.sh | sh
#
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root

HEAD="$(git rev-parse HEAD 2>/dev/null || echo no-git)"
STAMP=".venv/.sync-head"

if [ ! -d .venv ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$HEAD" ]; then
  echo "▶ syncing dependencies (HEAD=$HEAD)…"
  uv sync
  echo "$HEAD" > "$STAMP"
else
  echo "▶ venv is up to date (HEAD=$HEAD), skipping sync."
fi

# main.py reads its own server/.env (bind address, SMTP, provisioning and
# client-entitlement keys) — nothing sensitive belongs in the supervisor
# conf. uvicorn binds AUTH_HOST:AUTH_PORT from that file.
exec uv run python server/main.py
